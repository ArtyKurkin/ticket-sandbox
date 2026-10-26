"""Offline runtime authority/state machine. Fences contain no SDK implementation.

Only a future trusted, bounded adapter may invoke its fixed operation inside a
fence. This module never discovers a socket, calls Docker or adopts a target.
"""

from contextlib import contextmanager
import json
import sqlite3
import time
from datetime import datetime
from functools import wraps
from uuid import uuid4

from trusted_checker_shadow.policy import digest
from trusted_checker_shadow.predicate import HTTPResponse, evaluate_response
from .attestation import Attestation, ReceiptVerifier
from .contracts import (CleanupConfirmation, CreateIntent, CreateResponse,
                        DaemonIdentity, DaemonObservation, DispatchPermit, EgressEvidence,
                        EgressValidation, IdentityObservation, NetworkEvidence, Phase,
                        ProbeResponse, ProvisionRequest, Resource, RunRequest, RunnerObservation,
                        RuntimeApproval, RuntimeEnrollment, StartPermit, TargetSnapshot,
                        expected_config, stamp)
from .journal import RuntimeJournal, body, encode
from .live_contract import LIVE_PREFLIGHT_CASES, live_matrix_digest
from .profiles import Denied, EGRESS_CASES, LIMITS, matrix_digest, require, rules_digest


def fail_run_closed(method):
    """A rejected execution observation cannot be retried into a positive run."""
    @wraps(method)
    def guarded(self, run_id, *args, **kwargs):
        try:
            return method(self, run_id, *args, **kwargs)
        except Denied:
            self._unknown(run_id, "execution_identity_or_protocol_unconfirmed")
            raise
    return guarded


