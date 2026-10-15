"""Harness unit/SDK-fake tests only. No Docker endpoint is contacted."""
from contextlib import redirect_stdout
from dataclasses import asdict, replace
import copy
import io
import json
import os
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

from trusted_checker_poc.broker import Broker
from trusted_checker_poc.contracts import Runner
from trusted_checker_poc.integration.__main__ import main
from trusted_checker_poc.integration.evidence import Journal, configuration_observation, exclusive
from trusted_checker_poc.integration.runtime import Runtime, RecordingAdapter
from trusted_checker_poc.integration.safety import Approval, Denied, connect, preflight, resource_matches
from trusted_checker_poc.integration.scenarios import Inconclusive, Scenarios, expect
from trusted_checker_poc.registry import Registry, POLICY_ID
from trusted_checker_poc.state import State
from .fakes import IMAGE, FakeAdapter, fixture_target
from . import support

BASE = 'python:3.12-slim@sha256:' + 'b' * 64


def approved():
    return Approval('unix:///explicit-dedicated-test.sock', 'test-daemon', 'poc-test', IMAGE,
                    'sha256:' + 'c' * 64, BASE, approved=True, execute=True)


def sdk():
    client = MagicMock()
    client.info.return_value = {'ID': 'test-daemon', 'OSType': 'linux', 'Architecture': 'x86_64'}
    client.version.return_value = {'Version': '29.9.1'}
    client.images.get.side_effect = lambda identity: SimpleNamespace(attrs={
        'Id': identity, 'Os': 'linux', 'Architecture': 'amd64', 'Config': {}})
    return client


