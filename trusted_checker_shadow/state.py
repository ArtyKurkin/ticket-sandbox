"""Dedicated SQLite state: atomic mapping BEFORE issue; no Django DB connection.

The local process, database owner and fake authority are trusted. SQL triggers
defend accidental mutation, not a hostile process with write access to this file.
"""

from contextlib import closing, contextmanager
from dataclasses import asdict
import json
import os
from pathlib import Path
import sqlite3
from uuid import uuid4

from .backend import ExecutionTicket
from .comparison import compare
from .contracts import (CreationProvenance, OperatorRequest, OrdinaryEvidence,
                        ProbeResult, Reason, RuntimeObservation, TargetIdentity, Verdict, atom, instant,
                        require)
from .evidence import AuditEvent, OperatorReport
from .policy import POLICY, PeerPolicy, digest


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


class ShadowStore:
    MARKER = "trusted_checker_shadow_offline_v1"
    TABLES = {"shadow_meta", "shadow_control", "shadow_runs", "shadow_requests", "shadow_audit", "shadow_control_audit"}
    EVENTS = {"reserved", "issue_requested", "issue_dispatched", "issued", "issue_unknown", "start_requested",
              "terminal", "cleanup_confirmed", "cleanup_unresolved", "expired", "killed"}

    def __init__(self, path):
        path = Path(path).absolute()
        require(path.name.endswith(".shadow.sqlite3") and not path.is_symlink(), "dedicated_shadow_path_required")
        self.path = path
        created = False
        try:
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            # Read-only inspection BEFORE any initialization/mutation of an existing file.
            with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)) as db:
                tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                require(tables == self.TABLES, "foreign_database_rejected")
                require(db.execute("SELECT kind,version FROM shadow_meta").fetchall() == [(self.MARKER, 1)],
                        "foreign_database_rejected")
        else:
            os.close(fd)
            created = True
        if created:
            with closing(sqlite3.connect(self.path)) as db, db:
                db.executescript("""
                    BEGIN IMMEDIATE;
                    CREATE TABLE shadow_meta(kind TEXT NOT NULL, version INTEGER NOT NULL);
                    CREATE TABLE shadow_control(id INTEGER PRIMARY KEY CHECK(id=1),
                        enabled INTEGER NOT NULL CHECK(enabled IN (0,1)), epoch INTEGER NOT NULL);
                    INSERT INTO shadow_control VALUES(1,0,0);
                    CREATE TABLE shadow_runs(
                        id TEXT PRIMARY KEY, canonical_key TEXT NOT NULL UNIQUE,
                        fingerprint TEXT NOT NULL, operator_id TEXT NOT NULL,
                        enrollment TEXT NOT NULL, request TEXT NOT NULL, policy TEXT NOT NULL,
                        execution_id TEXT NOT NULL UNIQUE, epoch INTEGER NOT NULL,
                        lifecycle TEXT NOT NULL CHECK(lifecycle IN ('reserved','issuing','issued','running','terminal')),
                        created_at REAL NOT NULL, started_at REAL, finished_at REAL,
                        observed_from REAL, observed_until REAL, observed_before TEXT, observed_after TEXT,
                        deadline REAL NOT NULL,
                        result TEXT, cleanup TEXT NOT NULL CHECK(cleanup IN ('not_required','pending','confirmed','quarantined')),
                        unresolved INTEGER NOT NULL CHECK(unresolved IN (0,1)));
                    CREATE TABLE shadow_requests(operator_id TEXT NOT NULL, request_id TEXT NOT NULL,
                        fingerprint TEXT NOT NULL, run_id TEXT NOT NULL REFERENCES shadow_runs(id),
                        PRIMARY KEY(operator_id,request_id));
                    CREATE TABLE shadow_audit(sequence INTEGER PRIMARY KEY, run_id TEXT NOT NULL REFERENCES shadow_runs(id),
                        code TEXT NOT NULL, occurred_at REAL NOT NULL, UNIQUE(run_id,code));
                    CREATE TABLE shadow_control_audit(sequence INTEGER PRIMARY KEY,
                        operator_id TEXT NOT NULL, enabled INTEGER NOT NULL, epoch INTEGER NOT NULL, occurred_at REAL NOT NULL);
                """)
                db.execute("INSERT INTO shadow_meta VALUES(?,1)", (self.MARKER,))
                for table in ("shadow_meta", "shadow_requests", "shadow_audit", "shadow_control_audit"):
                    for action in ("UPDATE", "DELETE"):
                        db.execute(f"CREATE TRIGGER {table}_no_{action.lower()} BEFORE {action} ON {table} "
                                   "BEGIN SELECT RAISE(ABORT,'append_only_shadow_record'); END")
                # Do not use executescript again: it would implicitly commit the
                # initialization before all guards exist. The outer context
                # commits marker, schema and triggers together.
                for statement in (
                    """CREATE TRIGGER shadow_run_no_delete BEFORE DELETE ON shadow_runs
                    BEGIN SELECT RAISE(ABORT,'shadow_history_immutable'); END""",
                    """CREATE TRIGGER shadow_binding_immutable BEFORE UPDATE ON shadow_runs
                    WHEN NEW.id IS NOT OLD.id OR NEW.canonical_key IS NOT OLD.canonical_key
                      OR NEW.fingerprint IS NOT OLD.fingerprint OR NEW.operator_id IS NOT OLD.operator_id
                      OR NEW.enrollment IS NOT OLD.enrollment OR NEW.request IS NOT OLD.request OR NEW.policy IS NOT OLD.policy
                      OR NEW.execution_id IS NOT OLD.execution_id OR NEW.epoch IS NOT OLD.epoch
                      OR NEW.deadline IS NOT OLD.deadline OR NEW.created_at IS NOT OLD.created_at
                    BEGIN SELECT RAISE(ABORT,'shadow_binding_immutable'); END""",
                    """CREATE TRIGGER shadow_terminal_immutable BEFORE UPDATE ON shadow_runs
                    WHEN OLD.lifecycle='terminal' AND (NEW.result IS NOT OLD.result
                      OR NEW.lifecycle IS NOT OLD.lifecycle OR NEW.finished_at IS NOT OLD.finished_at
                      OR NEW.started_at IS NOT OLD.started_at OR NEW.observed_from IS NOT OLD.observed_from
                      OR NEW.observed_until IS NOT OLD.observed_until
                      OR NEW.observed_before IS NOT OLD.observed_before OR NEW.observed_after IS NOT OLD.observed_after)
                    BEGIN SELECT RAISE(ABORT,'shadow_terminal_immutable'); END""",
                ):
                    db.execute(statement)

    @contextmanager
    def _db(self):
        db = sqlite3.connect(self.path, timeout=1)
        db.row_factory = sqlite3.Row
        try:
            db.execute("PRAGMA foreign_keys=ON")
            db.execute("BEGIN IMMEDIATE")
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def _audit(self, db, run_id, code, now):
        require(code in self.EVENTS, "audit_code_invalid")
        db.execute("INSERT OR IGNORE INTO shadow_audit(run_id,code,occurred_at) VALUES(?,?,?)",
                   (run_id, code, now))

    def set_enabled(self, enabled, *, operator_id, now):
        atom(operator_id, "operator-")
        instant(now)
        require(type(enabled) is bool, "flag_invalid")
        with self._db() as db:
            db.execute("UPDATE shadow_control SET enabled=?,epoch=epoch+1 WHERE id=1", (int(enabled),))
            epoch = db.execute("SELECT epoch FROM shadow_control").fetchone()[0]
            db.execute("INSERT INTO shadow_control_audit(operator_id,enabled,epoch,occurred_at) VALUES(?,?,?,?)",
                       (operator_id, int(enabled), epoch, now))

    def reserve(self, request, enrollment, operator_id, now, max_parallel):
        require(type(request) is OperatorRequest, "request_schema_invalid")
        request.__post_init__()
        payload = request.payload()
        enrollment_body = asdict(enrollment)
        fingerprint = digest({"request": payload, "enrollment": enrollment_body, "operator": operator_id})
        ordinary = request.ordinary
        canonical = digest({"enrollment": digest(enrollment_body), "policy": POLICY.digest,
                            "slot": request.sample_slot, "check_run": ordinary.check_run_id if ordinary else None,
                            "ordinary_execution": ordinary.technical_execution_uuid if ordinary else None})
        with self._db() as db:
            alias = db.execute("SELECT * FROM shadow_requests WHERE operator_id=? AND request_id=?",
                               (operator_id, request.request_uuid)).fetchone()
            if alias:
                require(alias["fingerprint"] == fingerprint, "request_payload_conflict")
                return alias["run_id"], False
            old = db.execute("SELECT id,fingerprint FROM shadow_runs WHERE canonical_key=?", (canonical,)).fetchone()
            if old:
                require(old["fingerprint"] == fingerprint, "canonical_payload_conflict")
                run_id, created = old["id"], False
            else:
                control = db.execute("SELECT * FROM shadow_control").fetchone()
                require(control["enabled"] == 1, "feature_disabled")
                require(now < request.deadline <= now + POLICY.run_timeout_seconds, "deadline_invalid")
                require(not db.execute("SELECT 1 FROM shadow_runs WHERE unresolved=1 OR "
                                       "(lifecycle='terminal' AND cleanup IN ('pending','quarantined'))").fetchone(),
                        "circuit_open")
                active = db.execute("SELECT enrollment FROM shadow_runs WHERE lifecycle!='terminal'").fetchall()
                require(len(active) < max_parallel, "capacity_exhausted")
                require(not any(json.loads(r[0])["target"]["runtime_binding_uuid"] ==
                                enrollment.target.runtime_binding_uuid for r in active), "target_busy")
                run_id, execution_id = str(uuid4()), str(uuid4())
                # The complete mapping is durably committed BEFORE backend.issue.
                db.execute("""INSERT INTO shadow_runs(id,canonical_key,fingerprint,operator_id,enrollment,request,policy,
                    execution_id,epoch,lifecycle,created_at,deadline,cleanup,unresolved)
                    VALUES(?,?,?,?,?,?,?,?,?, 'reserved',?,?, 'not_required',0)""",
                    (run_id, canonical, fingerprint, operator_id, encoded(enrollment_body), encoded(payload),
                     encoded(asdict(POLICY)), execution_id, control["epoch"], now, request.deadline))
                self._audit(db, run_id, "reserved", now)
                created = True
            db.execute("INSERT INTO shadow_requests VALUES(?,?,?,?)",
                       (operator_id, request.request_uuid, fingerprint, run_id))
            return run_id, created

    def _row(self, db, run_id, operator_id):
        row = db.execute("SELECT * FROM shadow_runs WHERE id=? AND operator_id=?", (run_id, operator_id)).fetchone()
        require(row is not None, "run_not_authorized")
        return row

    def _ticket(self, row):
        enrollment = json.loads(row["enrollment"])
        policy = PeerPolicy(**json.loads(row["policy"]))
        require(policy.digest == enrollment["policy_digest"], "policy_snapshot_mismatch")
        return ExecutionTicket(row["id"], row["execution_id"], digest(enrollment),
                               enrollment["policy_digest"], TargetIdentity(**enrollment["target"]))

    def _matched(self, db, ticket):
        require(type(ticket) is ExecutionTicket, "ticket_invalid")
        ticket.__post_init__()
        row = db.execute("SELECT * FROM shadow_runs WHERE id=?", (ticket.run_uuid,)).fetchone()
        require(row is not None and self._ticket(row) == ticket, "execution_receipt_mismatch")
        return row

    def _terminal(self, db, row, result, now, event="terminal"):
        if row["lifecycle"] == "terminal":
            return False
        require(type(result) is ProbeResult, "result_schema_invalid")
        result.__post_init__()
        db.execute("UPDATE shadow_runs SET lifecycle='terminal',result=?,finished_at=? WHERE id=?",
                   (encoded(asdict(result)), now, row["id"]))
        self._audit(db, row["id"], event, now)
        return True

    def _gate(self, db, row, now):
        if row["lifecycle"] == "terminal":
            return False
        control = db.execute("SELECT * FROM shadow_control").fetchone()
        reason = (Reason.DEADLINE if now >= row["deadline"] else
                  Reason.KILLED if not control["enabled"] or control["epoch"] != row["epoch"] else None)
        if reason:
            self._terminal(db, row, ProbeResult(Verdict.UNKNOWN, reason), now,
                           "expired" if reason == Reason.DEADLINE else "killed")
            return False
        return True

    def claim_issue(self, run_id, operator_id, now):
        with self._db() as db:
            row = self._row(db, run_id, operator_id)
            if not self._gate(db, row, now) or row["lifecycle"] != "reserved":
                return None
            db.execute("UPDATE shadow_runs SET lifecycle='issuing',cleanup='quarantined',unresolved=1 WHERE id=?", (run_id,))
            self._audit(db, run_id, "issue_requested", now)
            return self._ticket(row)

    def dispatch_issue(self, ticket, backend, clock):
        from .backend import FakeExecutionBackend, IssueReceipt
        require(type(backend) is FakeExecutionBackend, "fake_backend_required")
        # A durable dispatch intent makes even a direct retry of this internal
        # method non-reissuing after process loss. Missing acknowledgment is not
        # permission to send another issue.
        with self._db() as db:
            row = self._matched(db, ticket)
            if row["lifecycle"] != "issuing" or db.execute(
                "SELECT 1 FROM shadow_audit WHERE run_id=? AND code='issue_dispatched'", (row["id"],)
            ).fetchone():
                return False
            self._audit(db, row["id"], "issue_dispatched", clock())
        with self._db() as db:
            row = self._matched(db, ticket)
            if row["lifecycle"] != "issuing":
                return False
            now = clock()
            if not self._gate(db, row, now):
                # No issue call was made; the earlier intent is safely closed.
                db.execute("UPDATE shadow_runs SET cleanup='not_required',unresolved=0 WHERE id=?", (row["id"],))
                return False
            require(row["lifecycle"] == "issuing", "issue_phase_invalid")
            try:
                receipt = backend.issue(ticket)
                require(type(receipt) is IssueReceipt and receipt.ticket == ticket, "issue_receipt_mismatch")
            except Exception:
                self._terminal(db, row, ProbeResult(Verdict.UNKNOWN, Reason.ISSUE), clock(), "issue_unknown")
                return False
            db.execute("UPDATE shadow_runs SET cleanup='not_required',unresolved=0 WHERE id=?", (row["id"],))
            if not self._gate(db, row, clock()):
                return False
            db.execute("UPDATE shadow_runs SET lifecycle='issued' WHERE id=?", (row["id"],))
            self._audit(db, row["id"], "issued", clock())
            return True

    def start(self, ticket, backend, clock):
        # Persist the ambiguous-create boundary BEFORE invoking the fake backend.
        # The second short transaction serializes the final flag check/start with
        # kill switch. A process crash rolls back only that second transaction;
        # the committed pending intent remains, so recovery cannot invent absence.
        from .backend import FakeExecutionBackend
        require(type(backend) is FakeExecutionBackend, "fake_backend_required")
        with self._db() as db:
            row = self._matched(db, ticket)
            now = clock()
            if not self._gate(db, row, now) or row["lifecycle"] != "issued":
                return False
            db.execute("UPDATE shadow_runs SET lifecycle='running',started_at=?,observed_from=?,"
                       "cleanup='pending',unresolved=1 WHERE id=?", (now, now, row["id"]))
            self._audit(db, row["id"], "start_requested", now)
        with self._db() as db:
            row = self._matched(db, ticket)
            now = clock()
            if not self._gate(db, row, now):
                db.execute("UPDATE shadow_runs SET cleanup='not_required',unresolved=0 WHERE id=?", (row["id"],))
                return False
            try:
                backend.start(ticket)
            except Exception:
                row = db.execute("SELECT * FROM shadow_runs WHERE id=?", (row["id"],)).fetchone()
                self._terminal(db, row, ProbeResult(Verdict.UNKNOWN, Reason.INFRASTRUCTURE), now)
                db.execute("UPDATE shadow_runs SET cleanup='quarantined' WHERE id=?", (row["id"],))
                return False
            # Start intent persists even if the process subsequently crashes.
            return True

    def finish(self, ticket, result, clock, *, before=None, after=None):
        for observation in (before, after):
            if observation is not None:
                require(type(observation) is RuntimeObservation, "runtime_observation_invalid")
                observation.__post_init__()
        with self._db() as db:
            row = self._matched(db, ticket)
            now = clock()
            if row["lifecycle"] == "terminal":
                return False
            require(row["lifecycle"] == "running", "execution_phase_invalid")
            db.execute("UPDATE shadow_runs SET observed_until=?,observed_before=?,observed_after=? WHERE id=?",
                       (now, encoded(asdict(before)) if before else None,
                        encoded(asdict(after)) if after else None, row["id"]))
            if not self._gate(db, row, now):
                return False
            return self._terminal(db, row, result, now)

    def confirm_cleanup(self, ticket, now):
        with self._db() as db:
            row = self._matched(db, ticket)
            require(row["lifecycle"] == "terminal" and row["started_at"] is not None, "cleanup_phase_invalid")
            db.execute("UPDATE shadow_runs SET cleanup='confirmed',unresolved=0 WHERE id=?", (row["id"],))
            self._audit(db, row["id"], "cleanup_confirmed", now)

    def expire(self, run_id, operator_id, now):
        with self._db() as db:
            row = self._row(db, run_id, operator_id)
            self._gate(db, row, now)

    def ticket_for_cleanup(self, run_id, operator_id):
        with self._db() as db:
            row = self._row(db, run_id, operator_id)
            require(row["lifecycle"] == "terminal" and row["started_at"] is not None, "cleanup_phase_invalid")
            return self._ticket(row)

    def report(self, run_id, operator_id):
        with self._db() as db:
            row = self._row(db, run_id, operator_id)
            events = db.execute("SELECT sequence,code,occurred_at FROM shadow_audit WHERE run_id=? ORDER BY sequence DESC LIMIT 16",
                                (run_id,)).fetchall()
            count = db.execute("SELECT COUNT(*) FROM shadow_audit WHERE run_id=?", (run_id,)).fetchone()[0]
        enrollment = json.loads(row["enrollment"])
        policy = PeerPolicy(**json.loads(row["policy"]))
        require(policy.digest == enrollment["policy_digest"], "policy_snapshot_mismatch")
        target = TargetIdentity(**enrollment["target"])
        request = json.loads(row["request"])
        ordinary = request["ordinary"]
        if ordinary is not None:
            ordinary = OrdinaryEvidence(**{**ordinary, "result": Verdict(ordinary["result"])})
        result = json.loads(row["result"]) if row["result"] else None
        if result is not None:
            result = ProbeResult(**{**result, "result": Verdict(result["result"]), "reason": Reason(result["reason"])})
        observations = []
        for name in ("observed_before", "observed_after"):
            body = json.loads(row[name]) if row[name] else None
            observations.append(RuntimeObservation(**{**body, "target": TargetIdentity(**body["target"])}) if body else None)
        report = OperatorReport(
            shadow_run_uuid=row["id"], execution_uuid=row["execution_id"], canonical_idempotency_key=row["canonical_key"],
            enrollment_uuid=enrollment["enrollment_uuid"], authority_id=enrollment["authority_id"],
            operator_id=row["operator_id"], target=target, provenance=CreationProvenance(**enrollment["provenance"]),
            policy=policy, ordinary=ordinary, lifecycle=row["lifecycle"], verdict=result, cleanup_state=row["cleanup"],
            unresolved=bool(row["unresolved"]), created_at=row["created_at"], started_at=row["started_at"],
            finished_at=row["finished_at"], observed_from=row["observed_from"], observed_until=row["observed_until"],
            deadline=row["deadline"], comparison=compare(ordinary, target, result.result if result else Verdict.UNKNOWN,
                                                        row["observed_from"], row["observed_until"]),
            diagnostics=tuple(AuditEvent(*event) for event in reversed(events)), audit_event_count=count,
            policy_digest=policy.digest, sample_slot=request["sample_slot"],
            observed_before=observations[0], observed_after=observations[1])
        report.to_dict()
        return report
