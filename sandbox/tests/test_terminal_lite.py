from unittest.mock import MagicMock, patch
import hashlib
import uuid

import docker
from django.test import SimpleTestCase, override_settings

from terminal.broker_v2 import Identity
from sandbox.services.terminal_teardown import teardown, IdentityError
from sandbox.services import terminal_lite as lite, ledger
from sandbox.tests.test_terminal_broker import BrokerAuthorizationTests


class TeardownTests(SimpleTestCase):
    def setUp(self):
        self.identity = Identity('a' * 64, 17, 'l1', 'task', str(uuid.uuid4()))
        self.client = MagicMock()
        self.resources = {}
        for name, kind in [(self.identity.container_id, 'task'), ('terminal', 'terminal'),
                           ('terminal-broker', 'terminal-broker')]:
            obj = MagicMock()
            obj.id = self.identity.container_id if kind == 'task' else name + '-immutable-id'
            obj.labels = {'ticket-sandbox.' + k: v for k, v in {
                'type': kind, 'attempt': '17', 'queue': 'l1', 'task': 'task',
                'generation': self.identity.generation, 'target': self.identity.container_id}.items()}
            obj.attrs = {'State': {'Running': False}}
            obj.wait.return_value = {'StatusCode': 1}
            obj.remove.side_effect = lambda *a, key=name, **kw: self.resources.pop(key, None)
            self.resources[name] = obj
        self.client.containers.get.side_effect = self.lookup

    def lookup(self, name):
        if name not in self.resources:
            raise docker.errors.NotFound('absent')
        return self.resources[name]

    def test_nonzero_broker_exit_allows_exact_task_deletion_and_repeat(self):
        task = self.resources[self.identity.container_id]
        teardown(self.client, self.identity, 'terminal')
        teardown(self.client, self.identity, 'terminal')
        task.remove.assert_called_once_with(force=True)

    def test_each_foreign_identity_component_blocks_all_deletions(self):
        for field in ('attempt', 'queue', 'task', 'generation', 'target'):
            broker = self.resources['terminal-broker']
            key = 'ticket-sandbox.' + field
            old = broker.labels[key]
            broker.labels[key] = 'foreign'
            with self.assertRaises(IdentityError):
                teardown(self.client, self.identity, 'terminal')
            for obj in self.resources.values():
                obj.remove.assert_not_called()
            broker.labels[key] = old

    def test_docker_api_failure_blocks_task_deletion(self):
        self.resources['terminal-broker'].stop.side_effect = docker.errors.APIError('unavailable')
        task = self.resources[self.identity.container_id]
        with self.assertRaises(docker.errors.APIError):
            teardown(self.client, self.identity, 'terminal')
        task.remove.assert_not_called()

    def test_worker_crash_after_gateway_removal_resumes(self):
        broker = self.resources['terminal-broker']
        broker.stop.side_effect = SystemExit('worker died')
        with self.assertRaises(SystemExit):
            teardown(self.client, self.identity, 'terminal')
        broker.stop.side_effect = None
        teardown(self.client, self.identity, 'terminal')
        self.assertEqual(self.resources, {})

    def test_missing_old_id_does_not_resolve_task_by_reused_name(self):
        self.resources.pop(self.identity.container_id)
        foreign = MagicMock()
        self.resources['task-name-reused'] = foreign
        teardown(self.client, self.identity, 'terminal')
        foreign.remove.assert_not_called()


