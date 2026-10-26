"""Dedicated offline provenance journal. No legacy DB or live I/O injection."""

from contextlib import closing, contextmanager
from dataclasses import asdict, is_dataclass
import json
import os
from pathlib import Path
import sqlite3

from trusted_checker_shadow.policy import digest
from .profiles import require


def body(value):
    if is_dataclass(value):
        return body(asdict(value))
    if isinstance(value, dict):
        return {key: body(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [body(item) for item in value]
    return value


def encode(value):
    raw = json.dumps(body(value), sort_keys=True, separators=(",", ":"), allow_nan=False)
    require(len(raw.encode()) <= 32768, "journal_document_limit")
    return raw


class RuntimeJournal:
    KIND = "trusted_checker_runtime_provenance_offline_v1"
    TABLES = {"rt_meta", "rt_control", "rt_documents", "rt_objects", "rt_requests", "rt_claims",
              "rt_revocations", "rt_ownership", "rt_receipts", "rt_audit"}
    CODES = {"approval_registered", "enabled", "disabled", "intent_recorded", "create_requested", "create_dispatch",
             "ownership_recorded", "quarantined", "identity_verified", "enrolled", "run_reserved", "phase_verified",
             "start_authorized", "start_dispatch", "runner_live", "probe_recorded", "terminal", "revoked", "cleanup_confirmed"}

    def __init__(self, path, *, live=False):
        require(type(live) is bool, 'journal_mode_invalid')
        self.live = live
        self.kind = 'trusted_checker_live_runtime_v2' if live else self.KIND
        self.version = 2 if live else 1
        self.path = Path(path).absolute()
        require(self.path.name.endswith(".runtime.sqlite3") and not self.path.is_symlink(), "dedicated_runtime_journal_required")
        try:
            fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            with closing(sqlite3.connect(self.path.as_uri()+"?mode=ro", uri=True)) as db:
                require({r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")} == self.TABLES,
                        "foreign_database_rejected")
                require(db.execute("SELECT kind,version FROM rt_meta").fetchall() == [(self.kind, self.version)], "foreign_database_rejected")
        else:
            os.close(fd)
            with closing(sqlite3.connect(self.path)) as db, db:
                db.executescript("""
                    BEGIN IMMEDIATE;
                    CREATE TABLE rt_meta(kind TEXT NOT NULL,version INTEGER NOT NULL);
                    CREATE TABLE rt_control(id INTEGER PRIMARY KEY CHECK(id=1),enabled INTEGER NOT NULL CHECK(enabled IN(0,1)),
                        epoch INTEGER NOT NULL,clock_highwater REAL NOT NULL);
                    INSERT INTO rt_control VALUES(1,0,0,0);
                    CREATE TABLE rt_documents(kind TEXT NOT NULL,id TEXT NOT NULL,body TEXT NOT NULL,digest TEXT NOT NULL,
                        PRIMARY KEY(kind,id));
                    CREATE TABLE rt_objects(kind TEXT NOT NULL,id TEXT NOT NULL,body TEXT NOT NULL,fingerprint TEXT NOT NULL,
                        phase TEXT NOT NULL,cleanup TEXT NOT NULL,epoch INTEGER NOT NULL,deadline REAL NOT NULL,
                        terminal TEXT,PRIMARY KEY(kind,id));
                    CREATE TABLE rt_requests(kind TEXT NOT NULL,id TEXT NOT NULL,fingerprint TEXT NOT NULL,object_id TEXT NOT NULL,
                        PRIMARY KEY(kind,id));
                    CREATE TABLE rt_claims(kind TEXT NOT NULL,canonical TEXT NOT NULL,object_id TEXT NOT NULL,
                        fingerprint TEXT NOT NULL,PRIMARY KEY(kind,canonical));
                    CREATE TABLE rt_revocations(kind TEXT NOT NULL,id TEXT NOT NULL,at REAL NOT NULL,PRIMARY KEY(kind,id));
                    CREATE TABLE rt_ownership(domain TEXT NOT NULL,resource_id TEXT NOT NULL,container_id TEXT NOT NULL,
                        daemon_digest TEXT NOT NULL,receipt_id TEXT NOT NULL,digest TEXT NOT NULL,
                        PRIMARY KEY(domain,resource_id),UNIQUE(daemon_digest,container_id));
                    CREATE TABLE rt_receipts(id TEXT PRIMARY KEY,digest TEXT NOT NULL,context TEXT NOT NULL,purpose TEXT NOT NULL);
                    CREATE TABLE rt_audit(sequence INTEGER PRIMARY KEY,context TEXT NOT NULL,code TEXT NOT NULL,at REAL NOT NULL,
                        UNIQUE(context,code,at));
                """)
                db.execute("INSERT INTO rt_meta VALUES(?,?)", (self.kind, self.version))
                for table in self.TABLES - {"rt_control", "rt_objects"}:
                    for action in ("UPDATE", "DELETE"):
                        db.execute(f"CREATE TRIGGER {table}_no_{action.lower()} BEFORE {action} ON {table} "
                                   "BEGIN SELECT RAISE(ABORT,'append_only_runtime_provenance'); END")
                db.execute("""CREATE TRIGGER rt_object_no_delete BEFORE DELETE ON rt_objects
                    BEGIN SELECT RAISE(ABORT,'runtime_history_immutable'); END""")
                db.execute("""CREATE TRIGGER rt_binding_immutable BEFORE UPDATE ON rt_objects
                    WHEN NEW.kind IS NOT OLD.kind OR NEW.id IS NOT OLD.id OR NEW.body IS NOT OLD.body
                      OR NEW.fingerprint IS NOT OLD.fingerprint OR NEW.epoch IS NOT OLD.epoch OR NEW.deadline IS NOT OLD.deadline
                    BEGIN SELECT RAISE(ABORT,'runtime_binding_immutable'); END""")
                db.execute("""CREATE TRIGGER rt_terminal_immutable BEFORE UPDATE ON rt_objects
                    WHEN OLD.terminal IS NOT NULL AND (NEW.terminal IS NOT OLD.terminal OR NEW.phase IS NOT OLD.phase)
                    BEGIN SELECT RAISE(ABORT,'runtime_terminal_immutable'); END""")

    @contextmanager
    def transaction(self):
        db = sqlite3.connect(self.path, timeout=1)
        db.row_factory = sqlite3.Row
        try:
            db.execute("BEGIN IMMEDIATE")
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def request_stop(self):
        """Irreversible per-journal live stop latch, independent of DB busy locks.

        A killed live journal is recovery-only. It is never silently re-enabled.
        """
        marker = self.path.with_suffix(self.path.suffix+'.stop')
        try:
            fd = os.open(marker, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            fd = None
        if fd is not None:
            try:
                os.write(fd, b'live-stop-v2\n')
                os.fsync(fd)
            finally:
                os.close(fd)
            folder = os.open(marker.parent, os.O_RDONLY)
            try:
                os.fsync(folder)
            finally:
                os.close(folder)

    def stop_requested(self):
        marker = self.path.with_suffix(self.path.suffix+'.stop')
        return marker.exists() or marker.is_symlink()

    def put(self, db, kind, identifier, value):
        raw, fingerprint = encode(value), digest(body(value))
        old = db.execute("SELECT digest FROM rt_documents WHERE kind=? AND id=?", (kind, identifier)).fetchone()
        if old:
            require(old[0] == fingerprint, "immutable_document_conflict")
            return
        db.execute("INSERT INTO rt_documents VALUES(?,?,?,?)", (kind, identifier, raw, fingerprint))

    def get(self, db, kind, identifier):
        row = db.execute("SELECT body FROM rt_documents WHERE kind=? AND id=?", (kind, identifier)).fetchone()
        require(row is not None, "provenance_document_missing")
        return json.loads(row[0])

    def audit(self, db, context, code, now):
        require(code in self.CODES, "audit_code_invalid")
        db.execute("INSERT OR IGNORE INTO rt_audit(context,code,at) VALUES(?,?,?)", (context, code, now))

    def receipt(self, db, signed, context, purpose):
        payload = signed.payload
        identifier = payload.approval_uuid if hasattr(payload, "approval_uuid") else payload.receipt_uuid
        old = db.execute("SELECT * FROM rt_receipts WHERE id=?", (identifier,)).fetchone()
        if old:
            require((old["digest"], old["context"], old["purpose"]) == (signed.digest, context, purpose), "receipt_replay_conflict")
        else:
            db.execute("INSERT INTO rt_receipts VALUES(?,?,?,?)", (identifier, signed.digest, context, purpose))

    def ownership(self, db, resource, identifier, signed):
        receipt = signed.payload
        self.put(db, "ownership_"+resource.value, identifier, {"receipt": body(receipt), "attestation_digest": signed.digest})
        db.execute("INSERT INTO rt_ownership VALUES(?,?,?,?,?,?)", (resource.value, identifier, receipt.container_id,
                   digest(body(receipt.daemon)), receipt.receipt_uuid, signed.digest))
