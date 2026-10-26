from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from unittest import TestCase
from unittest.mock import patch

from trusted_checker_runtime.attestation import Attestation, ReceiptVerifier
from trusted_checker_runtime.boundary import capture_create_response
from trusted_checker_runtime.contracts import ProvisionRequest, Resource, RunRequest
from trusted_checker_runtime.profiles import Denied
from .support import Lab, uuid


class ProvenanceTests(TestCase):
    def setUp(self):
        self.lab = Lab()
        self.addCleanup(self.lab.close)
        self.a = self.lab.authority

    def test_default_off_before_provision(self):
        x = self.lab
        with self.assertRaisesRegex(Denied, 'feature_disabled'):
            self.a.provision(ProvisionRequest(uuid(), x.approval.approval_uuid, x.attempt))
        self.assertEqual(x.creates, 0)

    def test_forged_approval_is_not_a_digest_authorization(self):
        x = self.lab
        forged = Attestation(x.approval, 'operator:unit', x.approval.digest)
        with self.assertRaisesRegex(Denied, 'signature_invalid'):
            self.a.register_approval(forged)

    def test_expired_approval(self):
        x = self.lab
        old = replace(x.approval, approval_uuid=uuid(), created_at=x.clock()-60, expires_at=x.clock())
        with self.assertRaisesRegex(Denied, 'expired'):
            self.a.register_approval(x.sign(old))

    def test_wrong_daemon_or_endpoint_approval(self):
        x = self.lab
        for changes in ({'daemon_id': 'other'}, {'endpoint_reference': 'endpoint:other'},
                        {'endpoint_config_digest': '8'*64}, {'session_uuid': uuid()}):
            with self.subTest(changes=changes), self.assertRaisesRegex(Denied, 'deployment_mismatch'):
                self.a.register_approval(x.sign(replace(x.approval, approval_uuid=uuid(), daemon=replace(x.daemon, **changes))))

    def test_unsigned_or_unknown_signer(self):
        x = self.lab
        for signed in (x.approval, replace(x.sign(x.approval), signer='operator:foreign')):
            with self.subTest(signed=type(signed)), self.assertRaises(Denied):
                self.a.register_approval(signed)

    def test_signer_scope_and_key_separation(self):
        x = self.lab
        with self.assertRaisesRegex(Denied, 'key_separation'):
            ReceiptVerifier((x.grants[0], replace(x.grants[1], key=x.grants[0].key)))
        with self.assertRaises(Denied):
            self.a.register_approval(x.sign(replace(x.approval, scope='staging-shadow-foreign')))

    def test_production_and_platform_network_rejected(self):
        x = self.lab
        for scope in ('production', 'prod-shadow-x', 'test-shadow-production', 'live', 'poc-unit'):
            with self.subTest(scope=scope), self.assertRaises(Denied):
                replace(x.approval, scope=scope)
        for name in ('training-platform-runtime', 'bridge', 'host'):
            with self.subTest(name=name), self.assertRaises(Denied):
                replace(x.network, network_name=name)

    def test_policy_images_profiles_and_limits_are_closed(self):
        x = self.lab
        for changes in ({'policy_digest': '0'*64}, {'policy_id': 'synthetic'}, {'policy_version': True},
                        {'runner_image_id': 'latest'}, {'target_image_id': 'sha256:short'},
                        {'target_profile_digest': '0'*64}, {'authority_mode': 'live'}, {'schema_version': True}):
            with self.subTest(changes=changes), self.assertRaises(Denied):
                replace(x.approval, **changes)
        for changes in ({'internal': False}, {'driver': 'host'}, {'dedicated_daemon': False},
                        {'target_port': 80}, {'default_egress': 'allow'}, {'runner_ipv4': x.network.target_ipv4}):
            with self.subTest(changes=changes), self.assertRaises(Denied):
                replace(x.network, **changes)

    def test_duplicate_provision_is_same_intent_after_restart(self):
        x = self.lab
        intent = x.provision()
        self.assertEqual(self.a.provision(x.request), intent)
        self.assertEqual(x.new_authority().provision(replace(x.request, request_uuid=uuid())), intent)
        self.assertEqual(x.creates, 0)

    def test_concurrent_provision_is_one_persisted_mapping(self):
        x = self.lab
        self.a.set_enabled(True)
        requests = [ProvisionRequest(uuid(), x.approval.approval_uuid, x.attempt) for _ in range(8)]
        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(lambda r: x.new_authority().provision(r), requests))
        self.assertEqual(len({r.intent_uuid for r in results}), 1)
        with x.journal.transaction() as db:
            self.assertEqual(db.execute("SELECT count(*) FROM rt_objects").fetchone()[0], 1)

    def test_foreign_owner_same_attempt_cannot_rebind(self):
        x = self.lab
        x.provision()
        with self.assertRaisesRegex(Denied, 'binding_conflict'):
            self.a.provision(replace(x.request, request_uuid=uuid(), attempt=replace(x.attempt, owner_id=8)))

    def test_create_checks_daemon_endpoint_and_session(self):
        x = self.lab
        intent = x.provision()
        for changes in ({'daemon_id': 'other'}, {'endpoint_reference': 'endpoint:other'}, {'session_uuid': uuid()}):
            with self.subTest(changes=changes), self.assertRaises(Denied):
                self.a.begin_create(intent, x.daemon_receipt(intent.intent_uuid, **changes))
        self.assertEqual(self.a.report(intent.intent_uuid, Resource.TARGET)['phase'], 'intent_recorded')

    def test_forged_create_receipt_never_records_ownership(self):
        x = self.lab
        intent = x.provision(); permit = x.dispatch(intent)
        signed = x.response(intent, permit)
        with self.assertRaises(Denied):
            self.a.record_create_response(permit, replace(signed, signature='0'*64))
        report = self.a.report(intent.intent_uuid, Resource.TARGET)
        self.assertIsNone(report['owned_container_id'])
        self.assertEqual(report['phase'], 'create_requested')

    def test_create_receipt_must_match_exact_issued_intent(self):
        x = self.lab
        intent = x.provision(); permit = x.dispatch(intent)
        response = x.response(intent, permit).payload
        for changes in ({'image_id': x.approval.runner_image_id}, {'permit_uuid': uuid()},
                        {'intent_digest': '0'*64}, {'resource': Resource.RUNNER}, {'context_uuid': uuid()},
                        {'daemon': replace(x.daemon, endpoint_reference='endpoint:foreign')}):
            with self.subTest(changes=changes), self.assertRaises(Denied):
                self.a.record_create_response(permit, x.sign(replace(response, **changes)))
        self.assertIsNone(self.a.report(intent.intent_uuid, Resource.TARGET)['owned_container_id'])

    def test_lost_create_response_blocks_retry_and_other_attempt(self):
        x = self.lab
        intent = x.provision(); permit = x.dispatch(intent)
        with self.assertRaises(Denied):
            with x.new_authority().create_fence(permit):
                self.fail('second create')
        with self.assertRaisesRegex(Denied, 'circuit_open'):
            self.a.provision(replace(x.request, request_uuid=uuid(), attempt=replace(x.attempt, attempt_id=42)))
        self.assertEqual(x.creates, 1)
        with self.assertRaises(Denied):
            self.a.enroll(intent.intent_uuid)

    def test_create_response_without_dispatch_provenance_rejected(self):
        x = self.lab
        intent = x.provision()
        permit = self.a.begin_create(intent, x.daemon_receipt(intent.intent_uuid))
        with self.assertRaises(Denied):
            self.a.record_create_response(permit, x.response(intent, permit))

    def test_ownership_persistence_failure_does_not_allow_second_create(self):
        x = self.lab
        intent = x.provision(); permit = x.dispatch(intent)
        with patch.object(x.journal, 'ownership', side_effect=OSError('SECRET')):
            with self.assertRaisesRegex(Denied, '^ownership_persistence_unconfirmed$'):
                self.a.record_create_response(permit, x.response(intent, permit))
        self.assertEqual(self.a.report(intent.intent_uuid, Resource.TARGET)['phase'], 'create_requested')
        with self.assertRaises(Denied):
            with self.a.create_fence(permit):
                self.fail('retry')

    def test_late_id_after_deadline_is_owned_but_never_enrolled(self):
        x = self.lab
        intent = x.provision(); permit = x.dispatch(intent)
        signed = x.response(intent, permit)
        x.clock.advance(9)
        self.a.record_create_response(permit, signed)
        report = self.a.report(intent.intent_uuid, Resource.TARGET)
        self.assertEqual((report['phase'], report['cleanup'], report['owned_container_id']), ('quarantined', 'pending', x.target_id))
        with self.assertRaises(Denied):
            self.a.enroll(intent.intent_uuid)

    def test_kill_during_create_late_ownership_only(self):
        x = self.lab
        intent = x.provision(); permit = x.dispatch(intent)
        self.a.kill()
        self.a.record_create_response(permit, x.response(intent, permit))
        self.assertEqual(self.a.report(intent.intent_uuid, Resource.TARGET)['phase'], 'quarantined')
        with self.assertRaises(Denied):
            with self.a.target_start_fence(intent.intent_uuid, x.daemon_receipt(intent.intent_uuid)):
                self.fail('start after kill')
        self.a.record_cleanup(x.cleanup(Resource.TARGET))
        self.assertEqual(self.a.report(intent.intent_uuid, Resource.TARGET)['cleanup'], 'confirmed')

    def test_owner_receipt_is_immutable_and_idempotent(self):
        x = self.lab
        intent = x.owned_target()
        self.assertEqual(self.a.record_create_response(x.target_permit, x.target_response), x.target_id)
        changed = x.sign(replace(x.target_response.payload, receipt_uuid=uuid(), container_id='7'*64))
        with self.assertRaisesRegex(Denied, 'ownership_conflict'):
            self.a.record_create_response(x.target_permit, changed)

    def test_existing_id_labels_candidate_not_enrollment(self):
        x = self.lab
        for value in ({'container_id': x.target_id, 'labels': {'trusted': True}}, x.target_id):
            with self.subTest(value=value), self.assertRaises(Denied):
                self.a.provision(value)
        x.provision()
        with self.assertRaises(Denied):
            self.a.enroll(x.intent.intent_uuid)

    def test_initial_target_start_must_have_durable_intent(self):
        x = self.lab
        intent = x.owned_target()
        with self.assertRaises(Denied):
            with self.a.target_start_fence(intent.intent_uuid, x.daemon_receipt(intent.intent_uuid)):
                self.fail('second target start')

    def test_verified_enrollment_survives_authority_restart(self):
        x = self.lab
        enrollment = x.enrolled()
        self.assertEqual(x.new_authority().enroll(x.intent.intent_uuid), enrollment)
        report = self.a.report(x.intent.intent_uuid, Resource.TARGET)
        self.assertEqual(report['sandbox_task_ownership'], 'not_claimed')
        self.assertEqual(report['phase'], 'enrolled')

    def test_new_daemon_session_requires_new_approval(self):
        x = self.lab
        x.enrolled()
        restarted = x.new_authority(replace(x.daemon, session_uuid=uuid()))
        request = RunRequest(uuid(), x.enrollment.enrollment_uuid, x.attempt, uuid())
        with self.assertRaisesRegex(Denied, 'daemon_mismatch'):
            restarted.reserve_run(request, x.enrollment)

    def test_approval_and_binding_revocation(self):
        x = self.lab
        x.enrolled()
        self.a.revoke_binding(x.enrollment)
        with self.assertRaises(Denied):
            x.reserve()
        self.a.revoke_approval(x.approval.approval_uuid)
        with self.assertRaises(Denied):
            self.a.register_approval(x.sign(x.approval))

    def test_raw_response_capture_rejects_short_id_fallback_and_arbitrary_keys(self):
        x = self.lab
        intent = x.provision(); permit = x.dispatch(intent)
        for raw in (None, [], {'Id': 'short'}, {'id': x.target_id}, {'Name': x.target_id},
                    {'Id': x.target_id, 'labels': {'owned': True}}, {'Id': x.target_id, 'Warnings': 'secret'}):
            with self.subTest(raw=type(raw)), self.assertRaises(Denied):
                capture_create_response(intent, permit, raw, daemon=x.daemon, receipt_uuid=uuid(), observed_at=x.clock())
        captured = capture_create_response(intent, permit, {'Id': x.target_id, 'Warnings': ['untrusted discarded']},
                                          daemon=x.daemon, receipt_uuid=uuid(), observed_at=x.clock())
        self.assertEqual(captured.container_id, x.target_id)
        self.assertNotIn('untrusted', repr(captured))
