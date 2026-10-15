"""Real SQLite/threads and mocked SDK. No daemon, socket or VDS access."""
from dataclasses import asdict, replace
import copy
import json
from pathlib import Path
import sqlite3
import threading
import time
import unittest
from unittest.mock import patch
from uuid import uuid4

from trusted_checker_poc.broker import Broker
from trusted_checker_poc.contracts import Runner
from trusted_checker_poc.docker_adapter import Plan
from trusted_checker_poc.integration.evidence import Journal, configuration_observation
from trusted_checker_poc.integration.runtime import RecordingAdapter
from trusted_checker_poc.integration.safety import Approval
from trusted_checker_poc.lifecycle import Lifecycle
from trusted_checker_poc.recovery import reconcile
from trusted_checker_poc.registry import Registry, POLICY_ID
from trusted_checker_poc.state import State
from . import test_docker_contract
from .fakes import IMAGE
from . import support


class RecoveryTests(support.WorkerTestCase):
    def setUp(self):
        super().setUp()
        self.directory = Path(self.temp.name) / 'run'
        self.approval = Approval('unix:///not-contacted', 'approved-dedicated-daemon', 'poc-unit',
            IMAGE, 'sha256:' + 'd'*64, 'python@sha256:'+'a'*64, approved=True, execute=True)
        self.journal = Journal(self.directory, create=True, approval=self.approval, environment={
            'daemon_id': self.approval.daemon_id,
            'images': {'runner': IMAGE, 'target': self.approval.target_image}})
        self.fixture = test_docker_contract.DockerContractTests(methodName='runTest')
        self.fixture.setUp()
        self.fixture.target = replace(self.fixture.target, scope=self.journal.body['scope'])
        self.fixture.approval = replace(self.fixture.approval, scope=self.journal.body['scope'])
        self.fixture.plan = replace(self.fixture.plan, target=self.fixture.target)
        self.fixture.client.networks.get.return_value.attrs['Labels']['tc-poc.scope'] = self.journal.body['scope']
        self.obj = self.fixture.sdk_runner()
        self.client = self.fixture.client
        self.adapter = RecordingAdapter(self.client, self.fixture.approval, self.journal)
        self.adapter.inspect_target = lambda _: self.fixture.target
        self.state = State(self.directory / 'state.sqlite')
        self.state.enroll(self.fixture.target)
        self.registry = Registry(runner_image_id=IMAGE, timeout=0.12)
        self.broker = Broker(self.state, self.registry, self.adapter, scope=self.fixture.target.scope)
        self.request = self.broker.issue(self.fixture.target.container_id, self.fixture.target.owner, POLICY_ID)
        self.created = threading.Event()
        self.event = None
        self.release = self.workers.gate()
        self.removed = threading.Event()
        self.obj.remove.side_effect = lambda **_: self.removed.set()
        self.hold = False
        self.lose = False
        self.client.api.create_container.side_effect = self.create

    def create(self, **spec):
        intent = self.state.receipt('create_intents', self.request.run_id)
        # Durable intent exists before the first Docker call.
        self.assertIsNotNone(intent)
        self.fixture.plan = Plan(self.registry.get(POLICY_ID), self.fixture.target,
            self.request.run_id, spec['environment']['POC_CHALLENGE'], intent=intent)
        self.obj.attrs = self.fixture.runner_attrs()
        self.event = {'Type': 'container', 'Action': 'create', 'timeNano': time.time_ns(),
                      'Actor': {'ID': self.obj.id, 'Attributes': {**spec['labels'], 'image': spec['image']}}}
        self.client.events.return_value = [self.event]
        self.created.set()
        if self.hold:
            self.release.wait()
        if self.lose:
            raise TimeoutError('create response lost with private payload')
        return {'Id': self.obj.id}

    def execute(self, wait=True):
        result = self.broker.execute(self.request, owner=self.fixture.target.owner)
        if wait:
            self.workers.join()
        return result

    def expire_at(self, entered):
        execution = self.workers.submit(self.execute, False)
        self.wait_for(entered)
        self.clock.advance()
        return execution.result(support.WATCHDOG)

    def has_lease(self):
        with self.state.db() as db:
            return bool(db.execute('SELECT 1 FROM locks WHERE run_id=?', (self.request.run_id,)).fetchone())

    def recover(self, *, apply=False, identity=None, approval=None):
        return reconcile(self.client, approval or self.approval, self.journal,
                         self.request.run_id, identity or self.obj.id, apply=apply)

    def await_cleanup(self):
        self.workers.join()
        with self.state.db() as db:
            self.assertIsNotNone(db.execute('SELECT 1 FROM cleanups WHERE run_id=?', (self.request.run_id,)).fetchone())
        self.assertFalse(self.has_lease())

    def test_create_returning_after_timeout_records_exact_id_without_start(self):
        self.hold = True
        terminal = self.expire_at(self.created)
        self.assertTrue(self.created.is_set())
        self.assertEqual(terminal['reason'], 'runner_deadline_exceeded')
        self.assertIsNone(self.state.read(self.request.run_id)['runner'])
        self.assertIsNone(self.state.receipt('runner_ownership', self.request.run_id))
        self.assertTrue(self.has_lease())
        self.release.set()
        self.await_cleanup()
        own = self.state.receipt('runner_ownership', self.request.run_id)
        self.assertEqual(own['container_id'], self.obj.id)
        self.assertEqual(own['source']['kind'], 'sdk_create_response')
        self.obj.start.assert_not_called()
        self.assertEqual(self.execute(), terminal)
        self.assertIsNone(self.state.read(self.request.run_id)['runner'])
        self.obj.remove.assert_called_once_with(force=True)

    def test_returned_id_is_saved_before_inspect_fails(self):
        self.client.containers.get.side_effect = TimeoutError('inspect unavailable')
        terminal = self.execute()
        own = self.state.receipt('runner_ownership', self.request.run_id)
        self.assertEqual(own['container_id'], self.obj.id)
        self.assertEqual(terminal['result'], 'unknown')
        self.assertTrue(self.has_lease())
        self.client.containers.get.side_effect = None
        self.assertTrue(self.broker.cleanup(self.request.run_id))
        self.assertFalse(self.has_lease())
        self.obj.start.assert_not_called()

    def test_managed_low_level_launch_preserves_sdk_host_configuration(self):
        from docker.types import HostConfig
        self.client.api.create_host_config.side_effect = lambda **kwargs: HostConfig(version='1.45', **kwargs)
        self.execute()
        kwargs = self.client.api.create_container.call_args.kwargs
        host = kwargs['host_config']
        self.assertTrue(host['ReadonlyRootfs'])
        self.assertFalse(host.get('Privileged', False))  # SDK omits the false default.
        self.assertEqual(host['CapDrop'], ['ALL'])
        self.assertEqual(host['Memory'], 64*1024*1024)
        self.assertEqual(host['NanoCpus'], 250_000_000)
        self.assertEqual(host['PidsLimit'], 32)
        self.assertEqual(host['NetworkMode'], self.fixture.target.network_id)
        self.assertEqual(kwargs['networking_config'], {self.fixture.target.network_id: None})
        self.assertEqual(kwargs['user'], '10001:10001')
        self.assertEqual(kwargs['entrypoint'], ['/usr/local/bin/python','-I','/checker/runner.py'])
        self.assertIn('no-new-privileges:true', host['SecurityOpt'])
        self.assertEqual(kwargs['labels']['tc-poc.integration'], self.journal.body['integration_id'])
        self.assertEqual(host['Tmpfs'], {'/scratch':'rw,noexec,nosuid,nodev,size=1m,uid=10001,gid=10001,mode=0700'})

    def test_registration_delayed_until_after_terminal_never_starts(self):
        entered = threading.Event()
        original = self.state.register_runner
        def register(*args):
            entered.set()
            self.release.wait()
            return original(*args)
        with patch.object(self.state, 'register_runner', side_effect=register):
            terminal = self.expire_at(entered)
            self.assertTrue(entered.is_set())
            self.assertEqual(terminal['reason'], 'runner_deadline_exceeded')
            self.release.set()
            self.await_cleanup()
        self.obj.start.assert_not_called()
        self.assertEqual(self.execute(), terminal)

    def test_expiry_before_registration_correctly_skips_entered_hook(self):
        original = self.adapter.prepare
        entered = threading.Event()
        def prepare(plan):
            runner = original(plan)
            self.clock.advance()  # Ownership exists, but registration is no longer permitted.
            return runner
        def register(*args):
            entered.set()
            self.fail('registration after observed deadline')
        with patch.object(self.adapter,'prepare',side_effect=prepare), \
                patch.object(self.state,'register_runner',side_effect=register):
            terminal = self.execute()
        self.assertEqual(terminal['reason'],'runner_deadline_exceeded')
        self.assertFalse(entered.is_set())
        self.assertIsNotNone(self.state.receipt('runner_ownership',self.request.run_id))
        self.assertFalse(self.has_lease())
        self.obj.start.assert_not_called()

    def test_delayed_registration_waits_for_prepare_io_before_expiring(self):
        io_entered, registered = threading.Event(), threading.Event()
        io_release = self.workers.gate()
        record = self.adapter.record_prepare_event
        original = self.state.register_runner
        def paused_io(event):
            if event['stage'] == 'before_create':
                io_entered.set()
                io_release.wait()
            record(event)
        def register(*args):
            registered.set()
            self.release.wait()
            return original(*args)
        with patch.object(self.adapter,'record_prepare_event',side_effect=paused_io), \
                patch.object(self.state,'register_runner',side_effect=register):
            execution = self.workers.submit(self.execute,False)
            try:
                self.wait_for(io_entered)
                self.assertFalse(registered.is_set())
                self.assertGreater(self.state.read(self.request.run_id)['deadline'],self.clock.time())
                io_release.set()
                self.wait_for(registered)
                self.clock.advance()
                terminal = execution.result(support.WATCHDOG)
                self.assertEqual(terminal['reason'],'runner_deadline_exceeded')
            finally:
                io_release.set()
                self.release.set()
                self.workers.join()
        self.assertFalse(self.has_lease())
        self.obj.start.assert_not_called()

    def test_expiry_before_create_does_not_require_uninitialized_event(self):
        original = self.adapter.inspect_target
        def inspect(identity):
            self.clock.advance()  # Expiry before begin/prepare is valid cancellation fencing.
            return original(identity)
        with patch.object(self.adapter,'inspect_target',side_effect=inspect):
            terminal = self.execute()
        self.assertEqual(terminal['reason'],'runner_deadline_exceeded')
        self.assertIsNone(self.event)
        self.assertFalse(self.created.is_set())
        self.client.api.create_container.assert_not_called()
        self.obj.start.assert_not_called()

    def test_unknown_create_outcome_retains_quarantine(self):
        self.lose = True
        terminal = self.execute()
        self.assertEqual(terminal['reason'], 'runner_prepare_unknown')
        self.assertIsNone(self.state.receipt('runner_ownership', self.request.run_id))
        self.assertTrue(self.has_lease())
        self.obj.remove.assert_not_called()
        self.obj.start.assert_not_called()

    def test_lost_response_recovered_from_intent_and_independent_daemon_event(self):
        self.lose = True
        terminal = self.execute()
        before = Path(self.state.path).read_bytes()
        dry = self.recover()
        self.assertEqual(dry['status'], 'recovery_dry_run_passed')
        self.assertEqual(Path(self.state.path).read_bytes(), before)
        self.assertIsNone(self.state.receipt('runner_ownership', self.request.run_id))
        self.obj.remove.assert_not_called()
        recovered = self.recover(apply=True)
        self.assertEqual(recovered['status'], 'ownership_recovered')
        self.assertTrue(self.has_lease())  # Ownership alone does not release.
        self.obj.start.assert_not_called()
        self.assertTrue(self.broker.cleanup(self.request.run_id))
        self.assertFalse(self.has_lease())
        self.assertEqual(self.execute(), terminal)
        self.client.containers.list.assert_not_called()
        self.client.containers.prune.assert_not_called()
        self.client.events.assert_called_with(since=int(self.state.receipt('create_intents', self.request.run_id)['created_epoch']),
            until=unittest.mock.ANY, filters={'container': self.obj.id, 'event':'create','type':'container'}, decode=True)

    def test_crash_between_raw_create_and_ownership_uses_same_recovery(self):
        self.workers.expected.append(SystemExit)
        with patch.object(Lifecycle, 'received', side_effect=SystemExit('simulated thread crash')):
            terminal = self.expire_at(self.created)
            self.workers.join()
        self.assertEqual(terminal['reason'], 'runner_deadline_exceeded')
        self.assertTrue(self.has_lease())
        self.assertEqual(self.recover(apply=True)['status'], 'ownership_recovered')
        self.assertTrue(self.broker.cleanup(self.request.run_id))
        self.obj.start.assert_not_called()
        self.assertEqual(self.execute(), terminal)

    def test_duplicate_recovery_and_cleanup_do_not_duplicate_ownership_or_remove(self):
        self.lose = True
        self.execute()
        self.assertEqual(self.recover(apply=True)['status'], 'ownership_recovered')
        original = self.state.receipt('runner_ownership', self.request.run_id)
        self.assertEqual(self.recover(apply=True)['status'], 'ownership_recovered')
        self.assertEqual(self.state.receipt('runner_ownership', self.request.run_id), original)
        self.assertTrue(self.broker.cleanup(self.request.run_id))
        self.assertTrue(self.broker.cleanup(self.request.run_id))
        self.obj.remove.assert_called_once_with(force=True)
        with self.state.db() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM runner_ownership').fetchone()[0], 1)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM recovery_audit').fetchone()[0], 2)

    def test_cleanup_failure_then_retry_preserves_terminal_and_lease(self):
        self.hold = True
        terminal = self.expire_at(self.created)
        self.obj.remove.side_effect = TimeoutError('remove outcome lost')
        self.release.set()
        self.workers.join()
        self.assertIsNotNone(self.state.receipt('runner_ownership', self.request.run_id))
        self.assertFalse(self.broker.cleanup(self.request.run_id))
        self.assertTrue(self.has_lease())
        self.obj.remove.side_effect = None
        self.assertTrue(self.broker.cleanup(self.request.run_id))
        self.assertFalse(self.has_lease())
        self.assertEqual(self.execute(), terminal)

    def test_foreign_image_scope_run_token_and_extra_network_are_never_adopted(self):
        self.lose = True
        self.execute()
        original = copy.deepcopy(self.obj.attrs)
        for mutation in ('id', 'image', 'scope', 'run', 'token', 'intent', 'integration', 'extra_network'):
            with self.subTest(mutation=mutation):
                self.obj.attrs = copy.deepcopy(original)
                if mutation == 'id': self.obj.attrs['Id'] = 'f'*64
                elif mutation == 'image': self.obj.attrs['Image'] = 'sha256:'+'f'*64
                elif mutation == 'extra_network': self.obj.attrs['NetworkSettings']['Networks']['foreign'] = {}
                else: self.obj.attrs['Config']['Labels']['tc-poc.'+mutation] = 'foreign'
                self.assertEqual(self.recover(apply=True)['status'], 'quarantine')
                self.assertIsNone(self.state.receipt('runner_ownership', self.request.run_id))
                self.assertTrue(self.has_lease())
                self.obj.remove.assert_not_called()

    def test_wrong_daemon_never_adopts_or_cleans(self):
        self.lose = True
        self.execute()
        outcome = self.recover(apply=True, approval=replace(self.approval, daemon_id='foreign'))
        self.assertEqual(outcome['status'], 'quarantine')
        self.assertTrue(self.has_lease())
        self.obj.remove.assert_not_called()

    def test_labels_alone_or_wrong_event_id_time_image_cannot_prove_ownership(self):
        self.lose = True
        self.execute()
        self.assertIsNotNone(self.event)
        event = copy.deepcopy(self.event)
        variants = [[], [{**event, 'timeNano': 1}]]
        for key, value in [('ID','f'*64), ('Attributes',{**event['Actor']['Attributes'], 'image':'sha256:'+'f'*64})]:
            changed = copy.deepcopy(event); changed['Actor'][key] = value; variants.append([changed])
        for events in variants:
            with self.subTest(events=events):
                self.client.events.return_value = events
                self.assertEqual(self.recover(apply=True)['status'], 'quarantine')
                self.assertTrue(self.has_lease())
                self.obj.remove.assert_not_called()

    def test_cleanup_revalidates_daemon_and_intent_token(self):
        self.lose = True
        self.execute()
        self.assertEqual(self.recover(apply=True)['status'], 'ownership_recovered')
        self.client.info.return_value = {'ID': 'foreign'}
        self.assertFalse(self.broker.cleanup(self.request.run_id))
        self.client.info.return_value = {'ID': self.approval.daemon_id}
        self.obj.attrs['Config']['Labels']['tc-poc.token'] = 'foreign'
        self.assertFalse(self.broker.cleanup(self.request.run_id))
        self.assertTrue(self.has_lease())
        self.obj.remove.assert_not_called()

    def test_append_only_receipts_and_technical_cas(self):
        self.lose = True
        terminal = self.execute()
        self.recover(apply=True)
        for table in ('create_intents', 'runner_ownership', 'recovery_audit'):
            for verb in ('DELETE FROM', 'UPDATE'):
                sql = f'{verb} {table}' + (' SET body=body' if verb == 'UPDATE' else '')
                with self.subTest(sql=sql), self.assertRaises(sqlite3.IntegrityError), self.state.db() as db:
                    db.execute(sql)
        self.assertFalse(self.state.finish(self.request.run_id, {**terminal, 'result':'passed'}))
        self.assertEqual(self.execute(), terminal)

    def test_terminal_row_does_not_grant_start_even_with_recovered_id(self):
        self.lose = True
        self.execute()
        self.recover(apply=True)
        self.assertFalse(self.state.register_runner(self.request.run_id,
            Runner(
                self.obj.id, IMAGE, self.request.run_id, self.fixture.target.scope, True)))
        with self.assertRaises(ValueError):
            self.state.start_once(self.request.run_id, self.obj.start)
        self.obj.start.assert_not_called()

    def legacy(self, with_trace=True):
        # A pre-19.1 DB has no create intent. No retroactive fabrication of one.
        row = self.state.read(self.request.run_id)
        self.state.admit(self.request, self.fixture.target.owner, 2, time.time()+1)
        self.fixture.plan = Plan(self.registry.get(POLICY_ID), self.fixture.target, self.request.run_id, 'a'*64)
        self.obj.attrs = self.fixture.runner_attrs()
        row = self.state.read(self.request.run_id)
        terminal = self.broker._result(row, self.registry.get(POLICY_ID), 'runner_deadline_exceeded', failure='timeout')
        self.state.finish(self.request.run_id, terminal)
        if with_trace:
            self.journal.body['observations'].append(configuration_observation(self.obj, self.fixture.plan, 'pre_start'))
        self.event = {'Type':'container','Action':'create','timeNano':time.time_ns(),
            'Actor':{'ID':self.obj.id,'Attributes':{**self.obj.attrs['Config']['Labels'],'image':IMAGE}}}
        self.client.events.return_value = [self.event]
        return terminal

    def test_legacy_orphan_requires_durable_sdk_observation_and_daemon_event(self):
        terminal = self.legacy()
        self.assertEqual(self.recover()['status'], 'recovery_dry_run_passed')
        self.assertEqual(self.recover(apply=True)['status'], 'ownership_recovered')
        self.assertIsNone(self.state.receipt('create_intents', self.request.run_id))
        self.assertTrue(self.broker.cleanup(self.request.run_id))
        self.assertEqual(self.execute(), terminal)

    def test_existing_orphan_without_original_sdk_trace_stays_quarantined(self):
        self.legacy(with_trace=False)
        result = self.recover(apply=True)
        self.assertEqual(result['reason'], 'durable_create_response_trace_missing')
        self.assertTrue(self.has_lease())
        self.assertIsNone(self.state.receipt('runner_ownership', self.request.run_id))
        self.obj.remove.assert_not_called()

    def test_historical_sqlite_dry_run_does_not_upgrade_or_write(self):
        self.legacy()
        with self.state.db() as db:
            schema = [(name, db.execute('SELECT sql FROM sqlite_master WHERE name=?', (name,)).fetchone()[0],
                       db.execute(f'SELECT * FROM {name}').fetchall()) for name in ('targets','runs','locks')]
        Path(self.state.path).unlink()
        db = sqlite3.connect(self.state.path)
        for name, sql, rows in schema:
            db.execute(sql)
            for row in rows:
                db.execute(f"INSERT INTO {name} VALUES ({','.join('?' for _ in row)})", tuple(row))
        db.commit(); db.close()
        before = Path(self.state.path).read_bytes()
        self.assertEqual(self.recover()['status'], 'recovery_dry_run_passed')
        self.assertEqual(Path(self.state.path).read_bytes(), before)
        self.assertEqual(self.recover(apply=True)['status'], 'ownership_recovered')
        self.assertTrue(self.broker.cleanup(self.request.run_id))

    def test_cancellation_while_start_diagnostics_blocked_prevents_sdk_start(self):
        entered = threading.Event()
        original = self.adapter.observe_runner
        def observe(obj, plan, phase):
            if phase == 'starting':
                entered.set()
                self.release.wait()
            return original(obj, plan, phase)
        with patch.object(self.adapter, 'observe_runner', side_effect=observe):
            terminal = self.expire_at(entered)
            self.assertTrue(entered.is_set())
            self.assertEqual(terminal['reason'], 'runner_deadline_exceeded')
            self.release.set()
            self.await_cleanup()
        self.obj.start.assert_not_called()
        self.assertEqual(self.execute(), terminal)

    def test_concurrent_cleanup_is_serialized_across_state_instances(self):
        self.lose = True
        self.execute()
        self.recover(apply=True)
        entered = threading.Event()
        def remove(**kwargs):
            entered.set()
            self.release.wait()
        self.obj.remove.side_effect = remove
        restarted = Broker(State(self.state.path), self.registry, self.adapter, scope=self.fixture.target.scope)
        first = self.workers.submit(self.broker.cleanup, self.request.run_id)
        try:
            self.wait_for(entered)
            second = self.workers.submit(restarted.cleanup, self.request.run_id)
        finally:
            self.release.set()
        self.assertTrue(first.result(support.WATCHDOG))
        self.assertTrue(second.result(support.WATCHDOG))
        self.workers.join()
        self.obj.remove.assert_called_once_with(force=True)
        self.assertFalse(self.has_lease())

    def test_start_invocation_and_terminal_finish_are_serialized(self):
        self.state.admit(self.request, self.fixture.target.owner, 2, self.clock.time()+2)
        intent = self.state.create_intent(self.request.run_id, self.approval.daemon_id,
                                         self.journal.body['integration_id'], 'a'*64)
        runner = Runner(self.obj.id, IMAGE, self.request.run_id, self.fixture.target.scope, True)
        self.state.own_runner(self.request.run_id, runner, daemon_id=self.approval.daemon_id,
            integration_id=self.journal.body['integration_id'], source={'kind':'sdk_create_response'}, intent_id=intent['intent_id'])
        self.assertTrue(self.state.register_runner(self.request.run_id, runner))
        entered, finish_attempted = threading.Event(), threading.Event()
        def start():
            entered.set()
            self.release.wait()
        other = State(self.state.path)
        terminal = {'result':'unknown','reason':'runner_deadline_exceeded'}
        def finish():
            finish_attempted.set()
            return other.finish(self.request.run_id, terminal)
        invocation = self.workers.submit(self.state.start_once, self.request.run_id, start)
        try:
            self.wait_for(entered)
            closing = self.workers.submit(finish)
            self.wait_for(finish_attempted)
            self.assertFalse(closing.done())
        finally:
            self.release.set()
        invocation.result(support.WATCHDOG)
        self.assertTrue(closing.result(support.WATCHDOG))
        self.workers.join()
        with self.assertRaises(ValueError):
            other.start_once(self.request.run_id, lambda: self.fail('late start'))
        self.assertEqual(json.loads(self.state.read(self.request.run_id)['result']), terminal)

    def test_wrong_run_uuid_and_events_error_keep_quarantine(self):
        self.lose = True
        self.execute()
        wrong = reconcile(self.client, self.approval, self.journal, str(uuid4()), self.obj.id, apply=True)
        self.assertEqual(wrong['status'], 'quarantine')
        self.client.events.side_effect = TimeoutError('private daemon endpoint')
        outcome = self.recover(apply=True)
        self.assertEqual(outcome['reason'], 'daemon_audit_unavailable')
        self.assertTrue(self.has_lease())
        self.obj.remove.assert_not_called()

    def test_evidence_export_redacts_secret_intent_token(self):
        self.lose = True
        self.execute()
        token = self.state.receipt('create_intents', self.request.run_id)['token']
        self.journal.report()
        report = (self.directory / 'report.json').read_text()
        self.assertNotIn(token, report)
        self.assertIn('token_digest', report)
        self.assertNotIn('POC_CHALLENGE', report)

    def test_invalid_id_and_unapproved_environment_never_contact_candidate(self):
        self.lose = True
        self.execute()
        self.client.reset_mock()
        bad = reconcile(self.client,self.approval,self.journal,'/private/secret',self.obj.id,apply=True)
        self.assertNotIn('secret', json.dumps(bad))
        self.client.containers.get.assert_not_called()
        with self.assertRaises(ValueError):
            self.recover(approval=replace(self.approval,approved=False))
        self.client.containers.get.assert_not_called()
