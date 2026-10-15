"""Diagnostic/recovery fault injection against SDK fakes, never a live daemon."""
from dataclasses import asdict
import json
from pathlib import Path
import subprocess
import sys
from unittest.mock import patch

from trusted_checker_poc.broker import Broker
from trusted_checker_poc.integration.evidence import Journal
from trusted_checker_poc.integration.runtime import RecordingAdapter
from trusted_checker_poc.integration.safety import Approval
from trusted_checker_poc.registry import Registry, POLICY_ID
from trusted_checker_poc.state import State
from .fakes import IMAGE, FakeAdapter, fixture_target
from . import test_docker_contract
from . import support


class HardeningTests(support.WorkerTestCase):
    def setUp(self):
        super().setUp()
        self.directory = Path(self.temp.name) / 'run'
        self.journal = Journal(self.directory, create=True, approval=Approval(
            'unix:///fake', 'fake-daemon', 'poc-unit', IMAGE, IMAGE, 'python@sha256:' + 'a' * 64),
            environment={'daemon_id': 'fake-daemon'})
        self.fixture = test_docker_contract.DockerContractTests(methodName='runTest')
        self.fixture.setUp()
        self.obj = self.fixture.sdk_runner()
        self.adapter = RecordingAdapter(self.fixture.client, self.fixture.approval, self.journal)
        prepare = self.adapter.prepare
        def issued_prepare(plan):
            self.fixture.plan = plan
            self.obj.attrs = self.fixture.runner_attrs()
            self.obj.attrs['Config']['Env'].append('TOKEN=do-not-export')
            return prepare(plan)
        self.adapter.prepare = issued_prepare
        self.target = self.fixture.target
        self.state = State(self.directory / 'state.sqlite')
        self.state.enroll(self.target)
        self.registry = Registry(runner_image_id=IMAGE)
        self.broker = Broker(self.state, self.registry, self.adapter, scope=self.target.scope)
        self.adapter.inspect_target = lambda identity: self.target

    def execute(self):
        request = self.broker.issue(self.target.container_id, self.target.owner, POLICY_ID)
        result = self.broker.execute(request, owner=self.target.owner)
        self.workers.join()
        return request, result

    def test_recorded_live_start_and_observation_allowlist(self):
        self.obj.attrs['Config']['Env'].append('TOKEN=do-not-export')
        request, result = self.execute()
        self.assertEqual(result['result'], 'passed')
        phases = [o['phase'] for o in self.journal.body['observations']]
        self.assertEqual(phases, ['pre_start', 'starting', 'post_start', 'finished'])
        self.assertEqual(self.journal.body['start_attempts'][request.run_id], 1)
        self.assertEqual(self.journal.body['physical_starts'][request.run_id], 1)
        self.assertNotIn('do-not-export', self.journal.path.read_text())
        self.obj.start.assert_called_once()

    def test_fast_exit_is_measured_as_rejected_exited_without_outcome(self):
        self.obj.start.side_effect = lambda: setattr(self.obj, 'attrs', self.fixture.runner_attrs('exited', detached=True))
        request, result = self.execute()
        self.assertEqual((result['result'], result['reason']), ('unknown', 'runner_identity_mismatch'))
        self.assertEqual(self.journal.body['observations'][-1]['phase'], 'post_start_rejected')
        self.assertEqual(self.journal.body['observations'][-1]['state'], 'exited')
        self.assertEqual(self.journal.body['start_attempts'][request.run_id], 1)
        self.assertNotIn(request.run_id, self.journal.body['physical_starts'])
        self.obj.logs.assert_not_called()
        self.obj.remove.assert_called_once_with(force=True)

    def test_post_start_drift_is_not_reported_as_verified_runtime(self):
        def weaken():
            self.obj.attrs = self.fixture.runner_attrs('running')
            self.obj.attrs['HostConfig']['Privileged'] = True
        self.obj.start.side_effect = weaken
        _, result = self.execute()
        self.assertEqual(result['result'], 'unknown')
        self.assertEqual(result['integrity']['checker_runtime'], 'unknown')
        self.obj.logs.assert_not_called()
        self.obj.remove.assert_called_once_with(force=True)

    def test_start_failure_and_api_timeout_are_unknown_never_technical(self):
        self.obj.start.side_effect = TimeoutError('private SDK error with credential')
        _, result = self.execute()
        self.assertEqual(result['result'], 'unknown')
        self.assertEqual(result['failure_class'], 'unknown_execution')
        self.assertNotIn('private SDK', json.dumps(result))
        self.obj.logs.assert_not_called()

    def test_lost_remove_response_then_notfound_retains_lease_and_result(self):
        from docker.errors import NotFound
        self.obj.remove.side_effect = TimeoutError('response lost')
        request, result = self.execute()
        self.assertEqual(result['result'], 'passed')
        self.fixture.client.containers.get.side_effect = NotFound('gone')
        self.assertFalse(self.broker.cleanup(request.run_id))
        with self.state.db() as db:
            self.assertIsNotNone(db.execute('SELECT 1 FROM locks WHERE run_id=?', (request.run_id,)).fetchone())
        self.assertEqual(json.loads(self.state.read(request.run_id)['result']), result)

    def test_recovery_uses_original_policy_snapshot_without_rerun(self):
        policy = self.registry.get(POLICY_ID)
        request = self.state.issue(self.target.container_id, self.target.owner, POLICY_ID, asdict(policy))
        self.state.admit(request, self.target.owner, 2, self.clock.time() - 1)
        changed = Registry(runner_image_id='sha256:' + 'f' * 64, timeout=1)
        fake = FakeAdapter(self.target)
        restarted = Broker(self.state, changed, fake, scope=self.target.scope)
        result = restarted.execute(request, owner=self.target.owner)
        self.assertEqual(result['reason'], 'execution_outcome_unknown')
        self.assertEqual(result['policy_identity'], asdict(policy))
        self.assertEqual(fake.physical_runs, 0)

    def test_completed_prelaunch_rejection_releases_without_prepare(self):
        from trusted_checker_poc.contracts import AdapterError
        self.adapter.inspect_target = lambda _: (_ for _ in ()).throw(AdapterError('target_unavailable', 'target_unavailable'))
        request, result = self.execute()
        self.assertEqual(result['result'], 'unknown')
        self.fixture.client.api.create_container.assert_not_called()
        with self.state.db() as db:
            self.assertIsNone(db.execute('SELECT 1 FROM locks WHERE run_id=?', (request.run_id,)).fetchone())

    def test_unknown_create_response_keeps_lease_even_without_runner_handle(self):
        self.fixture.client.api.create_container.side_effect = TimeoutError('unknown create')
        request, result = self.execute()
        self.assertEqual(result['reason'], 'runner_prepare_unknown')
        self.assertIsNone(self.state.read(request.run_id)['runner'])
        with self.state.db() as db:
            self.assertIsNotNone(db.execute('SELECT 1 FROM locks WHERE run_id=?', (request.run_id,)).fetchone())

    def test_inspect_still_running_at_deadline_is_not_positive_no_create_proof(self):
        import threading
        release = self.workers.gate()
        entered = threading.Event()
        def blocked(_):
            entered.set()
            release.wait()
            return self.target
        self.adapter.inspect_target = blocked
        broker = Broker(self.state, Registry(runner_image_id=IMAGE, timeout=0.03), self.adapter, scope=self.target.scope)
        request = broker.issue(self.target.container_id, self.target.owner, POLICY_ID)
        try:
            execution = self.workers.submit(broker.execute, request, owner=self.target.owner)
            self.wait_for(entered)
            self.clock.advance()
            result = execution.result(support.WATCHDOG)
            self.assertEqual(result['reason'], 'runner_deadline_exceeded')
            with self.state.db() as db:
                self.assertIsNotNone(db.execute('SELECT 1 FROM locks WHERE run_id=?', (request.run_id,)).fetchone())
        finally:
            release.set()
            self.workers.join()
            self.fixture.client.api.create_container.assert_not_called()
        self.assertEqual(json.loads(self.state.read(request.run_id)['result']), result)

    def test_scenario_checks_survive_optimization(self):
        code = "from trusted_checker_poc.integration.scenarios import require; require(False)"
        completed = subprocess.run([sys.executable, '-O', '-c', code], capture_output=True, text=True)
        self.assertNotEqual(completed.returncode, 0)
        self.assertIn('AssertionError', completed.stderr)

    def test_fixture_config_is_strict_and_reload_identity_is_digest_based(self):
        from trusted_checker_poc import synthetic_target as target
        config = self.directory / 'fixture-config.json'
        for body in ({'bind': '0.0.0.0'}, {'bind': '127.0.0.1', 'response_delay': 1.0}):
            config.write_text(json.dumps(body))
            with patch.object(target, 'CONFIG', config):
                self.assertEqual(target.read_config(), body)
        for body in ({'bind': '8.8.8.8'}, {'bind': '0.0.0.0', 'response_delay': -1},
                     {'bind': '0.0.0.0', 'response_delay': True}, {'bind': '0.0.0.0', 'response_delay': 11},
                     {'bind': '0.0.0.0', 'url': 'http://host'}):
            config.write_text(json.dumps(body))
            with patch.object(target, 'CONFIG', config), self.assertRaises(ValueError):
                target.read_config()
        self.assertNotEqual(target.config_digest({'bind': '0.0.0.0'}), target.config_digest({'bind': '127.0.0.1'}))