class LiteLifecycleTests(BrokerAuthorizationTests):
    def setUp(self):
        super().setUp()
        self.client_docker = MagicMock()
        self.objects = {}
        old = self.identity
        self.add('task', 'task', old['container_id'], old['generation'])
        self.add('terminal', 'terminal', old['container_id'], old['generation'])
        self.add('terminal-broker', 'terminal-broker', old['container_id'], old['generation'])
        self.client_docker.containers.get.side_effect = self.lookup
        for name, value in [('get_docker_client', self.client_docker), ('wait_for_terminal_ready', None), ('get_free_port', 24567)]:
            p = patch.object(lite.ds, name, return_value=value)
            p.start()
            self.addCleanup(p.stop)
        p = patch.object(lite.ds, 'create_task_container', side_effect=self.create_task)
        self.create = p.start()
        self.addCleanup(p.stop)
        p = patch.object(lite.ds, 'create_terminal_container', side_effect=self.create_terminal)
        self.terminal_create = p.start()
        self.addCleanup(p.stop)

    def add(self, name, kind, target_id, generation):
        obj = MagicMock()
        obj.id = target_id if kind == 'task' else hashlib.sha256(name.encode()).hexdigest()
        obj.name = name
        obj.attrs = {'State': {'Running': True}}
        obj.labels = {'ticket-sandbox.' + k: str(v) for k, v in dict(type=kind,
            attempt=self.attempt.pk, queue='l1', task='broker-task', generation=generation,
            target=target_id, terminal=name.removesuffix('-broker')).items()}
        obj.stop.side_effect = lambda **kw: obj.attrs['State'].update(Running=False)
        obj.remove.side_effect = lambda **kw: self.objects.pop(name, None)
        self.objects[name] = obj
        return obj

    def lookup(self, value):
        for obj in self.objects.values():
            if value in (obj.id, obj.name):
                return obj
        raise docker.errors.NotFound('absent')

    def create_task(self, queue, task, attempt, *, generation):
        name = lite.ds.task_resource_name(queue, task, f'{attempt}-{generation}')
        return self.add(name, 'task', hashlib.sha256(name.encode()).hexdigest(), generation)

    def create_terminal(self, queue, task, attempt, target, port, base_path, *, terminal_name):
        obj = self.lookup(target)
        self.add(terminal_name + '-broker', 'terminal-broker', target, obj.labels['ticket-sandbox.generation'])
        return self.add(terminal_name, 'terminal', target, obj.labels['ticket-sandbox.generation'])

    def test_crash_after_create_resumes_and_duplicate_does_not_reset_again(self):
        op = str(uuid.uuid4())
        def crash(*args, **kwargs):
            self.create_task(*args, **kwargs)
            raise SystemExit('worker killed before create response')
        self.create.side_effect = crash
        with self.assertRaises(SystemExit):
            lite.run(self.attempt, 'reset', op)
        self.assertEqual(self.authorize().status_code, 403)
        self.create.side_effect = self.create_task
        lite.run(self.attempt, 'reset', op)
        lite.run(self.attempt, 'reset', op)
        self.attempt.refresh_from_db()
        self.assertEqual(self.attempt.restart_count, 1)
        self.assertEqual(self.attempt.environment_status, 'ready')
        self.assertEqual(self.create.call_count, 1)
        self.assertEqual(self.authorize().status_code, 403)  # Old identity stays revoked.

    def test_cleanup_recovers_unpublished_create_and_is_repeatable(self):
        def crash(*args, **kwargs):
            self.create_task(*args, **kwargs)
            raise SystemExit('worker killed')
        self.create.side_effect = crash
        with self.assertRaises(SystemExit):
            lite.run(self.attempt, 'reset', str(uuid.uuid4()))
        lite.cleanup(self.attempt)
        lite.cleanup(self.attempt)
        self.assertEqual(self.objects, {})
        self.attempt.refresh_from_db()
        self.assertEqual(self.attempt.environment_status, 'idle')

    def test_parallel_executor_is_rejected(self):
        with lite.execution_lock(self.attempt.pk):
            with self.assertRaises(lite.OperationBusy):
                lite.run(self.attempt, 'reset', str(uuid.uuid4()))
        self.create.assert_not_called()

    def test_identity_error_preserves_old_container_and_revokes_access(self):
        self.objects['task'].labels['ticket-sandbox.generation'] = str(uuid.uuid4())
        with self.assertRaises(IdentityError):
            lite.run(self.attempt, 'reset', str(uuid.uuid4()))
        self.objects['task'].remove.assert_not_called()
        self.create.assert_not_called()
        self.assertEqual(self.authorize().status_code, 403)

    def test_completed_cleanup_fences_late_celery_delivery(self):
        op = str(uuid.uuid4())
        request, _ = ledger.request_environment(self.attempt, 'reset', op_id=op)
        lite.cleanup(self.attempt)
        lite.run(self.attempt, 'reset', op)
        self.create.assert_not_called()

    def test_first_start_accepts_new_attempt_and_publishes_in_progress(self):
        with ledger.writer():
            lite.save(self.attempt, status='new', container_id='', container_name='',
                terminal_container_name='', terminal_url='', environment_generation=None)
        self.objects.clear()
        lite.run(self.attempt, 'start', str(uuid.uuid4()))
        self.attempt.refresh_from_db()
        self.assertEqual(self.attempt.status, 'in_progress')
        self.assertEqual(self.attempt.environment_status, 'ready')

    def test_stale_docker_create_state_is_reloaded_before_readiness_check(self):
        def stale(*args, **kwargs):
            obj = self.create_task(*args, **kwargs)
            obj.attrs['State']['Running'] = False
            obj.reload.side_effect = lambda: obj.attrs['State'].update(Running=True)
            return obj
        self.create.side_effect = stale
        lite.run(self.attempt, 'reset', str(uuid.uuid4()))
        self.assertEqual(self.attempt.environment_status, 'ready')

    def test_transient_failure_remains_pending_and_same_operation_resumes(self):
        op = str(uuid.uuid4())
        self.create.side_effect = docker.errors.APIError('temporary daemon failure')
        with self.assertRaises(docker.errors.APIError):
            lite.run(self.attempt, 'reset', op)
        self.attempt.refresh_from_db()
        self.assertEqual(self.attempt.environment_status, 'restarting')
        self.create.side_effect = self.create_task
        lite.run(self.attempt, 'reset', op)
        self.assertEqual(self.attempt.environment_status, 'ready')
        self.assertEqual(self.attempt.restart_count, 1)

    def test_cleanup_after_generation_rotation_uses_old_recorded_identity(self):
        gateway = self.objects['terminal']
        gateway.stop.side_effect = SystemExit('worker died before task deletion')
        with self.assertRaises(SystemExit):
            lite.run(self.attempt, 'reset', str(uuid.uuid4()))
        gateway.stop.side_effect = lambda **kw: gateway.attrs['State'].update(Running=False)
        lite.cleanup(self.attempt)
        self.assertEqual(self.objects, {})

    def test_reconciler_requeues_committed_request_with_same_operation(self):
        from sandbox.tasks import reconcile_broker_environments
        op = str(uuid.uuid4())
        ledger.request_environment(self.attempt, 'start', op_id=op)
        with patch('sandbox.tasks.start_environment_task.delay') as send:
            reconcile_broker_environments()
        send.assert_called_once_with(self.attempt.pk, op)

    def test_late_daemon_create_after_cleanup_is_reaped_without_touching_new_generation(self):
        op = str(uuid.uuid4())
        self.create.side_effect = SystemExit('worker died with request still in flight')
        with self.assertRaises(SystemExit):
            lite.run(self.attempt, 'reset', op)
        retired_generation = self.attempt.environment_operation['generation']
        lite.cleanup(self.attempt)
        # Model Docker completing the lost request AFTER cleanup returned.
        late = self.create_task('l1', 'broker-task', self.attempt.pk, generation=retired_generation)
        self.create.side_effect = self.create_task
        lite.run(self.attempt, 'start', str(uuid.uuid4()))
        active_id = self.attempt.container_id
        lite.reap_retired(self.attempt)
        late.remove.assert_called_once_with(force=True)
        self.assertEqual(self.lookup(active_id).id, active_id)

    def test_created_but_unstarted_container_is_adopted_and_started(self):
        def unstarted(*args, **kwargs):
            obj = self.create_task(*args, **kwargs)
            obj.attrs['State'] = dict(Running=False, Status='created')
            obj.start.side_effect = lambda: obj.attrs['State'].update(Running=True, Status='running')
            raise SystemExit('worker died before Docker start')
        self.create.side_effect = unstarted
        op = str(uuid.uuid4())
        with self.assertRaises(SystemExit):
            lite.run(self.attempt, 'reset', op)
        self.create.side_effect = self.create_task
        lite.run(self.attempt, 'reset', op)
        self.assertEqual(self.attempt.environment_status, 'ready')
        self.assertEqual(self.create.call_count, 1)

    @override_settings(TERMINAL_BROKER_ENABLED=False)
    def test_disabled_flag_allows_retirement_reconciliation_but_never_launches(self):
        from sandbox.tasks import reconcile_broker_environments
        with ledger.writer():
            lite.save(self.attempt, environment_operation={'retired':[self.identity]})
        with patch('sandbox.tasks.reap_retired_broker_resources.delay') as reap, \
             patch('sandbox.tasks.start_environment_task.delay') as start:
            reconcile_broker_environments()
        reap.assert_called_once_with(self.attempt.pk)
        start.assert_not_called()

    def test_internally_consistent_foreign_checkpoint_never_authorizes_deletion(self):
        other_generation = str(uuid.uuid4())
        foreign = {**self.identity, 'attempt':self.attempt.pk+1,
                   'generation':other_generation, 'terminal':'', 'task_name':'task'}
        obj = self.objects['task']
        obj.labels.update({'ticket-sandbox.attempt':str(foreign['attempt']),
                           'ticket-sandbox.generation':other_generation})
        with ledger.writer():
            lite.save(self.attempt, environment_operation={'stage':'ready', 'retired':[foreign]})
        with self.assertRaises(IdentityError):
            lite.reap_retired(self.attempt)
        obj.remove.assert_not_called()