class IntegrationTests(support.WorkerTestCase):
    def setUp(self):
        super().setUp()
        self.directory = Path(self.temp.name) / 'run'
        self.approval = approved()
        self.client = sdk()
        self.environment = preflight(self.client, self.approval)
        self.journal = Journal(self.directory, create=True, approval=self.approval, environment=self.environment)

    def argv(self, command='run', *, allow=True, approve=True):
        args = [command, '--endpoint', self.approval.endpoint, '--approved-daemon-id', 'test-daemon',
                '--scope', 'poc-test', '--runner-image', IMAGE, '--target-image', self.approval.target_image,
                '--python-base', BASE]
        if command != 'preflight':
            args += ['--directory', str(self.directory)]
        if allow and command != 'preflight':
            args += ['--allow-execution']
        if approve:
            args += ['--approve-isolated-daemon']
        return args

    def test_denied_before_client_construction_or_any_api(self):
        for approval in (replace(self.approval, approved=False), replace(self.approval, execute=False),
                         replace(self.approval, endpoint='tcp://127.0.0.1:2375'),
                         replace(self.approval, runner_image='runner:latest'),
                         replace(self.approval, python_base='python:3.12-slim'),
                         replace(self.approval, scope='training-platform')):
            with self.subTest(approval=approval), patch('docker.DockerClient') as constructor:
                with self.assertRaises(Denied):
                    connect(approval, mutation=True)
                constructor.assert_not_called()

    def test_explicit_client_does_not_use_environment_or_context(self):
        with patch('docker.DockerClient') as constructor, patch('docker.from_env') as auto:
            connect(self.approval, mutation=True)
            constructor.assert_called_once_with(base_url=self.approval.endpoint, timeout=3, version='auto')
            auto.assert_not_called()

    def test_cli_denies_missing_execution_or_isolation_approval_before_connector(self):
        for allow, approval in ((False, True), (True, False)):
            connector = MagicMock()
            with redirect_stdout(io.StringIO()) as out:
                code = main(self.argv(allow=allow, approve=approval), connector=connector)
            self.assertEqual(code, 5)
            self.assertEqual(json.loads(out.getvalue())['status'], 'environment_not_approved')
            connector.assert_not_called()

    def test_preflight_is_read_only_and_does_not_export_env_or_host_paths(self):
        self.client.info.return_value['DockerRootDir'] = '/private/host-secret'
        self.client.images.get.side_effect = lambda identity: SimpleNamespace(attrs={
            'Id': identity, 'Os': 'linux', 'Architecture': 'amd64', 'Config': {'Env': ['TOKEN=private-secret']}})
        body = preflight(self.client, self.approval)
        self.assertEqual(body['status'], 'preflight_passed')
        self.assertNotIn('secret', json.dumps(body))
        self.assertNotIn(self.approval.endpoint, json.dumps(body))
        self.client.containers.assert_not_called()
        self.client.containers.create.assert_not_called()
        self.client.networks.create.assert_not_called()
        self.client.images.pull.assert_not_called()
        self.client.images.build.assert_not_called()

    def test_wrong_daemon_denies_before_image_network_access(self):
        self.client.info.return_value['ID'] = 'foreign'
        self.client.reset_mock()
        with self.assertRaises(Denied):
            preflight(self.client, self.approval)
        self.client.images.get.assert_not_called()
        self.client.networks.get.assert_not_called()

    def test_image_and_platform_drift_are_rejected(self):
        for changes in ({'Id': 'sha256:' + '0' * 64}, {'Architecture': 'arm64'}, {'Config': {'Volumes': {'/host': {}}}}):
            attrs = {'Id': IMAGE, 'Os': 'linux', 'Architecture': 'amd64', 'Config': {}}
            attrs.update(changes)
            self.client.images.get.side_effect = None
            self.client.images.get.return_value.attrs = attrs
            with self.assertRaises(Denied):
                preflight(self.client, self.approval)

    def test_optional_network_is_inspected_by_full_id_and_never_created(self):
        approval = replace(self.approval, network_id='d' * 64)
        network = {'Id': 'd' * 64, 'Internal': True, 'Driver': 'bridge', 'Labels': {'tc-poc.scope': 'poc-test'}}
        self.client.networks.get.return_value.attrs = network
        self.assertEqual(preflight(self.client, approval)['inspected_network_id'], 'd' * 64)
        for field, bad in [('Internal', False), ('Id', 'e' * 64), ('Labels', {'tc-poc.scope': 'foreign'})]:
            with self.subTest(field=field):
                self.client.networks.get.return_value.attrs = {**network, field: bad}
                with self.assertRaises(Denied):
                    preflight(self.client, approval)
        self.client.networks.create.assert_not_called()

    def test_private_atomic_journal_and_existing_directory_refusal(self):
        self.assertEqual(self.directory.stat().st_mode & 0o777, 0o700)
        self.assertEqual(self.journal.path.stat().st_mode & 0o777, 0o600)
        with self.assertRaises(FileExistsError):
            Journal(self.directory, create=True, approval=self.approval, environment=self.environment)
        with exclusive(self.directory):
            with self.assertRaises(BlockingIOError):
                with exclusive(self.directory):
                    self.fail('parallel writer admitted')

    def test_immutable_receipts_and_separate_cleanup_report(self):
        state = State(self.directory / 'state.sqlite')
        target = fixture_target()
        state.enroll(target)
        adapter = FakeAdapter(target)
        broker = Broker(state, Registry(runner_image_id=IMAGE), adapter, scope=target.scope)
        request = broker.issue(target.container_id, target.owner, POLICY_ID)
        result = broker.execute(request, owner=target.owner)
        self.workers.join()
        self.journal.report()
        body = json.loads((self.directory / 'report.json').read_text())
        self.assertEqual(body['terminal_receipts'][request.run_id], result)
        self.assertIn(request.run_id, body['cleanup_receipts'])
        self.assertIn('Unsigned', (self.directory / 'report.md').read_text())
        with state.db() as db:
            db.execute('UPDATE runs SET result=? WHERE id=?', (json.dumps({**result, 'reason': 'tampered'}), request.run_id))
        with self.assertRaisesRegex(ValueError, 'terminal_receipt_changed'):
            self.journal.receipts()

    def test_confirmed_cleanup_replay_does_not_call_adapter_again(self):
        state = State(self.directory / 'state.sqlite')
        target = fixture_target()
        state.enroll(target)
        adapter = FakeAdapter(target)
        broker = Broker(state, Registry(runner_image_id=IMAGE), adapter, scope=target.scope)
        request = broker.issue(target.container_id, target.owner, POLICY_ID)
        result = broker.execute(request, owner=target.owner)
        self.workers.join()
        with patch.object(adapter, 'cleanup', side_effect=AssertionError('must not call')):
            self.assertTrue(broker.cleanup(request.run_id))
            self.assertTrue(Broker(state, broker.registry, adapter, scope=target.scope).cleanup(request.run_id))
        self.assertEqual(json.loads(state.read(request.run_id)['result']), result)

    def test_unknown_never_becomes_a_passing_behavior_test(self):
        with self.assertRaises(Inconclusive):
            expect({'result': 'unknown', 'reason': 'runner_identity_mismatch'}, 'passed', 'probe_passed')
        with self.assertRaises(AssertionError):
            expect({'result': 'failed', 'reason': 'unexpected_http_response'}, 'passed')

    def record(self, kind='target'):
        facts = {'image': self.approval.target_image, 'generation': 'fixture-generation'} if kind == 'target' else {}
        record = self.journal.intent(kind, **facts)
        self.journal.recorded(record, 'e' * 64 if kind == 'target' else 'd' * 64)
        runtime = Runtime(self.client, self.approval, self.journal)
        labels = runtime.labels(record)
        attrs = {'Id': record['id'], 'Image': self.approval.target_image,
                 'Config': {'Labels': labels}, 'Labels': labels, 'Internal': True, 'Driver': 'bridge'}
        return runtime, record, attrs

    def test_ownership_requires_recorded_exact_id_image_scope_generation_and_token(self):
        runtime, record, attrs = self.record()
        self.assertTrue(resource_matches(attrs, record, self.journal.body['integration_id'], runtime.scope))
        variants = []
        for field, value in [('Id', 'f' * 64), ('Image', IMAGE)]:
            changed = copy.deepcopy(attrs); changed[field] = value; variants.append(changed)
        for field in ('tc-poc.integration', 'tc-poc.scope', 'tc-poc.generation', 'tc-poc.token', 'tc-poc.role'):
            changed = copy.deepcopy(attrs); changed['Config']['Labels'][field] = 'foreign'; variants.append(changed)
        for changed in variants:
            self.assertFalse(resource_matches(changed, record, self.journal.body['integration_id'], runtime.scope))
        self.assertFalse(resource_matches(attrs, {**record, 'status': 'create_intent'}, self.journal.body['integration_id'], runtime.scope))

    def test_network_create_intent_precedes_api_and_records_exact_returned_id(self):
        runtime = Runtime(self.client, self.approval, self.journal)
        def create(*args, **kwargs):
            saved = json.loads(self.journal.path.read_text())
            record = saved['resources'][0]
            self.assertEqual(record['status'], 'create_intent')
            attrs = {'Id': 'd' * 64, 'Labels': kwargs['labels'], 'Internal': True, 'Driver': 'bridge'}
            obj = MagicMock(); obj.id = 'd' * 64; obj.attrs = attrs
            return obj
        self.client.networks.create.side_effect = create
        record = runtime.network_create()
        self.assertEqual(record['id'], 'd' * 64)
        self.assertTrue(self.client.networks.create.call_args.kwargs['internal'])
        self.client.networks.list.assert_not_called()

    def test_lost_create_response_leaves_intent_and_does_not_guess_or_delete(self):
        runtime = Runtime(self.client, self.approval, self.journal)
        self.client.networks.create.side_effect = TimeoutError('private daemon payload')
        with self.assertRaises(TimeoutError):
            runtime.network_create()
        self.assertEqual(self.journal.body['resources'][0]['status'], 'create_intent')
        self.assertFalse(runtime.cleanup())
        self.client.networks.get.assert_not_called()
        self.client.containers.list.assert_not_called()
        self.assertNotIn('private daemon', (self.directory / 'report.json').read_text())

    def test_cleanup_exact_targets_and_networks_only_after_ownership_check(self):
        runtime, record, attrs = self.record()
        obj = MagicMock(); obj.attrs = attrs
        self.client.containers.get.return_value = obj
        self.assertTrue(runtime.cleanup())
        self.client.containers.get.assert_called_once_with(record['id'])
        obj.remove.assert_called_once_with(force=True)
        self.assertTrue(runtime.cleanup())
        obj.remove.assert_called_once()
        self.client.containers.list.assert_not_called()
        self.client.containers.prune.assert_not_called()
        self.client.networks.prune.assert_not_called()

    def test_foreign_target_and_ambiguous_remove_retain_journal_and_no_broad_delete(self):
        runtime, record, attrs = self.record()
        obj = MagicMock(); obj.attrs = copy.deepcopy(attrs)
        self.client.containers.get.return_value = obj
        obj.attrs['Config']['Labels']['tc-poc.token'] = 'foreign'
        self.assertFalse(runtime.cleanup())
        obj.remove.assert_not_called()
        obj.attrs = attrs
        obj.remove.side_effect = TimeoutError('remove response lost')
        self.assertFalse(runtime.cleanup())
        self.assertEqual(record['status'], 'recorded')
        self.client.containers.list.assert_not_called()

    def test_missing_recorded_fixture_can_be_confirmed_absent_without_runner_receipt(self):
        from docker.errors import NotFound
        runtime, record, _ = self.record()
        self.client.containers.get.side_effect = NotFound('gone')
        self.assertTrue(runtime.cleanup())
        self.assertEqual(record['removal'], 'observed_absent')
        self.assertEqual(self.journal.body['cleanup_receipts'], {})

    def test_durable_lease_without_runner_quarantines_resources(self):
        runtime, record, attrs = self.record()
        target = fixture_target()
        runtime.state.enroll(target)
        request = runtime.state.issue(target.container_id, target.owner, POLICY_ID)
        import time
        runtime.state.admit(request, target.owner, 2, time.time() + 100)
        self.assertFalse(runtime.cleanup())
        self.client.containers.get.assert_not_called()

    def test_network_with_connected_foreign_container_is_not_removed(self):
        runtime, record, attrs = self.record('network')
        attrs['Containers'] = {'foreign': {}}
        obj = MagicMock(); obj.attrs = attrs
        self.client.networks.get.return_value = obj
        self.assertFalse(runtime.cleanup())
        obj.remove.assert_not_called()

    def test_cleanup_removes_targets_before_extra_networks_created_after_them(self):
        runtime, target, target_attrs = self.record()
        network = self.journal.intent('network')
        self.journal.recorded(network, 'd' * 64)
        network_attrs = {'Id': network['id'], 'Labels': runtime.labels(network), 'Internal': True,
                         'Driver': 'bridge', 'Containers': {target['id']: {}}}
        target_obj, network_obj = MagicMock(), MagicMock()
        target_obj.attrs, network_obj.attrs = target_attrs, network_attrs
        order = []
        def target_remove(**kwargs):
            order.append('target')
            network_attrs['Containers'] = {}
        target_obj.remove.side_effect = target_remove
        network_obj.remove.side_effect = lambda: order.append('network')
        self.client.containers.get.return_value = target_obj
        self.client.networks.get.return_value = network_obj
        self.assertTrue(runtime.cleanup())
        self.assertEqual(order, ['target', 'network'])

    def test_report_command_is_offline(self):
        self.journal.report()
        (self.directory / 'report.json').unlink()  # Regenerate from crash journal.
        (self.directory / 'report.md').unlink()
        connector = MagicMock()
        with redirect_stdout(io.StringIO()) as out:
            self.assertEqual(main(['report', '--directory', str(self.directory)], connector=connector), 0)
        connector.assert_not_called()
        self.assertEqual(json.loads(out.getvalue())['status'], 'test_inconclusive')
        self.assertTrue((self.directory / 'report.md').exists())

    def test_interrupted_provision_preserves_private_artifacts_and_cleanup_status(self):
        self.directory = Path(self.temp.name) / 'new-run'
        def runtime_factory(client, approval, journal):
            runtime = MagicMock()
            runtime.provision.side_effect = RuntimeError('private endpoint/credential')
            def cleanup():
                journal.body['cleanup_status'] = 'cleanup_incomplete'
                return False
            runtime.cleanup.side_effect = cleanup
            return runtime
        with patch('trusted_checker_poc.integration.__main__.Runtime', side_effect=runtime_factory), redirect_stdout(io.StringIO()) as out:
            self.assertEqual(main(self.argv(), connector=lambda *_: self.client), 4)
        body = json.loads((self.directory / 'report.json').read_text())
        self.assertEqual(body['status'], 'test_inconclusive')
        self.assertEqual(body['cleanup_status'], 'cleanup_incomplete')
        self.assertIsNotNone(body['finished_at'])
        self.assertNotIn('credential', json.dumps(body))
        self.assertEqual(json.loads(out.getvalue())['cleanup_status'], 'cleanup_incomplete')

    def test_cleanup_cli_rejects_other_daemon_journal_before_runtime(self):
        self.journal.body['environment']['daemon_id'] = 'different-original-daemon'
        self.journal.save()
        with patch('trusted_checker_poc.integration.__main__.Runtime') as runtime, redirect_stdout(io.StringIO()):
            self.assertEqual(main(self.argv('cleanup'), connector=lambda *_: self.client), 5)
        runtime.assert_not_called()

    def test_preflight_cli_no_mutations(self):
        with redirect_stdout(io.StringIO()) as out:
            self.assertEqual(main(self.argv('preflight'), connector=lambda *_: self.client), 0)
        self.assertEqual(json.loads(out.getvalue())['status'], 'preflight_passed')
        self.client.containers.create.assert_not_called()
        self.client.networks.create.assert_not_called()

    def test_cli_defaults_to_single_prepare_diagnostic(self):
        from trusted_checker_poc.integration.__main__ import parser
        self.assertEqual(parser().parse_args(self.argv()).scenario,'prepare')
        self.assertEqual(parser().parse_args(self.argv()+['--scenario','full']).scenario,'full')

    def test_reconcile_cli_defaults_to_read_only_dry_run(self):
        args = self.argv('cleanup', allow=False)
        args[0] = 'reconcile'
        args += ['--run-id','00000000-0000-4000-8000-000000000001','--runner-id','e'*64]
        connector = MagicMock(return_value=self.client)
        with patch('trusted_checker_poc.integration.__main__.reconcile', return_value={'status':'recovery_dry_run_passed'}) as recover, \
                patch('trusted_checker_poc.integration.__main__.Runtime') as runtime, redirect_stdout(io.StringIO()):
            self.assertEqual(main(args, connector=connector), 0)
        self.assertFalse(connector.call_args.args[1])
        self.assertFalse(recover.call_args.kwargs['apply'])
        runtime.assert_not_called()
        self.assertFalse((self.directory / 'state.sqlite').exists())

    def test_reconcile_apply_requires_execution_permission_before_connection(self):
        args = self.argv('cleanup', allow=False)
        args[0] = 'reconcile'
        args += ['--run-id','00000000-0000-4000-8000-000000000001','--runner-id','e'*64,'--apply']
        connector = MagicMock()
        with redirect_stdout(io.StringIO()):
            self.assertEqual(main(args, connector=connector), 5)
        connector.assert_not_called()

    def test_scenario_unknown_is_explicit_and_receipts_saved(self):
        runtime = SimpleNamespace(journal=self.journal, adapter=SimpleNamespace(behavior=False, action=None), ensure_healthy=lambda:None)
        scenarios = Scenarios(runtime, 1)
        scenarios.case('known_unknown', lambda: expect({'result': 'unknown', 'reason': 'timeout'}, 'passed'))
        self.assertEqual(self.journal.body['scenarios'][0]['status'], 'test_inconclusive')
        self.assertTrue((self.directory / 'report.md').exists())


if __name__ == '__main__':
    unittest.main()
