from dataclasses import replace
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest import TestCase
from unittest.mock import patch
from trusted_checker_runtime.contracts import CreateTrace, ProvisionRequest, Resource
from trusted_checker_runtime.live_contract import LIVE_POLICY, LIVE_TARGET
from trusted_checker_runtime.profiles import Denied
from trusted_checker_runtime.journal import body
from trusted_checker_shadow.policy import POLICY, digest
from trusted_checker_live.recovery import OwnershipRecovery
from trusted_checker_live.runner import packet
from .support import LiveLab, uuid


class RuntimeTests(TestCase):
    def setUp(self):
        self.x = LiveLab()
        self.addCleanup(self.x.close)

    def issued_target(self):
        x = self.x
        x.authority.set_enabled(True)
        return x.authority.provision(ProvisionRequest(uuid(), x.approval.approval_uuid, x.attempt))

    def test_default_off_no_client_factory(self):
        x = self.x
        with self.assertRaises(Denied):
            x.runtime.provision_new(ProvisionRequest(uuid(), x.approval.approval_uuid, x.attempt))
        x.factory.assert_not_called()
        self.assertEqual(x.api.creates, 0)
        with self.assertRaisesRegex(Denied, 'sdk_operation_not_allowed'):
            x.adapter._call('exec_create', 'arbitrary')
        x.factory.assert_not_called()

    def test_live_policy_is_distinct_and_immutable(self):
        self.assertNotEqual(LIVE_POLICY.digest, POLICY.digest)
        self.assertEqual(POLICY.execution_mode, 'offline_fake_only')
        self.assertEqual(LIVE_POLICY.execution_mode, 'live_external_peer')
        for changes in ({'port': 80}, {'path': '/probe'}, {'version': True}, {'proxy': True}, {'redirect': True}):
            with self.subTest(changes=changes), self.assertRaises(Denied):
                replace(LIVE_POLICY, **changes)

    def test_wrong_policy_version_and_offline_mixing_rejected(self):
        x = self.x
        for changes in ({'policy_digest': POLICY.digest}, {'policy_version': 1}, {'schema_version': 1},
                        {'target_profile_digest': '0'*64}, {'authority_mode': 'offline_runtime_contract_only'}):
            with self.subTest(changes=changes), self.assertRaises(Denied):
                replace(x.approval, **changes)

    def test_full_broken_then_fixed_mock_runtime_scoped_results(self):
        x = self.x
        enrollment = x.provision_live()
        self.assertEqual(enrollment.verification_mode, 'live_runtime_chain_v2')
        broken = x.submit_live()
        self.assertEqual(broken['terminal']['result'], 'failed')
        self.assertEqual(broken['terminal']['reason'], 'peer_connection_refused')
        x.api.http = packet(x.network.target_ipv4, 200, b'APP OK: customer service is running\n', True, 'none')
        fixed = x.submit_live()
        self.assertEqual(fixed['terminal']['result'], 'passed')
        self.assertEqual(fixed['cleanup'], 'confirmed')
        self.assertEqual(fixed['terminal']['policy_digest'], LIVE_POLICY.digest)
        self.assertEqual(fixed['terminal']['criteria_scope'], 'external_ipv4_http_only')
        self.assertEqual(fixed['terminal']['local_access'], 'unverified')
        self.assertEqual(fixed['terminal']['application_authenticity'], 'unproven')
        self.assertEqual((x.api.creates, x.api.starts, x.api.removes), (3, 3, 2))

    def test_exact_ownership_is_saved_before_first_inspect(self):
        x = self.x
        intent = self.issued_target()
        original = x.api.inspect_container
        def inspect(identifier):
            report = x.authority.report(intent.intent_uuid, Resource.TARGET)
            self.assertEqual(report['owned_container_id'], identifier)
            return original(identifier)
        x.api.inspect_container = inspect
        x.adapter.create(intent)
        self.assertFalse(any(c.startswith('inspect:') for c in x.api.calls))
        x.adapter.start_target(intent.intent_uuid)
        self.assertEqual(x.api.starts, 1)

    def test_wrong_daemon_session_and_endpoint_before_create(self):
        x = self.x
        intent = self.issued_target()
        x.adapter._witness_reader = lambda ep: replace(ep.witness, process_start_ticks=999)
        with self.assertRaises(Denied):
            x.adapter.create(intent)
        self.assertEqual(x.api.creates, 0)
        x.adapter._witness_reader = lambda ep: ep.witness
        x.adapter.endpoint = replace(x.endpoint, socket_path='/run/tc-shadow/foreign.sock')
        with self.assertRaises(Denied):
            x.adapter.create(intent)
        x.factory.assert_not_called()

    def test_wrong_daemon_id_is_not_approval(self):
        x = self.x
        intent = self.issued_target()
        x.api.info = lambda: {'ID': 'foreign'}
        with self.assertRaises(Denied):
            x.adapter.create(intent)
        self.assertEqual(x.api.creates, 0)

    def test_wrong_target_image_and_network_no_create(self):
        x = self.x
        intent = self.issued_target()
        with patch.object(x.api, 'inspect_image', return_value={'Id': x.approval.runner_image_id}):
            with self.assertRaises(Denied): x.adapter.create(intent)
        with patch.object(x.api, 'inspect_network', return_value={'Id': x.network.network_id, 'Internal': False}):
            with self.assertRaises(Denied): x.adapter.create(intent)
        self.assertEqual(x.api.creates, 0)

    def test_malformed_raw_create_response_retains_ambiguity(self):
        for raw in ({'id': 'd'*64}, {'Id': 'short'}, {}, None):
            with self.subTest(raw=raw):
                x = LiveLab()
                try:
                    x.authority.set_enabled(True)
                    intent = x.authority.provision(ProvisionRequest(uuid(), x.approval.approval_uuid, x.attempt))
                    x.api.raw_hook = lambda response: raw
                    with self.assertRaises(Denied): x.adapter.create(intent)
                    report = x.authority.report(intent.intent_uuid, Resource.TARGET)
                    self.assertIsNone(report['owned_container_id'])
                    self.assertIn(report['phase'], ('create_requested', 'quarantined'))
                    with self.assertRaises(Denied): x.adapter.create(intent)
                    self.assertEqual((x.api.creates, x.api.starts), (1, 0))
                finally: x.close()

    def test_create_timeout_and_lost_response_no_recreate(self):
        x = self.x
        intent = self.issued_target()
        def lost(response): raise TimeoutError('SECRET SDK RESPONSE')
        x.api.raw_hook = lost
        with self.assertRaisesRegex(Denied, '^create_outcome_unconfirmed$'): x.adapter.create(intent)
        self.assertIn(x.target_id, x.api.objects)  # Side effect happened, response lost.
        with self.assertRaises(Denied): x.adapter.create(intent)
        self.assertEqual(x.api.creates, 1)
        self.assertIsNone(x.authority.report(intent.intent_uuid, Resource.TARGET)['owned_container_id'])

    def test_ownership_persistence_failure_blocks_progress(self):
        x = self.x
        intent = self.issued_target()
        with patch.object(x.journal, 'ownership', side_effect=OSError('SECRET')):
            with self.assertRaisesRegex(Denied, '^ownership_persistence_unconfirmed$'): x.adapter.create(intent)
        with self.assertRaises(Denied): x.adapter.start_target(intent.intent_uuid)
        with self.assertRaises(Denied): x.adapter.create(intent)
        self.assertEqual((x.api.creates, x.api.starts), (1, 0))

    def test_duplicate_create_and_initial_start_at_most_once(self):
        x = self.x
        intent = self.issued_target(); x.adapter.create(intent)
        with self.assertRaises(Denied): x.adapter.create(intent)
        x.adapter.start_target(intent.intent_uuid)
        with self.assertRaises(Denied): x.adapter.start_target(intent.intent_uuid)
        self.assertEqual((x.api.creates, x.api.starts), (1, 1))

    def test_kill_inside_raw_create_late_exact_ownership_only(self):
        x = self.x
        intent = self.issued_target()
        def kill(response):
            self.assertIn(x.runtime.kill(), ('stop_latched', 'stop_latched_control_update_pending'))
            return response
        x.api.raw_hook = kill
        x.adapter.create(intent)
        report = x.authority.report(intent.intent_uuid, Resource.TARGET)
        self.assertEqual((report['owned_container_id'], report['phase']), (x.target_id, 'quarantined'))
        with self.assertRaises(Denied): x.adapter.start_target(intent.intent_uuid)
        x.authority.set_enabled(True)
        with self.assertRaises(Denied): x.adapter.approval()
        self.assertEqual(x.api.starts, 0)

    def test_late_exact_id_preserved_after_deadline(self):
        x = self.x
        intent = self.issued_target()
        def late(response): x.clock.advance(9); return response
        x.api.raw_hook = late
        x.adapter.create(intent)
        report = x.authority.report(intent.intent_uuid, Resource.TARGET)
        self.assertEqual((report['phase'], report['cleanup']), ('quarantined', 'pending'))
        self.assertEqual(report['owned_container_id'], x.target_id)
        with self.assertRaises(Denied): x.adapter.start_target(intent.intent_uuid)

    def test_duplicate_submit_does_not_create_start_or_remove_again(self):
        x = self.x
        x.provision_live(); report = x.submit_live()
        counts = x.api.creates, x.api.starts, x.api.removes
        replay = x.runtime.submit(x.run_request, x.enrollment)
        self.assertEqual(replay, report)
        self.assertEqual((x.api.creates, x.api.starts, x.api.removes), counts)

    def test_identity_endpoint_and_extra_network_drift(self):
        for kind in ('started', 'restart', 'endpoint', 'ip', 'network', 'extra', 'paused', 'dead'):
            with self.subTest(kind=kind):
                x = LiveLab()
                try:
                    x.provision_live(); attrs = x.api.objects[x.target_id]
                    ep = next(iter(attrs['NetworkSettings']['Networks'].values()))
                    if kind == 'started': attrs['State']['StartedAt'] = '2026-10-19T10:00:01Z'
                    if kind == 'restart': attrs['RestartCount'] = 1
                    if kind == 'endpoint': ep['EndpointID'] = '8'*64
                    if kind == 'ip': ep['IPAddress'] = '172.30.0.8'
                    if kind == 'network': ep['NetworkID'] = '8'*64
                    if kind == 'extra': attrs['NetworkSettings']['Networks']['foreign'] = dict(ep)
                    if kind in ('paused', 'dead'): attrs['State'][kind.capitalize()] = True
                    report = x.submit_live()
                    self.assertEqual(report['terminal']['result'], 'unknown')
                    self.assertEqual(x.api.creates, 1)
                finally: x.close()

    def test_post_probe_target_restart_cannot_pass(self):
        x = self.x
        x.provision_live()
        original = x.api.logs
        def logs(*args, **kwargs):
            x.api.objects[x.target_id]['RestartCount'] = 1
            return original(*args, **kwargs)
        x.api.logs = logs
        x.api.http = packet(x.network.target_ipv4, 200, b'APP OK: customer service is running', True, 'none')
        self.assertEqual(x.submit_live()['terminal']['result'], 'unknown')

    def test_forged_or_incomplete_runner_protocol_is_unknown(self):
        x = self.x
        x.provision_live()
        x.api.http['result'] = 'passed'
        report = x.submit_live()
        self.assertEqual(report['terminal']['result'], 'unknown')
        self.assertEqual(report['cleanup'], 'confirmed')

    def test_http_timeout_redirect_wrong_body_semantics(self):
        x = self.x
        x.provision_live()
        for response, expected in ((packet(x.network.target_ipv4, transport='timeout'), 'unknown'),
                                  (packet(x.network.target_ipv4, 302, b'', True, 'none'), 'failed'),
                                  (packet(x.network.target_ipv4, 200, b'bad', True, 'none'), 'failed')):
            with self.subTest(expected=expected):
                x.api.http = response
                self.assertEqual(x.submit_live()['terminal']['result'], expected)

    def test_unconfirmed_active_egress_never_releases_probe(self):
        x = self.x
        x.provision_live(); x.validator.active_provider = None
        report = x.submit_live()
        self.assertEqual(report['terminal']['result'], 'unknown')
        self.assertFalse(x.api.released)
        self.assertNotIn('attach', x.api.calls)

    def test_foreign_installed_rule_no_runner_create(self):
        x = self.x
        x.provision_live()
        x.validator.reader.read = lambda: {'nftables': []}
        report = x.submit_live()
        self.assertEqual(report['terminal']['result'], 'unknown')
        self.assertEqual(x.api.creates, 1)

    def test_cleanup_requires_ownership_and_replay_is_idempotent(self):
        x = self.x
        x.authority.set_enabled(True)
        with self.assertRaises(Denied): x.cleanup_agent.confirm(uuid(), Resource.RUNNER)
        x.factory.assert_not_called()
        x.provision_live(); report = x.submit_live()
        before = x.api.removes
        self.assertEqual(x.cleanup_agent.confirm(report['id'], Resource.RUNNER), report)
        self.assertEqual(x.api.removes, before)

    def test_lost_remove_response_retains_pending_cleanup(self):
        x = self.x
        x.provision_live()
        with patch.object(x.api, 'remove_container', side_effect=TimeoutError('SECRET')):
            report = x.submit_live()
        self.assertEqual(report['cleanup'], 'pending')
        with self.assertRaises(Denied): x.submit_live()

    def test_rollback_after_disable_exact_target_cleanup(self):
        x = self.x
        enrollment = x.provision_live(); x.submit_live()
        result = x.runtime.rollback_target(enrollment)
        self.assertEqual(result['cleanup'], 'confirmed')
        self.assertEqual(x.api.objects, {})
        with self.assertRaises(Denied): x.adapter.approval()

    def test_recovery_needs_independent_trace_and_never_starts(self):
        x = self.x
        intent = self.issued_target()
        def lost(response): raise TimeoutError()
        x.api.raw_hook = lost
        with self.assertRaises(Denied): x.adapter.create(intent)
        with x.journal.transaction() as db:
            from trusted_checker_runtime.contracts import DispatchPermit
            permit = DispatchPermit(**{**x.journal.get(db, 'create_dispatch_target', intent.intent_uuid), 'resource': Resource.TARGET})
        trace = CreateTrace(uuid(), intent.intent_uuid, x.scope, x.clock(), Resource.TARGET, x.daemon,
            digest(body(intent)), x.target_id, intent.image_id, x.clock(), 'independent_daemon_create_event', '7'*64)
        recovery = OwnershipRecovery(x.adapter)
        with self.assertRaises(Denied): recovery.recover(permit, replace(x.sign(trace), signature='0'*64))
        report = recovery.recover(permit, x.sign(trace))
        self.assertEqual(report['owned_container_id'], x.target_id)
        self.assertEqual(report['phase'], 'quarantined')
        self.assertEqual(x.api.starts, 0)
        self.assertEqual(recovery.recover(permit, x.sign(trace)), report)

    def test_target_task_files_static_compatibility_and_no_edits(self):
        from pathlib import Path
        root = Path(__file__).resolve().parents[2]/'training_tasks/l1/service-bind-localhost'
        self.assertIn('CMD ["/start.sh"]', (root/'Dockerfile').read_text())
        script = (root/'files/customer-app').read_text()
        self.assertIn('mkdir -p "$(dirname "$PIDFILE")"', script)
        self.assertIn('nohup python3 /opt/customer-app/app_server.py', script)
        self.assertEqual(LIVE_TARGET.command, ('/start.sh',))
        self.assertFalse(LIVE_TARGET.read_only)
        self.assertEqual(LIVE_TARGET.user, '0:0')
        self.assertEqual({p for p, _ in LIVE_TARGET.tmpfs}, {'/tmp', '/run'})

    def test_concurrent_adapter_create_is_one_raw_invocation(self):
        x = self.x
        intent = self.issued_target()
        gate, original = Barrier(2), x.api.inspect_image
        def image(identifier):
            gate.wait(timeout=20)
            return original(identifier)
        x.api.inspect_image = image
        def create():
            try: return x.adapter.create(intent).payload.container_id
            except Denied: return 'denied'
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: create(), range(2)))
        self.assertCountEqual(results, [x.target_id, 'denied'])
        self.assertEqual(x.api.creates, 1)

    def test_final_output_change_or_nonzero_exit_prevents_pass(self):
        for kind in ('output', 'exit'):
            with self.subTest(kind=kind):
                x = LiveLab()
                try:
                    x.provision_live()
                    x.api.http = packet(x.network.target_ipv4, 200, b'APP OK: customer service is running', True, 'none')
                    if kind == 'exit':
                        x.api.wait = lambda *args, **kw: {'StatusCode': 1}
                    else:
                        original = x.api.logs
                        calls = []
                        def logs(*args, **kwargs):
                            calls.append(1)
                            return original(*args, **kwargs) if len(calls) == 1 else iter([b'{"result":"passed"}'])
                        x.api.logs = logs
                    self.assertEqual(x.submit_live()['terminal']['result'], 'unknown')
                finally:x.close()

    def test_live_and_offline_store_markers_cannot_be_mixed(self):
        from trusted_checker_runtime.journal import RuntimeJournal
        x = self.x
        before = x.journal.path.read_bytes()
        with self.assertRaises(Denied): RuntimeJournal(x.journal.path)
        self.assertEqual(x.journal.path.read_bytes(), before)
        offline = RuntimeJournal(x.journal.path.parent/'another.runtime.sqlite3')
        before = offline.path.read_bytes()
        with self.assertRaises(Denied): RuntimeJournal(offline.path, live=True)
        self.assertEqual(offline.path.read_bytes(), before)

    def test_target_build_copy_is_pinned_without_changing_task_source(self):
        from trusted_checker_live.artifacts import target_build_recipe
        text = target_build_recipe('ubuntu:22.04@sha256:'+'a'*64)
        self.assertTrue(text.startswith('FROM ubuntu:22.04@sha256:'))
        self.assertIn('COPY files/start.sh /start.sh', text)
        with self.assertRaises(Denied): target_build_recipe('ubuntu:22.04')
