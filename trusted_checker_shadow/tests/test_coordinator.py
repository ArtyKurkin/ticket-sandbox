from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from dataclasses import replace
import json
import sqlite3
import threading
from unittest.mock import patch
from uuid import uuid4

from trusted_checker_shadow.backend import (ExecutionReceipt, FakeExecutionBackend,
                                           FakeScenario, IssueFault)
from trusted_checker_shadow.contracts import Reason, Rejected, Verdict
from trusted_checker_shadow.predicate import FakeTransport, TransportFault
from trusted_checker_shadow.state import ShadowStore
from .support import ShadowCase, fixture


class CoordinatorTests(ShadowCase):
    def test_duplicate_completed_and_alias_return_same_run(self):
        self.enabled()
        request = self.request()
        first = self.coordinator.submit(request, self.enrollment)
        second = self.coordinator.submit(request, self.enrollment)
        alias = self.coordinator.submit(replace(request, request_uuid=str(uuid4())), self.enrollment)
        self.assertEqual(first, second)
        self.assertEqual(first, alias)
        self.assertEqual((self.backend.issue_calls, self.backend.simulated_creates, self.backend.simulated_starts), (1, 1, 1))

    def test_request_and_canonical_conflicting_payload(self):
        self.enabled()
        request = self.request()
        self.coordinator.submit(request, self.enrollment)
        with self.assertRaisesRegex(Rejected, "request_payload_conflict"):
            self.coordinator.submit(replace(request, sample_slot=str(uuid4())), self.enrollment)
        with self.assertRaisesRegex(Rejected, "canonical_payload_conflict"):
            self.coordinator.submit(replace(request, request_uuid=str(uuid4()), deadline=request.deadline-1), self.enrollment)
        self.assertEqual(self.backend.simulated_starts, 1)

    def test_deliberate_resample_has_new_slot_and_preserves_history(self):
        self.enabled()
        request = self.request()
        first = self.coordinator.submit(request, self.enrollment)
        second = self.coordinator.submit(self.request(), self.enrollment)
        self.assertNotEqual(first.shadow_run_uuid, second.shadow_run_uuid)
        self.assertNotEqual(first.canonical_idempotency_key, second.canonical_idempotency_key)
        self.assertEqual(self.coordinator.report(first.shadow_run_uuid), first)
        self.assertEqual(self.backend.simulated_starts, 2)

    def test_restart_coordinator_or_lost_submit_response_does_not_reissue(self):
        self.enabled()
        request = self.request()
        first = self.coordinator.submit(request, self.enrollment)
        backend = FakeExecutionBackend()
        restarted = self.make_coordinator(store=ShadowStore(self.path), backend=backend)
        self.assertEqual(restarted.submit(request, self.enrollment), first)
        self.assertEqual((backend.issue_calls, backend.simulated_starts), (0, 0))

    def test_concurrent_duplicate_uses_one_issue_and_start(self):
        self.enabled()
        request = self.request()
        self.backend.observation_release = threading.Event()
        with ThreadPoolExecutor(max_workers=2) as executor:
            first = executor.submit(self.coordinator.submit, request, self.enrollment)
            try:
                self.assertTrue(self.backend.observation_ready.wait(5))
                other = self.make_coordinator(store=ShadowStore(self.path))
                pending = executor.submit(other.submit, request, self.enrollment).result(5)
                self.assertEqual(pending.lifecycle, "running")
                self.assertIsNone(pending.verdict)
                with self.assertRaisesRegex(Rejected, "circuit_open|capacity_exhausted"):
                    self.coordinator.submit(self.request(), self.enrollment)
            finally:
                self.backend.observation_release.set()
            completed = first.result(5)
        self.assertEqual(completed.shadow_run_uuid, pending.shadow_run_uuid)
        self.assertEqual(completed.verdict.result, Verdict.PASSED)
        self.assertEqual((self.backend.issue_calls, self.backend.simulated_starts), (1, 1))

    def test_lost_issue_response_quarantines_and_never_reissues(self):
        self.backend = FakeExecutionBackend(FakeScenario(issue_fault=IssueFault.LOST_RESPONSE))
        self.coordinator = self.make_coordinator()
        self.enabled()
        request = self.request()
        first = self.coordinator.submit(request, self.enrollment)
        self.assertEqual(first.verdict.reason, Reason.ISSUE)
        self.assertEqual(first.cleanup_state, "quarantined")
        self.assertTrue(first.unresolved)
        for coordinator in (self.coordinator, self.make_coordinator(store=ShadowStore(self.path))):
            self.assertEqual(coordinator.submit(request, self.enrollment), first)
        with self.assertRaisesRegex(Rejected, "circuit_open"):
            self.coordinator.submit(self.request(), self.enrollment)
        with self.assertRaisesRegex(Rejected, "cleanup_phase_invalid"):
            self.coordinator.reconcile_cleanup(first.shadow_run_uuid)
        self.assertEqual((self.backend.issue_calls, self.backend.simulated_creates, self.backend.simulated_starts), (1, 0, 0))

    def test_wrong_issue_receipt_cannot_be_acknowledged(self):
        report = self.run_scenario(FakeScenario(issue_fault=IssueFault.WRONG_RECEIPT))
        self.assertEqual(report.verdict.result, Verdict.UNKNOWN)
        self.assertTrue(report.unresolved)
        self.assertEqual(self.backend.simulated_starts, 0)

    def test_mapping_is_committed_before_backend_issue(self):
        original = self.backend.issue
        def inspect(ticket):
            with closing(sqlite3.connect(self.path)) as db:
                row = db.execute("SELECT id,execution_id,lifecycle FROM shadow_runs").fetchone()
            self.assertEqual(row, (ticket.run_uuid, ticket.execution_uuid, "issuing"))
            return original(ticket)
        self.enabled()
        with patch.object(self.backend, "issue", side_effect=inspect):
            self.assertEqual(self.coordinator.submit(self.request(), self.enrollment).verdict.result, Verdict.PASSED)

    def test_process_loss_between_issue_and_ack_mapping_does_not_generate_new_uuid(self):
        self.enabled()
        request = self.request()
        run_id, _ = self.store.reserve(request, self.enrollment, "operator-unit", self.clock(), 1)
        ticket = self.store.claim_issue(run_id, "operator-unit", self.clock())
        self.backend.issue(ticket)  # Coordinator crashed before acknowledging this issue.
        restarted = self.make_coordinator(store=ShadowStore(self.path))
        pending = restarted.submit(request, self.enrollment)
        self.assertEqual(pending.lifecycle, "issuing")
        self.assertEqual(pending.execution_uuid, ticket.execution_uuid)
        self.clock.advance()
        terminal = restarted.submit(request, self.enrollment)
        self.assertEqual(terminal.shadow_run_uuid, run_id)
        self.assertEqual(terminal.verdict.reason, Reason.DEADLINE)
        self.assertTrue(terminal.unresolved)
        self.assertEqual(self.backend.issue_calls, 1)
        self.assertEqual(self.backend.simulated_starts, 0)

    def test_process_loss_after_fake_start_retains_durable_start_intent(self):
        self.enabled()
        request = self.request()
        original = self.backend.start
        def crash(ticket):
            original(ticket)
            raise KeyboardInterrupt()
        with patch.object(self.backend, "start", side_effect=crash), self.assertRaises(KeyboardInterrupt):
            self.coordinator.submit(request, self.enrollment)
        with closing(sqlite3.connect(self.path)) as db:
            run_id, lifecycle, cleanup, unresolved = db.execute(
                "SELECT id,lifecycle,cleanup,unresolved FROM shadow_runs").fetchone()
        self.assertEqual((lifecycle, cleanup, unresolved), ("running", "pending", 1))
        self.clock.advance()
        report = self.coordinator.submit(request, self.enrollment)
        self.assertEqual(report.verdict.result, Verdict.UNKNOWN)
        self.assertEqual(self.backend.simulated_starts, 1)
        self.assertTrue(self.coordinator.reconcile_cleanup(run_id))
        self.assertEqual(self.coordinator.report(run_id).verdict, report.verdict)

    def test_lost_start_response_does_not_retry_start_and_cleanup_is_separate(self):
        report = self.run_scenario(FakeScenario(lose_start_response=True))
        self.assertEqual(report.verdict.result, Verdict.UNKNOWN)
        self.assertEqual(report.cleanup_state, "quarantined")
        self.assertTrue(self.coordinator.reconcile_cleanup(report.shadow_run_uuid))
        cleaned = self.coordinator.report(report.shadow_run_uuid)
        self.assertEqual(cleaned.verdict, report.verdict)
        self.assertEqual(cleaned.cleanup_state, "confirmed")
        self.assertEqual(self.backend.simulated_starts, 1)

    def test_late_pass_after_deadline_never_replaces_unknown(self):
        self.enabled()
        request = self.request()
        self.backend.observation_release = threading.Event()
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(self.coordinator.submit, request, self.enrollment)
            try:
                self.assertTrue(self.backend.observation_ready.wait(5))
                with closing(sqlite3.connect(self.path)) as db:
                    run_id = db.execute("SELECT id FROM shadow_runs").fetchone()[0]
                self.clock.advance(8)  # Exact deadline boundary, no sleeping.
                expired = self.coordinator.expire(run_id)
                self.assertEqual(expired.verdict.reason, Reason.DEADLINE)
            finally:
                self.backend.observation_release.set()
            final = future.result(5)
        self.assertEqual(final.verdict, expired.verdict)
        self.assertEqual(final.verdict.result, Verdict.UNKNOWN)
        self.assertEqual(final.cleanup_state, "confirmed")
        self.assertEqual(self.coordinator.submit(request, self.enrollment), final)

    def test_shadow_receipt_replay_from_another_run_is_unknown(self):
        self.enabled()
        original = self.backend.observe
        saved = []
        def capture(ticket):
            receipt = original(ticket)
            saved.append(receipt)
            return receipt
        with patch.object(self.backend, "observe", side_effect=capture):
            first = self.coordinator.submit(self.request(), self.enrollment)
        with patch.object(self.backend, "observe", return_value=saved[0]):
            second = self.coordinator.submit(self.request(), self.enrollment)
        self.assertEqual(first.verdict.result, Verdict.PASSED)
        self.assertEqual(second.verdict.reason, Reason.REPLAY)
        self.assertNotEqual(first.shadow_run_uuid, second.shadow_run_uuid)
        self.assertTrue(second.unresolved)

    def test_cleanup_pending_global_breaker_and_cleanup_only_recovery(self):
        report = self.run_scenario(FakeScenario(cleanup_confirmed=False))
        self.assertEqual(report.verdict.result, Verdict.PASSED)
        self.assertEqual(report.cleanup_state, "pending")
        self.assertFalse(self.coordinator.reconcile_cleanup(report.shadow_run_uuid))
        self.coordinator.kill()
        self.coordinator.set_enabled(True)
        with self.assertRaisesRegex(Rejected, "circuit_open"):
            self.coordinator.submit(self.request(), self.enrollment)
        self.backend.scenario = FakeScenario(cleanup_confirmed=True)
        self.assertTrue(self.coordinator.reconcile_cleanup(report.shadow_run_uuid))
        self.assertEqual(self.coordinator.report(report.shadow_run_uuid).verdict, report.verdict)
        self.assertEqual(self.backend.simulated_starts, 1)

    def test_kill_switch_during_observation_and_reenable_does_not_resurrect_run(self):
        self.enabled()
        request = self.request()
        original = self.backend.observe
        def killed(ticket):
            receipt = original(ticket)
            self.coordinator.kill()
            self.coordinator.set_enabled(True)  # Epoch must still invalidate the active run.
            return receipt
        with patch.object(self.backend, "observe", side_effect=killed):
            result = self.coordinator.submit(request, self.enrollment)
        self.assertEqual(result.verdict.reason, Reason.KILLED)
        self.assertEqual(result.cleanup_state, "confirmed")
        self.assertEqual(self.coordinator.submit(request, self.enrollment), result)
        self.assertEqual(self.backend.simulated_starts, 1)

    def test_kill_between_issue_and_start_prevents_create(self):
        self.enabled()
        original = self.store.start
        def stop(ticket, backend, clock):
            self.coordinator.kill()
            return original(ticket, backend, clock)
        with patch.object(self.store, "start", side_effect=stop):
            report = self.coordinator.submit(self.request(), self.enrollment)
        self.assertEqual(report.verdict.reason, Reason.KILLED)
        self.assertEqual(report.cleanup_state, "not_required")
        self.assertEqual(self.backend.simulated_creates, 0)
        with self.assertRaisesRegex(Rejected, "feature_disabled"):
            self.coordinator.submit(self.request(), self.enrollment)

    def test_deadline_checked_after_issue_and_before_start(self):
        self.enabled()
        original = self.backend.issue
        def late(ticket):
            receipt = original(ticket)
            self.clock.advance()
            return receipt
        with patch.object(self.backend, "issue", side_effect=late):
            report = self.coordinator.submit(self.request(), self.enrollment)
        self.assertEqual(report.verdict.reason, Reason.DEADLINE)
        self.assertEqual(report.cleanup_state, "not_required")
        self.assertEqual(self.backend.simulated_starts, 0)

    def test_backend_exception_is_sanitized_and_does_not_grant_pass(self):
        self.enabled()
        secret = "password=do-not-retain; raw Docker inspect and customer answer"
        with patch.object(self.backend, "observe", side_effect=RuntimeError(secret)):
            report = self.coordinator.submit(self.request(), self.enrollment)
        self.assertEqual(report.verdict.reason, Reason.INFRASTRUCTURE)
        self.assertNotIn(secret, json.dumps(report.to_dict()))
        self.assertNotIn(secret.encode(), self.path.read_bytes())

    def test_report_access_is_bound_to_operator_and_live_backend_forbidden(self):
        report = self.enabled().submit(self.request(), self.enrollment)
        with self.assertRaisesRegex(Rejected, "run_not_authorized"):
            self.store.report(report.shadow_run_uuid, "operator-other")
        with self.assertRaisesRegex(Rejected, "operator_not_authorized"):
            self.make_coordinator(operator_id="operator-other")

    def test_unknown_transport_result_stays_unknown_after_cleanup_and_retry(self):
        self.backend = FakeExecutionBackend(FakeScenario(transport=FakeTransport(fault=TransportFault.TIMEOUT)))
        self.coordinator = self.make_coordinator()
        self.enabled()
        request = self.request()
        report = self.coordinator.submit(request, self.enrollment)
        self.assertEqual(report.verdict.result, Verdict.UNKNOWN)
        self.assertEqual(report.cleanup_state, "confirmed")
        self.backend.scenario = FakeScenario()  # Later good environment cannot rewrite the receipt.
        self.assertEqual(self.coordinator.submit(request, self.enrollment), report)
        self.assertEqual(self.backend.simulated_starts, 1)

    def test_global_breaker_blocks_a_different_attempt_and_scope(self):
        from trusted_checker_shadow.contracts import CandidateMetadata, OperatorRequest
        from trusted_checker_shadow.enrollment import FakeTrustedAuthority
        another = fixture(2)
        another = replace(another, target=replace(another.target, scope="offline-another", container_id="e"*64))
        authority = FakeTrustedAuthority("fake-authority", (self.fixture, another))
        other_enrollment = authority.enroll(CandidateMetadata(another.target, "offline_fixture"),
                                            fixture_uuid=another.fixture_uuid, operator_id="operator-unit")
        backend = FakeExecutionBackend(FakeScenario(cleanup_confirmed=False))
        coordinator = self.make_coordinator(authority=authority, backend=backend)
        coordinator.set_enabled(True)
        coordinator.submit(self.request(), self.enrollment)
        request = OperatorRequest(str(uuid4()), other_enrollment.enrollment_uuid, another.target.attempt_id,
                                  another.target.owner_id, another.target.scope, str(uuid4()), self.clock()+8)
        with self.assertRaisesRegex(Rejected, "circuit_open"):
            coordinator.submit(request, other_enrollment)
        self.assertEqual(backend.simulated_creates, 1)

    def test_malformed_nested_receipt_is_unknown_without_copying_raw_observations(self):
        from trusted_checker_shadow.contracts import RuntimeObservation
        self.enabled()
        def malformed(ticket):
            return ExecutionReceipt(ticket, {"inspect": "private secret"}, RuntimeObservation(ticket.target),
                                    FakeTransport(), True)
        with patch.object(self.backend, "observe", side_effect=malformed):
            report = self.coordinator.submit(self.request(), self.enrollment)
        self.assertEqual(report.verdict.reason, Reason.PROTOCOL)
        self.assertEqual(report.lifecycle, "terminal")
        self.assertIsNone(report.observed_before)
        self.assertNotIn("private secret", json.dumps(report.to_dict()))

    def test_direct_duplicate_issue_after_lost_response_cannot_clear_quarantine(self):
        self.enabled()
        request = self.request()
        run_id, _ = self.store.reserve(request, self.enrollment, "operator-unit", self.clock(), 1)
        ticket = self.store.claim_issue(run_id, "operator-unit", self.clock())
        backend = FakeExecutionBackend(FakeScenario(issue_fault=IssueFault.LOST_RESPONSE))
        self.assertFalse(self.store.dispatch_issue(ticket, backend, self.clock))
        terminal = self.coordinator.report(run_id)
        self.assertFalse(self.store.dispatch_issue(ticket, backend, self.clock))
        self.assertEqual(self.coordinator.report(run_id), terminal)
        self.assertTrue(terminal.unresolved)
        self.assertEqual(backend.issue_calls, 1)

    def test_process_crash_during_issue_prevents_internal_dispatch_retry(self):
        self.enabled()
        request = self.request()
        run_id, _ = self.store.reserve(request, self.enrollment, "operator-unit", self.clock(), 1)
        ticket = self.store.claim_issue(run_id, "operator-unit", self.clock())
        original = self.backend.issue
        def crash(ticket):
            original(ticket)
            raise KeyboardInterrupt()
        with patch.object(self.backend, "issue", side_effect=crash), self.assertRaises(KeyboardInterrupt):
            self.store.dispatch_issue(ticket, self.backend, self.clock)
        self.assertFalse(self.store.dispatch_issue(ticket, self.backend, self.clock))
        self.assertEqual(self.backend.issue_calls, 1)
        self.clock.advance()
        self.assertEqual(self.coordinator.expire(run_id).verdict.result, Verdict.UNKNOWN)
