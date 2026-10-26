from dataclasses import FrozenInstanceError, asdict, replace
import json

from trusted_checker_shadow.backend import FakeExecutionBackend
from trusted_checker_shadow.contracts import (CandidateMetadata, CreationProvenance, OperatorRequest,
                                             Rejected, RuntimeObservation, Verdict)
from trusted_checker_shadow.enrollment import FakeTrustedAuthority
from trusted_checker_shadow.policy import POLICY
from .support import ShadowCase


class ContractTests(ShadowCase):
    def test_policy_frozen_versioned_and_not_synthetic(self):
        self.assertEqual(POLICY.policy_id, "service-bind-localhost-peer-v1")
        self.assertEqual(len(POLICY.digest), 64)
        with self.assertRaises(FrozenInstanceError):
            POLICY.port = 6379
        for change in ({"port": 6379}, {"path": "/probe"}, {"version": True},
                       {"max_body_bytes": 999999}, {"http_timeout_seconds": 99.0},
                       {"criteria_scope": "full_task_legacy"}, {"execution_mode": "docker"}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                replace(POLICY, **change)

    def test_feature_flag_default_off_before_backend(self):
        with self.assertRaisesRegex(Rejected, "feature_disabled"):
            self.coordinator.submit(self.request(), self.enrollment)
        self.assertEqual((self.backend.issue_calls, self.backend.simulated_starts), (0, 0))

    def test_candidate_and_runtime_observations_cannot_be_enrollment(self):
        self.enabled()
        for obj in (CandidateMetadata(self.fixture.target, "inspect"),
                    RuntimeObservation(self.fixture.target), asdict(self.enrollment)):
            with self.subTest(type=type(obj)), self.assertRaisesRegex(Rejected, "verified_enrollment_required"):
                self.coordinator.submit(self.request(), obj)

    def test_labels_or_inspect_require_independent_explicit_fixture(self):
        empty = FakeTrustedAuthority("fake-empty", ())
        for source in ("labels", "inspect", "sandbox_metadata"):
            with self.subTest(source=source), self.assertRaisesRegex(Rejected, "provenance_fixture_mismatch"):
                empty.enroll(CandidateMetadata(self.fixture.target, source),
                    fixture_uuid=self.fixture.fixture_uuid, operator_id="operator-unit")

    def test_forged_enrollment_changes_are_rejected_before_issue(self):
        self.enabled()
        target = self.enrollment.target
        variants = [replace(self.enrollment, target=replace(target, **change)) for change in (
            {"attempt_id": 2}, {"owner_id": 18}, {"daemon_id": "fake-foreign"},
            {"container_id": "e" * 64}, {"image_id": "sha256:" + "f" * 64},
            {"generation": self.request().sample_slot}, {"runtime_binding_uuid": self.request().sample_slot},
            {"started_at": "2026-10-19T11:00:00+00:00"}, {"restart_count": 1},
            {"network_id": "f" * 64}, {"endpoint_id": "e" * 64}, {"ipv4": "172.29.1.3"},
            {"scope": "offline-other"})]
        variants += [replace(self.enrollment, provenance=CreationProvenance("fixture:forged", "e" * 64)),
                     replace(self.enrollment, operator_id="operator-other"),
                     replace(self.enrollment, authority_id="fake-forged")]
        for forged in variants:
            with self.subTest(forged=forged), self.assertRaises(Rejected):
                self.coordinator.submit(self.request(), forged)
        self.assertEqual(self.backend.issue_calls, 0)

    def test_missing_provenance_or_altered_policy_digest_rejected(self):
        for change in ({"provenance": None}, {"policy_digest": "f" * 64}, {"policy_version": True}):
            with self.subTest(change=change), self.assertRaises(Rejected):
                replace(self.enrollment, **change)
        with self.assertRaisesRegex(Rejected, "fake_provenance_required"):
            CreationProvenance("historical-container", "a" * 64)

    def test_request_foreign_attempt_owner_and_scope(self):
        self.enabled()
        for change in ({"attempt_id": 3}, {"owner_id": 99}, {"scope": "offline-other"}):
            with self.subTest(change=change), self.assertRaisesRegex(Rejected, "request_target_mismatch"):
                self.coordinator.submit(replace(self.request(), **change), self.enrollment)

    def test_strict_request_no_arbitrary_url_port_or_docker_parameters(self):
        payload = asdict(self.request())
        for name, value in (("url", "http://evil/"), ("port", 22), ("command", ["sh"]),
                            ("mounts", ["/var/run/docker.sock"]), ("network", "host"),
                            ("credentials", "private"), ("stdout", "private")):
            with self.subTest(name=name), self.assertRaises(TypeError):
                OperatorRequest(**{**payload, name: value})
        with self.assertRaisesRegex(Rejected, "request_schema_invalid"):
            self.coordinator.submit(payload, self.enrollment)

    def test_invalid_task_policy_uuid_deadline_and_ipv4(self):
        for change in ({"task": "l1/other"}, {"policy_digest": "f" * 64}, {"policy_version": 2},
                       {"schema_version": True}, {"request_uuid": "short"}, {"deadline": float("nan")},
                       {"deadline": float("inf")}, {"attempt_id": True}):
            with self.subTest(change=change), self.assertRaises(Rejected):
                replace(self.request(), **change)
        for ip in ("localhost", "127.0.0.1", "169.254.169.254", "8.8.8.8", "::1", "172.029.1.2", 123):
            with self.subTest(ip=ip), self.assertRaises(Rejected):
                replace(self.fixture.target, ipv4=ip)
        for daemon in ("production", "unix:///var/run/docker.sock"):
            with self.assertRaises(Rejected):
                replace(self.fixture.target, daemon_id=daemon)

    def test_deadline_expired_or_unbounded_rejected(self):
        self.enabled()
        for seconds in (0, -1, 100):
            with self.subTest(seconds=seconds), self.assertRaisesRegex(Rejected, "deadline_invalid"):
                self.coordinator.submit(replace(self.request(), deadline=self.clock()+seconds), self.enrollment)
        self.assertEqual(self.backend.issue_calls, 0)

    def test_authority_restarts_with_same_fixture_without_promoting_other_candidates(self):
        restarted = FakeTrustedAuthority("fake-authority", (self.fixture,))
        self.assertEqual(restarted.verify(self.enrollment, operator_id="operator-unit"), self.enrollment)
        with self.assertRaisesRegex(Rejected, "operator_not_authorized"):
            restarted.verify(self.enrollment, operator_id="operator-other")

    def test_non_fake_backend_or_authority_not_accepted(self):
        for kwargs in ({"backend": object()}, {"authority": object()}):
            with self.subTest(kwargs=kwargs), self.assertRaises(Rejected):
                self.make_coordinator(**kwargs)
        class Subclass(FakeExecutionBackend):
            pass
        with self.assertRaisesRegex(Rejected, "fake_backend_required"):
            self.make_coordinator(backend=Subclass())

    def test_report_has_scope_policy_digest_and_no_full_success_claim(self):
        report = self.enabled().submit(self.request(), self.enrollment)
        data = report.to_dict()
        self.assertEqual(report.verdict.result, Verdict.PASSED)
        for key, expected in (("criteria_scope", "external_ipv4_http_only"), ("local_access", "unverified"),
                              ("application_authenticity", "unproven"), ("persistence", "unverified"),
                              ("execution_mode", "offline_fake_only"), ("policy_digest", POLICY.digest)):
            self.assertEqual(data[key], expected)
        self.assertNotIn("technical_passed", json.dumps(data))
        self.assertLess(len(json.dumps(data)), 16384)
