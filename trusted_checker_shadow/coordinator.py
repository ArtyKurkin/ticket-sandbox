"""Offline operator API, default OFF. Real runtime backends are rejected."""

import time

from .backend import CleanupReceipt, ExecutionReceipt, FakeExecutionBackend
from .contracts import OperatorRequest, ProbeResult, Reason, RuntimeObservation, Verdict, atom, require
from .enrollment import FakeTrustedAuthority
from .policy import POLICY, validate_policy
from .predicate import probe
from .state import ShadowStore


class OfflineCoordinator:
    def __init__(self, store, authority, backend, *, operator_id, clock=time.time, policy=POLICY, max_parallel=1):
        require(type(store) is ShadowStore, "dedicated_store_required")
        require(type(authority) is FakeTrustedAuthority, "fake_authority_required")
        require(type(backend) is FakeExecutionBackend, "fake_backend_required")
        atom(operator_id, "operator-")
        authority.authorize_operator(operator_id)
        require(type(max_parallel) is int and max_parallel == 1, "concurrency_limit_invalid")
        validate_policy(policy)
        self.store, self.authority, self.backend = store, authority, backend
        self.operator_id, self.clock, self.policy = operator_id, clock, policy
        self.max_parallel = max_parallel

    def set_enabled(self, enabled):
        self.store.set_enabled(enabled, operator_id=self.operator_id, now=self.clock())

    def kill(self):
        self.set_enabled(False)

    def submit(self, request, enrollment):
        validate_policy(self.policy)
        require(type(request) is OperatorRequest, "request_schema_invalid")
        request.__post_init__()
        self.authority.verify(enrollment, operator_id=self.operator_id)
        target = enrollment.target
        require((request.enrollment_uuid, request.attempt_id, request.owner_id, request.task, request.scope) ==
                (enrollment.enrollment_uuid, target.attempt_id, target.owner_id, target.task, target.scope),
                "request_target_mismatch")
        run_id, created = self.store.reserve(request, enrollment, self.operator_id, self.clock(), self.max_parallel)
        if not created:
            self.store.expire(run_id, self.operator_id, self.clock())
            return self.report(run_id)
        ticket = self.store.claim_issue(run_id, self.operator_id, self.clock())
        if ticket is None or not self.store.dispatch_issue(ticket, self.backend, self.clock):
            return self.report(run_id)
        if not self.store.start(ticket, self.backend, self.clock):
            return self.report(run_id)
        receipt = None
        safe_before, safe_after = None, None
        try:
            receipt = self.backend.observe(ticket)
            if type(receipt) is not ExecutionReceipt or receipt.ticket != ticket:
                result = ProbeResult(Verdict.UNKNOWN, Reason.REPLAY)
            else:
                if type(receipt.before) is not RuntimeObservation or type(receipt.after) is not RuntimeObservation:
                    result = ProbeResult(Verdict.UNKNOWN, Reason.PROTOCOL)
                else:
                    receipt.before.__post_init__()
                    receipt.after.__post_init__()
                    safe_before, safe_after = receipt.before, receipt.after
                    result = probe(target, safe_before, safe_after, receipt.transport, self.policy)
        except Exception:
            # No arbitrary exception text, output, inspect or API body is retained.
            result = ProbeResult(Verdict.UNKNOWN, Reason.INFRASTRUCTURE)
        self.store.finish(ticket, result, self.clock, before=safe_before, after=safe_after)
        if (type(receipt) is ExecutionReceipt and receipt.ticket == ticket and
                receipt.cleanup_confirmed is True):
            self.reconcile_cleanup(run_id)
        return self.report(run_id)

    def report(self, run_id):
        return self.store.report(run_id, self.operator_id)

    def expire(self, run_id):
        self.store.expire(run_id, self.operator_id, self.clock())
        return self.report(run_id)

    def reconcile_cleanup(self, run_id):
        """Read a known exact FAKE cleanup receipt. Never issue, start or adopt.

        An unknown issue without a known start stays quarantined. This API has
        no 'force', lease release, verdict correction or candidate-ID argument.
        """
        ticket = self.store.ticket_for_cleanup(run_id, self.operator_id)
        receipt = self.backend.cleanup_receipt(ticket)
        if type(receipt) is CleanupReceipt and receipt.ticket == ticket and receipt.confirmed is True:
            self.store.confirm_cleanup(ticket, self.clock())
            return True
        return False
