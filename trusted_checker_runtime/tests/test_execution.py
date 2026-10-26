from dataclasses import replace
from unittest import TestCase

from trusted_checker_runtime.contracts import Endpoint, OrdinaryMetadata, Phase, Resource, RunRequest
from trusted_checker_runtime.profiles import Denied
from .support import Lab, uuid


class ExecutionTests(TestCase):
    def setUp(self):
        self.x = Lab()
        self.addCleanup(self.x.close)
        self.a = self.x.authority

    def test_full_chain_scoped_pass_and_separate_cleanup(self):
        x = self.x
        x.enrolled(); x.running()
        terminal = x.finish()
        self.assertEqual(terminal['result'], 'passed')
        self.assertEqual(terminal['criteria_scope'], 'external_ipv4_http_only')
        self.assertEqual(terminal['application_authenticity'], 'unproven')
        self.assertFalse(terminal['continuous_attestation'])
        self.assertEqual(self.a.report(x.run)['cleanup'], 'pending')
        self.a.record_cleanup(x.cleanup())
        self.assertEqual(self.a.report(x.run)['cleanup'], 'confirmed')
        self.assertEqual(self.a.publish(x.run), terminal)
        self.assertEqual((x.creates, x.starts), (2, 2))  # Only fixture counters.

    def test_wrong_response_is_failed_and_timeout_unknown(self):
        for changes, expected in (({'status': 302}, 'failed'), ({'body': b'bad'}, 'failed'),
                                  ({'body': b'x'*1025}, 'failed'), ({'complete': False}, 'unknown'),
                                  ({'transport': 'timeout'}, 'unknown')):
            with self.subTest(changes=changes):
                x = Lab()
                try:
                    x.enrolled(); x.running()
                    self.assertEqual(x.finish(**changes)['result'], expected)
                finally:
                    x.close()

    def test_every_identity_dimension_drift_blocks_publication(self):
        x = self.x
        x.enrolled()
        changes = [dict(container_id='7'*64), dict(image_id='sha256:'+'7'*64),
                   dict(started_at='2026-10-19T10:00:01Z'), dict(restart_count=1),
                   dict(runtime_binding_uuid=uuid()), dict(generation_uuid=uuid()),
                   dict(attempt=replace(x.attempt, owner_id=8)), dict(attempt=replace(x.attempt, attempt_id=42)),
                   dict(daemon=replace(x.daemon, session_uuid=uuid())), dict(daemon=replace(x.daemon, daemon_id='other')),
                   dict(daemon=replace(x.daemon, endpoint_reference='endpoint:other')),
                   dict(endpoints=(replace(x.target_endpoint, endpoint_id='8'*64),)),
                   dict(endpoints=(replace(x.target_endpoint, ipv4='172.30.0.8'),)),
                   dict(endpoints=(replace(x.target_endpoint, network_id='8'*64),)),
                   dict(endpoints=(x.target_endpoint, replace(x.target_endpoint, endpoint_id='8'*64))),
                   dict(running=False), dict(paused=True), dict(restarting=True), dict(dead=True),
                   dict(config=replace(x.target.config, network_count=2)),
                   dict(config=replace(x.target.config, docker_socket=True))]
        for change in changes:
            with self.subTest(change=change):
                x.reserve()
                with self.assertRaises(Denied):
                    self.a.check_target(x.run, Phase.BEFORE_CREATE,
                        *x.bundle(x.run, Phase.BEFORE_CREATE, target=replace(x.target, **change)))
                self.assertEqual(self.a.publish(x.run)['result'], 'unknown')
        self.assertEqual(x.creates, 1)

    def test_invalid_initial_target_identity_cannot_enroll(self):
        x = self.x
        intent = x.owned_target()
        for change in (dict(restart_count=1), dict(started_at='2026-10-18T10:00:00Z'),
                       dict(image_id=x.approval.runner_image_id), dict(running=False), dict(paused=True),
                       dict(config=replace(x.target.config, host_mounts=1)),
                       dict(endpoints=(replace(x.target_endpoint, network_id='8'*64),))):
            with self.subTest(change=change), self.assertRaises(Denied):
                self.a.verify_provision(intent.intent_uuid, *x.bundle(intent.intent_uuid, Phase.ENROLL, target=replace(x.target, **change)))
        with self.assertRaises(Denied):
            self.a.enroll(intent.intent_uuid)

    def test_internal_network_without_independent_validation_is_not_enough(self):
        x = self.x
        intent = x.owned_target()
        identity, network, egress, validation = x.bundle(intent.intent_uuid, Phase.ENROLL)
        with self.assertRaises(Denied):
            self.a.verify_provision(intent.intent_uuid, identity, network, egress,
                x.sign(replace(validation.payload, passed_cases=('allow_target_8080',))))
        with self.assertRaises(Denied):
            self.a.enroll(intent.intent_uuid)

    def test_network_egress_and_independent_receipt_binding(self):
        x = self.x
        x.owned_target()
        bundle = x.bundle(x.intent.intent_uuid, Phase.ENROLL)
        altered = [(1, {'internal': False}), (1, {'driver': 'host'}), (1, {'network_profile_digest': '0'*64}),
                   (1, {'endpoints': (x.target_endpoint, x.runner_endpoint)}),
                   (2, {'default_deny': False}), (2, {'only_target_8080': False}),
                   (2, {'denies_host_metadata_platform': False}), (2, {'anti_spoofing': False}),
                   (2, {'rules_digest': '0'*64}), (2, {'runner_id': x.runner_id}),
                   (3, {'enforcement_receipt_digest': '0'*64}), (3, {'matrix_digest': '0'*64})]
        for index, changes in altered:
            test_bundle = list(bundle)
            test_bundle[index] = x.sign(replace(test_bundle[index].payload, **changes))
            with self.subTest(changes=changes), self.assertRaises(Denied):
                self.a.verify_provision(x.intent.intent_uuid, *test_bundle)
        with self.assertRaises(Denied):
            self.a.verify_provision(x.intent.intent_uuid, *bundle[:3], bundle[2])  # Enforcer cannot be validator.

    def test_forged_enrollment_and_foreign_attempt_rejected(self):
        x = self.x
        x.enrolled()
        for enrollment in (replace(x.enrollment, enrollment_uuid=uuid()),
                           replace(x.enrollment, scope='test-shadow-foreign')):
            with self.subTest(enrollment=enrollment.enrollment_uuid), self.assertRaises(Denied):
                self.a.reserve_run(RunRequest(uuid(), enrollment.enrollment_uuid, x.attempt, uuid()), enrollment)
        for attempt in (replace(x.attempt, owner_id=8), replace(x.attempt, attempt_id=42)):
            with self.subTest(attempt=attempt), self.assertRaises(Denied):
                self.a.reserve_run(RunRequest(uuid(), x.enrollment.enrollment_uuid, attempt, uuid()), x.enrollment)

    def test_duplicate_run_and_canonical_sample_mapping(self):
        x = self.x
        x.enrolled(); x.reserve()
        self.assertEqual(x.new_authority().reserve_run(x.run_request, x.enrollment), x.run)
        self.assertEqual(self.a.reserve_run(replace(x.run_request, request_uuid=uuid()), x.enrollment), x.run)
        with self.assertRaises(Denied):
            self.a.reserve_run(replace(x.run_request, sample_slot=uuid()), x.enrollment)

    def test_ordinary_claim_cannot_grant_same_generation_proven(self):
        x = self.x
        x.enrolled()
        ordinary = OrdinaryMetadata(x.attempt, 13, uuid(), 'passed', x.clock(), x.target.runtime_binding_uuid)
        x.reserve(ordinary)
        report = self.a.report(x.run)
        self.assertEqual(report['correlation_quality'], 'same_attempt_temporal')
        self.assertEqual(report['comparison'], 'incomparable')
        self.assertEqual(report['runtime_enrollment_uuid'], x.enrollment.enrollment_uuid)
        self.assertEqual(report['ordinary_execution_uuid'], ordinary.execution_uuid)
        with self.assertRaises(TypeError):
            OrdinaryMetadata(x.attempt, 13, uuid(), 'passed', x.clock(), correlation_quality='same_generation_proven')

    def test_other_ordinary_binding_is_explicit_mismatch(self):
        x = self.x
        x.enrolled()
        x.reserve(OrdinaryMetadata(x.attempt, None, uuid(), 'unknown', None, uuid()))
        self.assertEqual(self.a.report(x.run)['correlation_quality'], 'generation_mismatch')

    def test_kill_prevents_create_and_epoch_reenable_cannot_revive_run(self):
        x = self.x
        x.enrolled(); x.reserve()
        self.a.check_target(x.run, Phase.BEFORE_CREATE, *x.bundle(x.run, Phase.BEFORE_CREATE))
        self.a.kill(); self.a.set_enabled(True)
        with self.assertRaisesRegex(Denied, 'epoch_changed'):
            self.a.begin_create(x.run_intent(), x.daemon_receipt(x.run))
        self.a.expire_run(x.run)
        self.assertEqual(self.a.publish(x.run)['result'], 'unknown')
        self.assertEqual(x.creates, 1)

    def test_kill_prevents_authorized_start(self):
        x = self.x
        x.enrolled(); x.start_ready()
        self.a.kill()
        with self.assertRaises(Denied):
            with self.a.start_fence(x.start_permit):
                self.fail('cancelled start')
        self.a.expire_run(x.run)
        self.a.record_cleanup(x.cleanup())
        self.assertEqual(self.a.report(x.run)['cleanup'], 'confirmed')
        self.assertEqual(self.a.publish(x.run)['result'], 'unknown')

    def test_start_crash_keeps_consumed_intent(self):
        x = self.x
        x.enrolled(); x.start_ready()
        with self.assertRaisesRegex(RuntimeError, 'simulated'):
            with self.a.start_fence(x.start_permit):
                x.starts += 1
                raise RuntimeError('simulated process loss')
        with self.assertRaises(Denied):
            with x.new_authority().start_fence(x.start_permit):
                self.fail('second start')
        self.assertEqual(self.a.report(x.run)['phase'], 'start_requested')
        self.assertEqual(x.starts, 2)

    def test_create_crash_keeps_consumed_dispatch(self):
        x = self.x
        x.enrolled(); x.reserve()
        self.a.check_target(x.run, Phase.BEFORE_CREATE, *x.bundle(x.run, Phase.BEFORE_CREATE))
        permit = self.a.begin_create(x.run_intent(), x.daemon_receipt(x.run))
        with self.assertRaises(RuntimeError):
            with self.a.create_fence(permit):
                raise RuntimeError('simulated loss')
        with self.assertRaises(Denied):
            with x.new_authority().create_fence(permit):
                self.fail('second create')
        self.a.abandon_run(x.run)
        self.assertEqual(self.a.report(x.run)['cleanup'], 'quarantined')

    def test_late_runner_ownership_does_not_rewrite_terminal(self):
        x = self.x
        x.enrolled(); x.reserve()
        self.a.check_target(x.run, Phase.BEFORE_CREATE, *x.bundle(x.run, Phase.BEFORE_CREATE))
        intent = x.run_intent(); permit = x.dispatch(intent)
        signed = x.response(intent, permit)
        x.clock.advance(9); self.a.expire_run(x.run)
        original = self.a.publish(x.run)
        self.a.record_create_response(permit, signed)
        self.assertEqual(self.a.publish(x.run), original)
        self.assertEqual(self.a.report(x.run)['cleanup'], 'pending')
        self.a.kill(); self.a.record_cleanup(x.cleanup())
        self.assertEqual(self.a.publish(x.run), original)

    def test_stale_observation_cannot_authorize_create(self):
        x = self.x
        x.enrolled(); x.reserve()
        self.a.check_target(x.run, Phase.BEFORE_CREATE, *x.bundle(x.run, Phase.BEFORE_CREATE))
        x.clock.advance(3.1)
        with self.assertRaisesRegex(Denied, 'stale'):
            self.a.begin_create(x.run_intent(), x.daemon_receipt(x.run))

    def test_deadline_on_boundary_refuses_start(self):
        x = self.x
        x.enrolled(); x.start_ready()
        x.clock.advance(8)
        with self.assertRaisesRegex(Denied, 'deadline'):
            with self.a.start_fence(x.start_permit):
                self.fail('late start')

    def test_runner_hardening_profile_checked_before_start(self):
        x = self.x
        from trusted_checker_runtime.contracts import expected_config
        config = expected_config(x.approval, Resource.RUNNER)
        for changes in ({'user': '0:0'}, {'read_only': False}, {'privileged': True}, {'cap_drop': ()},
                        {'cap_add': ('NET_ADMIN',)}, {'no_new_privileges': False}, {'pid_mode': 'host'},
                        {'ipc_mode': 'host'}, {'host_mounts': 1}, {'docker_socket': True},
                        {'tmpfs_digest': '0'*64}, {'entrypoint_digest': '0'*64},
                        {'cpu_nanos': 999999999}, {'memory': 999999999}, {'pids': 999},
                        {'network_count': 2}, {'network_mode': '8'*64}, {'log_limit_bytes': 999999},
                        {'output_limit_bytes': 99999}, {'environment_digest': '8'*64}, {'log_files': 3}):
            with self.subTest(changes=changes):
                fixture = Lab()
                try:
                    fixture.enrolled(); fixture.owned_runner()
                    with self.assertRaises(Denied):
                        fixture.authority.check_target(fixture.run, Phase.BEFORE_START,
                            *fixture.bundle(fixture.run, Phase.BEFORE_START),
                            runner=fixture.runner(config=replace(config, **changes)))
                    self.assertEqual(fixture.authority.publish(fixture.run)['result'], 'unknown')
                finally:
                    fixture.close()

    def test_runner_must_have_observed_live_endpoint(self):
        x = self.x
        x.enrolled(); x.start_ready()
        with self.a.start_fence(x.start_permit):
            pass
        x.runner_started_at = x.clock.docker()
        for state, endpoint in (('exited', None), ('running', None)):
            with self.subTest(state=state), self.assertRaises(Denied):
                self.a.record_runner_live(x.run, x.runner(state, endpoint=endpoint))
        with self.assertRaises(Denied):
            self.a.record_probe(x.run, x.probe())

    def test_runner_restart_and_endpoint_change_after_probe_is_unknown(self):
        for changes in ({'restart_count': 1}, {'started_at': '2026-10-19T10:00:01Z'},
                        {'endpoint': Endpoint('e'*64, 'c'*64, '8'*64, '172.30.0.3')},
                        {'paused': True}, {'restarting': True}, {'dead': True}):
            with self.subTest(changes=changes):
                x = Lab()
                try:
                    x.enrolled(); x.running(); x.authority.record_probe(x.run, x.probe())
                    with self.assertRaises(Denied):
                        x.authority.check_target(x.run, Phase.AFTER_PROBE,
                            *x.bundle(x.run, Phase.AFTER_PROBE, runner_endpoint=x.runner_endpoint),
                            runner=x.runner('running', **changes))
                    self.assertEqual(x.authority.publish(x.run)['result'], 'unknown')
                finally:
                    x.close()

    def test_target_drift_is_rechecked_in_each_execution_phase(self):
        for phase in (Phase.BEFORE_START, Phase.AFTER_PROBE, Phase.BEFORE_PUBLISH):
            with self.subTest(phase=phase):
                x = Lab()
                try:
                    x.enrolled()
                    if phase == Phase.BEFORE_START:
                        x.owned_runner(); runner = x.runner(); endpoint = None
                    else:
                        x.running(); x.authority.record_probe(x.run, x.probe())
                        runner = x.runner('running'); endpoint = x.runner_endpoint
                        if phase == Phase.BEFORE_PUBLISH:
                            x.authority.check_target(x.run, Phase.AFTER_PROBE,
                                *x.bundle(x.run, Phase.AFTER_PROBE, runner_endpoint=endpoint), runner=runner)
                            runner = x.runner('running')
                    with self.assertRaises(Denied):
                        x.authority.check_target(x.run, phase, *x.bundle(x.run, phase,
                            target=replace(x.target, restart_count=1), runner_endpoint=endpoint), runner=runner)
                    self.assertEqual(x.authority.publish(x.run)['result'], 'unknown')
                finally:
                    x.close()

    def test_missing_post_or_publication_checks_cannot_pass(self):
        x = self.x
        x.enrolled(); x.running(); self.a.record_probe(x.run, x.probe())
        self.assertEqual(self.a.publish(x.run)['result'], 'unknown')

    def test_replay_and_late_pass_cannot_change_unknown(self):
        x = self.x
        x.enrolled(); x.running()
        original = self.a.abandon_run(x.run)
        with self.assertRaises(Denied):
            self.a.record_probe(x.run, x.probe())
        self.assertEqual(self.a.publish(x.run), original)
        self.a.record_cleanup(x.cleanup())
        self.assertEqual(self.a.publish(x.run), original)

    def test_pending_cleanup_blocks_even_a_new_sample(self):
        x = self.x
        x.enrolled(); x.running(); x.finish()
        with self.assertRaisesRegex(Denied, 'circuit_open'):
            x.reserve()
        self.a.record_cleanup(x.cleanup())
        x.reserve()
        self.assertEqual(self.a.report(x.run)['phase'], 'reserved')

    def test_cleanup_foreign_id_ownership_daemon_or_unknown_rejected(self):
        x = self.x
        x.enrolled(); x.running(); x.finish()
        receipt = x.cleanup().payload
        for changes in ({'container_id': x.target_id}, {'ownership_digest': '0'*64}, {'outcome': 'unknown'},
                        {'daemon': replace(x.daemon, session_uuid=uuid())}):
            with self.subTest(changes=changes), self.assertRaises(Denied):
                self.a.record_cleanup(x.sign(replace(receipt, **changes)))
        self.assertEqual(self.a.report(x.run)['cleanup'], 'pending')

    def test_clock_rollback_fails_closed(self):
        x = self.x
        x.enrolled(); x.reserve()
        x.clock.advance(-1)
        with self.assertRaisesRegex(Denied, 'clock_rollback'):
            self.a.begin_create(x.run_intent(), x.daemon_receipt(x.run))

    def test_wrong_probe_identity_cannot_be_retried_into_pass(self):
        x = self.x
        x.enrolled(); x.running()
        with self.assertRaises(Denied):
            self.a.record_probe(x.run, x.probe(checker_source_digest='0'*64))
        with self.assertRaises(Denied):
            self.a.record_probe(x.run, x.probe())
        self.assertEqual(self.a.publish(x.run)['result'], 'unknown')

    def test_initial_runner_started_at_must_be_inside_issued_run_window(self):
        x = self.x
        x.enrolled(); x.start_ready()
        with self.a.start_fence(x.start_permit):
            pass
        x.runner_started_at = '2026-10-18T10:00:00Z'
        with self.assertRaisesRegex(Denied, 'runner_start_time_unconfirmed'):
            self.a.record_runner_live(x.run, x.runner('running'))
        self.assertEqual(self.a.publish(x.run)['result'], 'unknown')

    def test_kill_between_positive_probe_and_publication_preserves_unknown(self):
        x = self.x
        x.enrolled(); x.running(); self.a.record_probe(x.run, x.probe())
        for phase in (Phase.AFTER_PROBE, Phase.BEFORE_PUBLISH):
            self.a.check_target(x.run, phase, *x.bundle(x.run, phase, runner_endpoint=x.runner_endpoint),
                                runner=x.runner('running'))
        self.a.kill()
        unknown = self.a.publish(x.run)
        self.assertEqual(unknown['result'], 'unknown')
        self.a.set_enabled(True)
        self.assertEqual(self.a.publish(x.run), unknown)