class RuntimeTargetAuthority:
    def __init__(self, journal, verifier, *, operator_principal, approved_daemon, clock=time.time):
        require(type(journal) is RuntimeJournal and type(verifier) is ReceiptVerifier, "authority_boundary_invalid")
        require(type(approved_daemon) is DaemonIdentity, "explicit_daemon_registration_required")
        approved_daemon.__post_init__()
        verifier.authorize_operator(operator_principal)
        self.journal, self.verifier = journal, verifier
        self.operator, self.daemon, self.clock = operator_principal, approved_daemon, clock

    def _now(self, db):
        now = self.clock()
        stamp(now)
        old = db.execute("SELECT clock_highwater FROM rt_control").fetchone()[0]
        require(now >= old, "clock_rollback")
        db.execute("UPDATE rt_control SET clock_highwater=?", (now,))
        return now

    def _approval(self, db, identifier):
        approval = RuntimeApproval.from_dict(self.journal.get(db, "approval", identifier))
        require(approval.operator_principal == self.operator, "operator_scope_mismatch")
        return approval

    def _object(self, db, kind, identifier):
        row = db.execute("SELECT * FROM rt_objects WHERE kind=? AND id=?", (kind, identifier)).fetchone()
        require(row is not None, "runtime_object_missing")
        intent = CreateIntent.from_dict(json.loads(row["body"]))
        return row, intent, self._approval(db, intent.approval_uuid)

    def _revoked(self, db, kind, identifier):
        return db.execute("SELECT 1 FROM rt_revocations WHERE kind=? AND id=?", (kind, identifier)).fetchone() is not None

    def _current(self, db, approval, now, row=None):
        require(approval.authority_mode != 'live_runtime_v2' or not self.journal.stop_requested(), 'live_stop_latched')
        require(approval.daemon == self.daemon, "registered_daemon_mismatch")
        require(approval.created_at <= now < approval.expires_at, "approval_expired")
        require(not self._revoked(db, "approval", approval.approval_uuid), "approval_revoked")
        control = db.execute("SELECT * FROM rt_control").fetchone()
        require(control["enabled"] == 1, "feature_disabled")
        if row is not None:
            require(row["epoch"] == control["epoch"], "control_epoch_changed")
            require(now < row["deadline"], "deadline_exceeded")
        return control["epoch"]

    def _circuit(self, db, exclude=None):
        for row in db.execute("SELECT kind,id,phase,cleanup,terminal FROM rt_objects"):
            if exclude == (row["kind"], row["id"]):
                continue
            require(not (row["phase"] in ("create_requested", "quarantined") and row["cleanup"] != "confirmed")
                    and not (row["terminal"] is not None and row["cleanup"] in ("pending", "quarantined")), "circuit_open")

    def _fresh(self, payload, context, approval, now):
        require(payload.context_uuid == context and 0 <= now-payload.observed_at <= approval.limits.api_seconds,
                "observation_context_or_freshness_invalid")

    def register_approval(self, signed):
        require(type(signed) is Attestation and type(signed.payload) is RuntimeApproval, "approval_receipt_required")
        approval = self.verifier.verify(signed, RuntimeApproval, signed.payload.scope)
        require((approval.authority_mode == 'live_runtime_v2') == self.journal.live, 'approval_journal_mode_mismatch')
        require(approval.operator_principal == self.operator and approval.daemon == self.daemon, "approval_deployment_mismatch")
        with self.journal.transaction() as db:
            now = self._now(db)
            require(approval.created_at <= now < approval.expires_at, "approval_expired")
            require(not self._revoked(db, "approval", approval.approval_uuid), "approval_revoked")
            self.journal.receipt(db, signed, approval.approval_uuid, "approval")
            self.journal.put(db, "approval", approval.approval_uuid, approval)
            self.journal.audit(db, approval.approval_uuid, "approval_registered", now)
        return approval.digest

    def set_enabled(self, enabled):
        require(type(enabled) is bool, "feature_flag_invalid")
        with self.journal.transaction() as db:
            now = self._now(db)
            db.execute("UPDATE rt_control SET enabled=?,epoch=epoch+1", (int(enabled),))
            self.journal.audit(db, "control", "enabled" if enabled else "disabled", now)

    def kill(self):
        self.set_enabled(False)

    def revoke_approval(self, approval_uuid):
        with self.journal.transaction() as db:
            self._approval(db, approval_uuid)
            now = self._now(db)
            db.execute("INSERT OR IGNORE INTO rt_revocations VALUES('approval',?,?)", (approval_uuid, now))
            self.journal.audit(db, approval_uuid, "revoked", now)

    def _dedupe(self, db, kind, request_id, canonical, fingerprint):
        alias = db.execute("SELECT * FROM rt_requests WHERE kind=? AND id=?", (kind, request_id)).fetchone()
        if alias:
            require(alias["fingerprint"] == fingerprint, "request_payload_conflict")
            return alias["object_id"]
        old = db.execute("SELECT * FROM rt_claims WHERE kind=? AND canonical=?", (kind, canonical)).fetchone()
        if old:
            require(old["fingerprint"] == fingerprint, "attempt_or_sample_binding_conflict")
            db.execute("INSERT INTO rt_requests VALUES(?,?,?,?)", (kind, request_id, fingerprint, old["object_id"]))
            return old["object_id"]
        return None

    def _insert(self, db, kind, intent, canonical, request_id, fingerprint, epoch):
        db.execute("INSERT INTO rt_objects VALUES(?,?,?,?,?,?,?,?,NULL)",
                   (kind, intent.intent_uuid, encode(intent), fingerprint, "intent_recorded" if kind == "target" else "reserved",
                    "not_required", epoch, intent.deadline))
        db.execute("INSERT INTO rt_claims VALUES(?,?,?,?)", (kind, canonical, intent.intent_uuid, fingerprint))
        db.execute("INSERT INTO rt_requests VALUES(?,?,?,?)", (kind, request_id, fingerprint, intent.intent_uuid))

    def provision(self, request):
        require(type(request) is ProvisionRequest, "provision_request_required")
        request.__post_init__()
        with self.journal.transaction() as db:
            approval = self._approval(db, request.approval_uuid)
            now = self._now(db)
            fingerprint = digest({"attempt": body(request.attempt), "approval": approval.digest})
            canonical = digest({"instance": request.attempt.sandbox_instance, "attempt": request.attempt.attempt_id})
            old = self._dedupe(db, "target", request.request_uuid, canonical, fingerprint)
            if old:
                return self._object(db, "target", old)[1]
            epoch = self._current(db, approval, now)
            self._circuit(db)
            require(not db.execute("SELECT 1 FROM rt_objects WHERE kind='target' AND cleanup!='confirmed'").fetchone(),
                    "pilot_target_capacity")
            intent = CreateIntent(str(uuid4()), Resource.TARGET, approval.approval_uuid, approval.digest, approval.scope,
                request.attempt, str(uuid4()), str(uuid4()), approval.daemon, approval.target_image_id,
                approval.network.digest, approval.policy_digest, approval.target_profile_digest, fingerprint,
                now, min(now+approval.limits.run_seconds, approval.expires_at))
            self._insert(db, "target", intent, canonical, request.request_uuid, fingerprint, epoch)
            self.journal.audit(db, intent.intent_uuid, "intent_recorded", now)
            return intent

    def _kind(self, resource):
        require(type(resource) is Resource, "ownership_domain_invalid")
        return "target" if resource == Resource.TARGET else "run"

    def begin_create(self, intent, daemon_receipt):
        require(type(intent) is CreateIntent, "trusted_intent_required")
        intent.__post_init__()
        kind = self._kind(intent.resource)
        with self.journal.transaction() as db:
            row, saved, approval = self._object(db, kind, intent.intent_uuid)
            require(saved == intent, "intent_not_issued")
            now = self._now(db)
            self._current(db, approval, now, row)
            self._circuit(db, (kind, intent.intent_uuid))
            require(row["phase"] == ("intent_recorded" if kind == "target" else "checked_create"), "create_already_requested")
            if kind == "run":
                self._enrollment_for_run(db, row, now)
                self._phase_fresh(db, row["id"], Phase.BEFORE_CREATE, now)
            observed = self.verifier.verify(daemon_receipt, DaemonObservation, approval.scope)
            self._fresh(observed, intent.intent_uuid, approval, now)
            require(observed.daemon == approval.daemon, "daemon_or_endpoint_mismatch")
            self.journal.receipt(db, daemon_receipt, intent.intent_uuid, "create_daemon")
            permit = DispatchPermit(str(uuid4()), intent.intent_uuid, intent.resource, digest(body(intent)), row["epoch"], row["deadline"])
            self.journal.put(db, "create_permit_"+kind, row["id"], permit)
            db.execute("UPDATE rt_objects SET phase='create_requested',cleanup='quarantined' WHERE kind=? AND id=?", (kind, row["id"]))
            self.journal.audit(db, row["id"], "create_requested", now)
            return permit

    @contextmanager
    def create_fence(self, permit):
        require(type(permit) is DispatchPermit, "dispatch_permit_required")
        permit.__post_init__()
        kind = self._kind(permit.resource)
        with self.journal.transaction() as db:
            row, intent, approval = self._object(db, kind, permit.intent_uuid)
            now = self._now(db)
            self._current(db, approval, now, row)
            require(self.journal.get(db, "create_permit_"+kind, row["id"]) == body(permit), "dispatch_permit_not_issued")
            require(row["phase"] == "create_requested" and not self._document_exists(db, "create_dispatch_"+kind, row["id"]),
                    "create_dispatch_already_claimed")
            if kind == "run":
                self._enrollment_for_run(db, row, now)
                self._phase_fresh(db, row["id"], Phase.BEFORE_CREATE, now)
            self.journal.put(db, "create_dispatch_"+kind, row["id"], permit)
            self.journal.audit(db, row["id"], "create_dispatch", now)
        # Dispatch intent survives a crash/rollback while the bounded future call
        # holds this second lock. No caller retries this fence after ambiguity.
        with self.journal.transaction() as db:
            row, intent, approval = self._object(db, kind, permit.intent_uuid)
            self._current(db, approval, self._now(db), row)
            require(row["phase"] == "create_requested", "create_phase_closed")
            yield intent  # No adapter/SDK call is implemented here.

    def _document_exists(self, db, kind, identifier):
        return db.execute("SELECT 1 FROM rt_documents WHERE kind=? AND id=?", (kind, identifier)).fetchone() is not None

    @contextmanager
    def target_start_fence(self, provisioning_uuid, daemon_receipt):
        """One bounded initial start of a newly OWNED pilot target, never restart/adopt."""
        with self.journal.transaction() as db:
            row, intent, approval = self._object(db, "target", provisioning_uuid)
            now = self._now(db)
            self._current(db, approval, now, row)
            require(row["phase"] == "exact_id_recorded" and not self._document_exists(db, "target_start_dispatch", row["id"]),
                    "target_start_not_authorized_or_consumed")
            daemon = self.verifier.verify(daemon_receipt, DaemonObservation, approval.scope)
            self._fresh(daemon, row["id"], approval, now)
            require(daemon.daemon == approval.daemon, "daemon_or_endpoint_mismatch")
            self.journal.receipt(db, daemon_receipt, row["id"], "target_start_daemon")
            owned = self._ownership(db, Resource.TARGET, row["id"])
            reference = {"provisioning_uuid": row["id"], "container_id": owned["receipt"]["container_id"],
                         "ownership_digest": owned["attestation_digest"], "approval_digest": approval.digest}
            self.journal.put(db, "target_start_dispatch", row["id"], reference)
        with self.journal.transaction() as db:
            row, _, approval = self._object(db, "target", provisioning_uuid)
            self._current(db, approval, self._now(db), row)
            require(row["phase"] == "exact_id_recorded", "target_start_phase_closed")
            yield reference

    def record_create_response(self, permit, signed):
        require(type(permit) is DispatchPermit, "dispatch_permit_required")
        kind = self._kind(permit.resource)
        try:
            with self.journal.transaction() as db:
                row, intent, approval = self._object(db, kind, permit.intent_uuid)
                response = self.verifier.verify(signed, CreateResponse, approval.scope)
                require(self.journal.get(db, "create_dispatch_"+kind, row["id"]) == body(permit), "trusted_dispatch_provenance_missing")
                require((response.context_uuid, response.permit_uuid, response.resource, response.intent_digest,
                         response.daemon, response.image_id) == (intent.intent_uuid, permit.permit_uuid, intent.resource,
                         digest(body(intent)), intent.daemon, intent.image_id), "create_response_binding_mismatch")
                now = self._now(db)
                require(intent.created_at <= response.observed_at <= now, "create_response_time_invalid")
                existing = self._document_exists(db, "ownership_"+intent.resource.value, row["id"])
                if existing:
                    saved = self.journal.get(db, "ownership_"+intent.resource.value, row["id"])
                    require(saved["attestation_digest"] == signed.digest, "ownership_conflict")
                    return response.container_id
                self.journal.receipt(db, signed, row["id"], "create_response_"+kind)
                # This is the first write using a returned exact ID. No inspect,
                # diagnostic stdout or target adoption precedes ownership.
                self.journal.ownership(db, intent.resource, row["id"], signed)
                live = row["terminal"] is None and row["phase"] == "create_requested"
                try:
                    self._current(db, approval, now, row)
                    if kind == "run":
                        self._enrollment_for_run(db, row, now)
                except Denied:
                    live = False
                if row["terminal"] is None:
                    db.execute("UPDATE rt_objects SET phase=?,cleanup=? WHERE kind=? AND id=?",
                        ("exact_id_recorded" if live and kind == "target" else "runner_owned" if live else "quarantined",
                         "retained" if live and kind == "target" else "pending", kind, row["id"]))
                else:
                    db.execute("UPDATE rt_objects SET cleanup='pending' WHERE kind=? AND id=?", (kind, row["id"]))
                self.journal.audit(db, row["id"], "ownership_recorded", now)
                return response.container_id
        except (sqlite3.Error, OSError):
            # The previously committed create_requested/dispatch intent remains
            # blocking even if storage cannot record a separate error event.
            raise Denied("ownership_persistence_unconfirmed") from None

    def quarantine(self, intent_uuid, resource):
        kind = self._kind(resource)
        with self.journal.transaction() as db:
            row, _, _ = self._object(db, kind, intent_uuid)
            now = self._now(db)
            if row["terminal"] is None:
                db.execute("UPDATE rt_objects SET phase='quarantined',cleanup='quarantined' WHERE kind=? AND id=?", (kind, intent_uuid))
            self.journal.audit(db, intent_uuid, "quarantined", now)

    def _ownership(self, db, resource, identifier):
        return self.journal.get(db, "ownership_"+resource.value, identifier)

    def _validate_target(self, snapshot, intent, approval, ownership):
        require(type(snapshot) is TargetSnapshot, "target_snapshot_required")
        snapshot.__post_init__()
        created = ownership["receipt"]
        require((snapshot.attempt, snapshot.runtime_binding_uuid, snapshot.generation_uuid, snapshot.daemon,
                 snapshot.container_id, snapshot.image_id, snapshot.policy_digest) ==
                (intent.attempt, intent.runtime_binding_uuid, intent.generation_uuid, approval.daemon,
                 created["container_id"], approval.target_image_id, approval.policy_digest), "target_identity_drift")
        require(snapshot.running and not (snapshot.paused or snapshot.restarting or snapshot.dead), "target_not_running")
        require(len(snapshot.endpoints) == 1 and snapshot.endpoints[0].container_id == snapshot.container_id
                and snapshot.endpoints[0].network_id == approval.network.network_id and
                snapshot.endpoints[0].ipv4 == approval.network.target_ipv4, "target_network_drift")
        require(snapshot.config == expected_config(approval, Resource.TARGET), "target_profile_drift")

    def _check_bundle(self, db, context, phase, approval, snapshot, identity, network, egress, validation, now, runner=None):
        observation = self.verifier.verify(identity, IdentityObservation, approval.scope)
        self._fresh(observation, context, approval, now)
        require(observation.phase == phase and observation.target == snapshot, "target_identity_drift")
        net = self.verifier.verify(network, NetworkEvidence, approval.scope)
        self._fresh(net, context, approval, now)
        require(net.phase == phase and net.daemon == approval.daemon and net.internal is True and net.driver == "bridge"
                and net.network_profile_digest == approval.network.digest, "network_profile_drift")
        endpoints = snapshot.endpoints + ((runner,) if runner is not None else ())
        require(len(net.endpoints) == len(endpoints) and set(net.endpoints) == set(endpoints), "extra_or_substituted_network_attachment")
        enforcement = self.verifier.verify(egress, EgressEvidence, approval.scope)
        self._fresh(enforcement, context, approval, now)
        expected_runner = None if phase in (Phase.ENROLL, Phase.BEFORE_CREATE) else self._ownership(db, Resource.RUNNER, context)["receipt"]["container_id"]
        require(enforcement.phase == phase and enforcement.daemon == approval.daemon and
                enforcement.target_digest == digest(body(snapshot)) and enforcement.runner_id == expected_runner and
                enforcement.network_profile_digest == approval.network.digest and
                enforcement.enforcement_reference == approval.network.enforcement_reference and
                enforcement.rules_digest == rules_digest(approval.network) and all((enforcement.default_deny,
                enforcement.only_target_8080, enforcement.denies_host_metadata_platform, enforcement.anti_spoofing)), "egress_unconfirmed")
        checked = self.verifier.verify(validation, EgressValidation, approval.scope)
        self._fresh(checked, context, approval, now)
        live = approval.authority_mode == 'live_runtime_v2'
        preflight = phase in (Phase.ENROLL, Phase.BEFORE_CREATE, Phase.BEFORE_START)
        expected_cases = LIVE_PREFLIGHT_CASES if live and preflight else EGRESS_CASES
        require(checked.phase == phase and checked.enforcement_receipt_digest == egress.digest and
                checked.matrix_digest == (live_matrix_digest(approval.network, phase) if live else matrix_digest(approval.network))
                and checked.passed_cases == expected_cases,
                "independent_egress_validation_missing")
        for signed, purpose in ((identity, "identity"), (network, "network"), (egress, "egress"), (validation, "validation")):
            self.journal.receipt(db, signed, context, phase.value+"_"+purpose)
        return {"target": body(snapshot), "observed_at": min(r.payload.observed_at for r in (identity, network, egress, validation)),
                "identity_receipt": identity.digest, "network_receipt": network.digest,
                "egress_receipt": egress.digest, "validation_receipt": validation.digest}

    def verify_provision(self, provisioning_uuid, identity, network, egress, validation):
        with self.journal.transaction() as db:
            row, intent, approval = self._object(db, "target", provisioning_uuid)
            now = self._now(db)
            self._current(db, approval, now, row)
            require(row["phase"] == "exact_id_recorded", "creation_ownership_required")
            require(self._document_exists(db, "target_start_dispatch", row["id"]), "target_start_provenance_missing")
            ownership = self._ownership(db, Resource.TARGET, row["id"])
            observation = self.verifier.verify(identity, IdentityObservation, approval.scope)
            self._validate_target(observation.target, intent, approval, ownership)
            require(observation.target.restart_count == 0 and intent.created_at <=
                    datetime.fromisoformat(observation.target.started_at).timestamp() <= now,
                    "initial_target_generation_unconfirmed")
            checked = self._check_bundle(db, row["id"], Phase.ENROLL, approval, observation.target,
                                         identity, network, egress, validation, now)
            self.journal.put(db, "target_baseline", row["id"], checked)
            db.execute("UPDATE rt_objects SET phase='identity_verified' WHERE kind='target' AND id=?", (row["id"],))
            self.journal.audit(db, row["id"], "identity_verified", now)

    def enroll(self, provisioning_uuid):
        with self.journal.transaction() as db:
            row, intent, approval = self._object(db, "target", provisioning_uuid)
            if row["phase"] == "enrolled":
                enrollment = RuntimeEnrollment.from_dict(self.journal.get(db, "enrollment", row["id"]))
                self._verify_enrollment(db, enrollment, self._now(db))
                return enrollment
            now = self._now(db)
            self._current(db, approval, now, row)
            require(row["phase"] == "identity_verified", "verified_provisioning_chain_required")
            baseline = self.journal.get(db, "target_baseline", row["id"])
            require(0 <= now-baseline["observed_at"] <= LIMITS.api_seconds, "enrollment_observation_stale")
            ownership = self._ownership(db, Resource.TARGET, row["id"])
            enrollment = RuntimeEnrollment(str(uuid4()), row["id"], approval.approval_uuid, approval.digest, approval.scope,
                TargetSnapshot.from_dict(baseline["target"]), ownership["receipt"]["receipt_uuid"], ownership["attestation_digest"], approval.policy_digest,
                'live_runtime_chain_v2' if approval.authority_mode == 'live_runtime_v2' else 'offline_runtime_chain_v1')
            self.journal.put(db, "enrollment", row["id"], enrollment)
            self.journal.put(db, "enrollment_index", enrollment.enrollment_uuid, {"provisioning_uuid": row["id"]})
            db.execute("UPDATE rt_objects SET phase='enrolled' WHERE kind='target' AND id=?", (row["id"],))
            self.journal.audit(db, row["id"], "enrolled", now)
            return enrollment

    def _verify_enrollment(self, db, enrollment, now):
        require(type(enrollment) is RuntimeEnrollment, "runtime_enrollment_required")
        enrollment.__post_init__()
        require(self.journal.get(db, "enrollment", enrollment.provisioning_uuid) == body(enrollment), "enrollment_not_issued")
        row, _, approval = self._object(db, "target", enrollment.provisioning_uuid)
        require(enrollment.verification_mode == ('live_runtime_chain_v2' if approval.authority_mode == 'live_runtime_v2'
                                                 else 'offline_runtime_chain_v1'), 'enrollment_mode_mismatch')
        require(row["phase"] == "enrolled" and not self._revoked(db, "binding", enrollment.target.runtime_binding_uuid), "runtime_binding_revoked")
        self._current(db, approval, now)
        return approval

    def revoke_binding(self, enrollment):
        require(type(enrollment) is RuntimeEnrollment, "runtime_enrollment_required")
        with self.journal.transaction() as db:
            require(self.journal.get(db, "enrollment", enrollment.provisioning_uuid) == body(enrollment), "enrollment_not_issued")
            self._object(db, "target", enrollment.provisioning_uuid)
            now = self._now(db)
            db.execute("INSERT OR IGNORE INTO rt_revocations VALUES('binding',?,?)", (enrollment.target.runtime_binding_uuid, now))
            db.execute("UPDATE rt_objects SET phase='quarantined',cleanup='pending' WHERE kind='target' AND id=?", (enrollment.provisioning_uuid,))
            self.journal.audit(db, enrollment.provisioning_uuid, "revoked", now)

    def reserve_run(self, request, enrollment):
        require(type(request) is RunRequest and type(enrollment) is RuntimeEnrollment, "runtime_run_contract_required")
        request.__post_init__()
        require(request.enrollment_uuid == enrollment.enrollment_uuid and request.attempt == enrollment.target.attempt,
                "run_owner_or_attempt_mismatch")
        with self.journal.transaction() as db:
            now = self._now(db)
            approval = self._verify_enrollment(db, enrollment, now)
            fingerprint = digest({"request": {k: v for k, v in body(request).items() if k != "request_uuid"}, "enrollment": body(enrollment)})
            canonical = digest({"enrollment": enrollment.enrollment_uuid, "slot": request.sample_slot,
                                "ordinary": request.ordinary.execution_uuid if request.ordinary else None})
            old = self._dedupe(db, "run", request.request_uuid, canonical, fingerprint)
            if old:
                return old
            self._circuit(db)
            require(not db.execute("SELECT 1 FROM rt_objects WHERE kind='run' AND terminal IS NULL").fetchone(), "runtime_capacity")
            epoch = self._current(db, approval, now)
            intent = CreateIntent(str(uuid4()), Resource.RUNNER, approval.approval_uuid, approval.digest, approval.scope,
                request.attempt, enrollment.target.runtime_binding_uuid, enrollment.target.generation_uuid, approval.daemon,
                approval.runner_image_id, approval.network.digest, approval.policy_digest, approval.runner_profile_digest,
                fingerprint, now, min(now+LIMITS.run_seconds, approval.expires_at))
            self._insert(db, "run", intent, canonical, request.request_uuid, fingerprint, epoch)
            self.journal.put(db, "run_enrollment", intent.intent_uuid, enrollment)
            self.journal.put(db, "run_request", intent.intent_uuid, request)
            self.journal.audit(db, intent.intent_uuid, "run_reserved", now)
            return intent.intent_uuid

    def _enrollment_for_run(self, db, row, now):
        enrollment = RuntimeEnrollment.from_dict(self.journal.get(db, "run_enrollment", row["id"]))
        self._verify_enrollment(db, enrollment, now)
        return enrollment

    def runner_create_intent(self, run_id):
        """Read only the pre-issued fixed intent; never accept Docker parameters."""
        with self.journal.transaction() as db:
            return self._object(db, "run", run_id)[1]

    def _phase_fresh(self, db, run_id, phase, now):
        saved = self.journal.get(db, "phase_"+phase.value, run_id)
        require(0 <= now-saved["observed_at"] <= LIMITS.api_seconds, "phase_observation_stale")

    def _runner(self, db, row, approval, signed, now, created=False):
        observed = self.verifier.verify(signed, RunnerObservation, approval.scope)
        self._fresh(observed, row["id"], approval, now)
        owned = self._ownership(db, Resource.RUNNER, row["id"])
        require((observed.container_id, observed.image_id, observed.daemon, observed.config) ==
                (owned["receipt"]["container_id"], approval.runner_image_id, approval.daemon, expected_config(approval, Resource.RUNNER))
                and observed.restart_count == 0 and not (observed.paused or observed.restarting or observed.dead), "runner_identity_or_profile_drift")
        if created:
            require(observed.state == "created" and observed.started_at is None and observed.endpoint is None, "runner_already_started")
        else:
            require(observed.state in ("running", "exited") and observed.started_at is not None, "runner_start_unconfirmed")
            if approval.authority_mode == 'live_runtime_v2' and observed.state == 'exited':
                require(observed.exit_code == 0, 'runner_exit_unconfirmed')
            require(json.loads(row["body"])["created_at"] <= datetime.fromisoformat(observed.started_at).timestamp() <= now,
                    "runner_start_time_unconfirmed")
            if observed.endpoint is not None:
                require(observed.endpoint.container_id == observed.container_id and
                        observed.endpoint.network_id == approval.network.network_id and
                        observed.endpoint.ipv4 == approval.network.runner_ipv4, "runner_network_drift")
            if self._document_exists(db, "runner_live", row["id"]):
                baseline = self.journal.get(db, "runner_live", row["id"])
                require(observed.started_at == baseline["started_at"] and
                        (observed.endpoint is not None and body(observed.endpoint) == baseline["endpoint"] or
                         observed.endpoint is None and observed.state == "exited"), "runner_runtime_generation_drift")
            else:
                require(observed.state == "running" and observed.endpoint is not None, "runner_live_endpoint_unconfirmed")
        return observed

    def check_target(self, run_id, phase, identity, network, egress, validation, runner=None):
        require(type(phase) is Phase and phase != Phase.ENROLL, "execution_phase_invalid")
        try:
            with self.journal.transaction() as db:
                row, _, approval = self._object(db, "run", run_id)
                now = self._now(db)
                self._current(db, approval, now, row)
                enrollment = self._enrollment_for_run(db, row, now)
                require(row["terminal"] is None, "execution_terminal")
                expected = {Phase.BEFORE_CREATE: "reserved", Phase.BEFORE_START: "runner_owned",
                            Phase.BEFORE_PROBE: 'running', Phase.AFTER_PROBE: "probe_recorded", Phase.BEFORE_PUBLISH: "post_checked"}
                require(phase != Phase.BEFORE_PROBE or approval.authority_mode == 'live_runtime_v2', 'live_phase_only')
                require(row["phase"] == expected[phase], "execution_phase_order_invalid")
                runner_endpoint = None
                if phase != Phase.BEFORE_CREATE:
                    actual = self._runner(db, row, approval, runner, now, created=phase == Phase.BEFORE_START)
                    runner_endpoint = actual.endpoint
                    self.journal.receipt(db, runner, run_id, phase.value+"_runner")
                checked = self._check_bundle(db, run_id, phase, approval, enrollment.target, identity, network, egress,
                                             validation, now, runner_endpoint)
                self.journal.put(db, "phase_"+phase.value, run_id, checked)
                next_phase = {Phase.BEFORE_CREATE: "checked_create", Phase.BEFORE_START: "checked_start",
                              Phase.BEFORE_PROBE: 'probe_ready', Phase.AFTER_PROBE: "post_checked", Phase.BEFORE_PUBLISH: "publish_checked"}[phase]
                db.execute("UPDATE rt_objects SET phase=? WHERE kind='run' AND id=?", (next_phase, run_id))
                self.journal.audit(db, run_id, "phase_verified", now)
        except Denied:
            self._unknown(run_id, "identity_or_authorization_unconfirmed")
            raise

    def authorize_start(self, run_id):
        with self.journal.transaction() as db:
            row, _, approval = self._object(db, "run", run_id)
            now = self._now(db)
            self._current(db, approval, now, row)
            enrollment = self._enrollment_for_run(db, row, now)
            self._phase_fresh(db, run_id, Phase.BEFORE_START, now)
            require(row["phase"] == "checked_start", "runner_start_not_authorized")
            owned = self._ownership(db, Resource.RUNNER, run_id)
            permit = StartPermit(str(uuid4()), run_id, digest(body(enrollment)), owned["receipt"]["container_id"], row["epoch"], row["deadline"])
            self.journal.put(db, "start_permit", run_id, permit)
            db.execute("UPDATE rt_objects SET phase='start_authorized' WHERE kind='run' AND id=?", (run_id,))
            self.journal.audit(db, run_id, "start_authorized", now)
            return permit

    @contextmanager
    def start_fence(self, permit):
        require(type(permit) is StartPermit, "start_permit_required")
        permit.__post_init__()
        with self.journal.transaction() as db:
            row, _, approval = self._object(db, "run", permit.run_uuid)
            now = self._now(db)
            self._current(db, approval, now, row)
            self._enrollment_for_run(db, row, now)
            self._phase_fresh(db, row["id"], Phase.BEFORE_START, now)
            require(row["phase"] == "start_authorized" and self.journal.get(db, "start_permit", row["id"]) == body(permit), "start_permit_not_issued_or_consumed")
            self.journal.put(db, "start_dispatch", row["id"], permit)
            db.execute("UPDATE rt_objects SET phase='start_requested' WHERE kind='run' AND id=?", (row["id"],))
            self.journal.audit(db, row["id"], "start_dispatch", now)
        with self.journal.transaction() as db:
            row, _, approval = self._object(db, "run", permit.run_uuid)
            self._current(db, approval, self._now(db), row)
            self._enrollment_for_run(db, row, self.clock())
            yield permit  # Future fixed bounded start only; no SDK implementation.
            db.execute("UPDATE rt_objects SET phase='start_invoked' WHERE kind='run' AND id=?", (row["id"],))

    @fail_run_closed
    def record_runner_live(self, run_id, signed):
        with self.journal.transaction() as db:
            row, _, approval = self._object(db, "run", run_id)
            now = self._now(db)
            self._current(db, approval, now, row)
            self._enrollment_for_run(db, row, now)
            require(row["phase"] == "start_invoked", "runner_start_not_invoked")
            actual = self._runner(db, row, approval, signed, now)
            self.journal.receipt(db, signed, run_id, "runner_live")
            self.journal.put(db, "runner_live", run_id, actual)
            db.execute("UPDATE rt_objects SET phase='running' WHERE kind='run' AND id=?", (run_id,))
            self.journal.audit(db, run_id, "runner_live", now)

    @fail_run_closed
    def record_probe(self, run_id, signed):
        with self.journal.transaction() as db:
            row, _, approval = self._object(db, "run", run_id)
            now = self._now(db)
            self._current(db, approval, now, row)
            enrollment = self._enrollment_for_run(db, row, now)
            require(row["phase"] == ('probe_ready' if approval.authority_mode == 'live_runtime_v2' else 'running'), "runner_runtime_unconfirmed")
            probe = self.verifier.verify(signed, ProbeResponse, approval.scope)
            self._fresh(probe, run_id, approval, now)
            runner = self._ownership(db, Resource.RUNNER, run_id)
            require((probe.runner_id, probe.runner_image_id, probe.checker_source_digest, probe.target_digest, probe.policy_digest) ==
                    (runner["receipt"]["container_id"], approval.runner_image_id, approval.checker_source_digest,
                     digest(body(enrollment.target)), approval.policy_digest), "probe_identity_mismatch")
            if probe.transport == 'refused' and approval.authority_mode == 'live_runtime_v2':
                outcome = {'result': 'failed', 'reason': 'peer_connection_refused', 'http_status': None,
                           'response_bytes': None, 'response_digest': None}
            elif probe.transport != "none":
                outcome = {"result": "unknown", "reason": "transport_uncertain", "http_status": None, "response_bytes": None, "response_digest": None}
            else:
                outcome = body(evaluate_response(HTTPResponse(probe.status, probe.body, probe.complete)))
            self.journal.receipt(db, signed, run_id, "probe")
            self.journal.put(db, "probe", run_id, {"outcome": outcome, "receipt_digest": signed.digest, "observed_at": probe.observed_at})
            db.execute("UPDATE rt_objects SET phase='probe_recorded' WHERE kind='run' AND id=?", (run_id,))
            self.journal.audit(db, run_id, "probe_recorded", now)

    def _terminal(self, db, row, result, reason, now):
        if row["terminal"] is not None:
            return json.loads(row["terminal"])
        approval = self._approval(db, json.loads(row['body'])['approval_uuid'])
        terminal = {"schema_version": approval.schema_version, "shadow_run_uuid": row["id"], "result": result, "reason": reason,
            "finished_at": now, "policy_id": approval.policy_id, "policy_version": approval.policy_version, "policy_digest": approval.policy_digest,
            "criteria_scope": "external_ipv4_http_only", "local_access": "unverified", "application_authenticity": "unproven",
            "persistence": "unverified", "execution_mode": 'live_external_peer' if approval.authority_mode == 'live_runtime_v2' else
                "offline_runtime_contract_only", "continuous_attestation": False}
        cleanup = "pending" if self._document_exists(db, "ownership_"+Resource.RUNNER.value, row["id"]) else "quarantined" if self._document_exists(db, "create_dispatch_run", row["id"]) else "not_required"
        db.execute("UPDATE rt_objects SET phase='terminal',terminal=?,cleanup=? WHERE kind='run' AND id=?", (encode(terminal), cleanup, row["id"]))
        self.journal.audit(db, row["id"], "terminal", now)
        return terminal

    @fail_run_closed
    def record_runner_finished(self, run_id, signed):
        with self.journal.transaction() as db:
            row, _, approval = self._object(db, 'run', run_id)
            now = self._now(db)
            self._current(db, approval, now, row)
            require(approval.authority_mode == 'live_runtime_v2' and row['phase'] == 'publish_checked', 'finalize_not_authorized')
            self._enrollment_for_run(db, row, now)
            actual = self._runner(db, row, approval, signed, now)
            require(actual.state == 'exited' and actual.exit_code == 0, 'runner_finish_unproven')
            self.journal.receipt(db, signed, run_id, 'runner_finished')
            self.journal.put(db, 'runner_finished', run_id, actual)

    def _unknown(self, run_id, reason):
        with self.journal.transaction() as db:
            row, _, _ = self._object(db, "run", run_id)
            return self._terminal(db, row, "unknown", reason, self._now(db))

    def publish(self, run_id):
        try:
            with self.journal.transaction() as db:
                row, _, approval = self._object(db, "run", run_id)
                if row["terminal"] is not None:
                    return json.loads(row["terminal"])
                now = self._now(db)
                self._current(db, approval, now, row)
                self._enrollment_for_run(db, row, now)
                require(row["phase"] == "publish_checked", "publication_identity_unconfirmed")
                self._phase_fresh(db, run_id, Phase.BEFORE_PUBLISH, now)
                if approval.authority_mode == 'live_runtime_v2':
                    finished = self.journal.get(db, 'runner_finished', run_id)
                    require(0 <= now-finished['observed_at'] <= LIMITS.api_seconds, 'runner_finish_stale')
                outcome = self.journal.get(db, "probe", run_id)["outcome"]
                return self._terminal(db, row, outcome["result"], outcome["reason"], now)
        except Denied:
            return self._unknown(run_id, "publication_identity_or_deadline_unconfirmed")

    def expire_run(self, run_id):
        with self.journal.transaction() as db:
            row, _, approval = self._object(db, "run", run_id)
            now = self._now(db)
            try:
                self._current(db, approval, now, row)
                self._enrollment_for_run(db, row, now)
            except Denied:
                self._terminal(db, row, "unknown", "deadline_or_cancellation", now)

    def abandon_run(self, run_id):
        return self._unknown(run_id, "execution_outcome_unknown")

    def record_cleanup(self, signed):
        require(type(signed) is Attestation and type(signed.payload) is CleanupConfirmation, "cleanup_receipt_required")
        kind = self._kind(signed.payload.resource)
        with self.journal.transaction() as db:
            row, intent, approval = self._object(db, kind, signed.payload.context_uuid)
            confirmation = self.verifier.verify(signed, CleanupConfirmation, approval.scope)
            now = self._now(db)
            self._fresh(confirmation, row["id"], approval, now)
            owned = self._ownership(db, intent.resource, row["id"])
            require(confirmation.daemon == intent.daemon and confirmation.container_id == owned["receipt"]["container_id"]
                    and confirmation.ownership_digest == owned["attestation_digest"], "cleanup_ownership_mismatch")
            require(row["terminal"] is not None if kind == "run" else row["phase"] == "quarantined", "cleanup_phase_invalid")
            require(confirmation.outcome == "removed_confirmed", "cleanup_unconfirmed")
            self.journal.receipt(db, signed, row["id"], "cleanup")
            self.journal.put(db, "cleanup_"+kind, row["id"], {"receipt_digest": signed.digest, "at": now})
            db.execute("UPDATE rt_objects SET cleanup='confirmed' WHERE kind=? AND id=?", (kind, row["id"]))
            self.journal.audit(db, row["id"], "cleanup_confirmed", now)

    def report(self, identifier, resource=Resource.RUNNER):
        kind = self._kind(resource)
        with self.journal.transaction() as db:
            row, intent, approval = self._object(db, kind, identifier)
            owned = self._ownership(db, resource, identifier) if self._document_exists(db, "ownership_"+resource.value, identifier) else None
            events = db.execute("SELECT code,at FROM rt_audit WHERE context=? ORDER BY sequence DESC LIMIT 16", (identifier,)).fetchall()
            request = self.journal.get(db, "run_request", identifier) if kind == "run" else None
            ordinary = request["ordinary"] if request else None
            enrollment = self.journal.get(db, "run_enrollment", identifier) if kind == "run" else None
            correlation = "unpaired"
            if ordinary is not None:
                if ordinary["claimed_binding_uuid"] not in (None, intent.runtime_binding_uuid):
                    correlation = "generation_mismatch"
                elif (ordinary["execution_uuid"] is not None or ordinary["check_run_id"] is not None) and ordinary["observed_at"] is not None:
                    correlation = "same_attempt_temporal"
            report = {"schema_version": approval.schema_version, "mode": approval.authority_mode, "resource": resource.value,
                "id": identifier, "approval_uuid": approval.approval_uuid, "approval_digest": approval.digest,
                "scope": approval.scope, "attempt": body(intent.attempt), "runtime_binding_uuid": intent.runtime_binding_uuid,
                "generation_uuid": intent.generation_uuid, "policy_digest": intent.policy_digest,
                "created_at": intent.created_at, "deadline": intent.deadline,
                "daemon": body(intent.daemon), "target_image_id": approval.target_image_id,
                "runner_image_id": approval.runner_image_id, "checker_source_digest": approval.checker_source_digest,
                "network_profile_digest": approval.network.digest,
                "policy_id": approval.policy_id, "policy_version": approval.policy_version,
                "runtime_enrollment_uuid": enrollment["enrollment_uuid"] if enrollment else None,
                "target_provisioning_uuid": enrollment["provisioning_uuid"] if enrollment else identifier,
                "target_snapshot": enrollment["target"] if enrollment else None,
                "ownership_receipt_digest": owned["attestation_digest"] if owned else None,
                "owned_container_id": owned["receipt"]["container_id"] if owned else None,
                "sandbox_task_ownership": "not_claimed", "phase": row["phase"], "cleanup": row["cleanup"],
                "terminal": json.loads(row["terminal"]) if row["terminal"] else None,
                "ordinary_execution_uuid": ordinary["execution_uuid"] if ordinary else None,
                "ordinary_check_run_id": ordinary["check_run_id"] if ordinary else None,
                "correlation_quality": correlation, "comparison": "incomparable",
                "criteria_scope": "external_ipv4_http_only", "local_access": "unverified",
                "application_authenticity": "unproven", "persistence": "unverified",
                "audit": [{"code": event["code"], "at": event["at"]} for event in reversed(events)]}
            require(len(encode(report).encode()) <= 16384, "operator_report_limit")
            return report
