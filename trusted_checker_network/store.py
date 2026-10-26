"""Dedicated durable offline network journal, no legacy/runtime DB writes."""
from contextlib import closing, contextmanager
from dataclasses import asdict, is_dataclass
import json
import os
from pathlib import Path
import sqlite3
from trusted_checker_runtime.profiles import require
from trusted_checker_shadow.policy import digest


def normalize(value):
    if is_dataclass(value): return normalize(asdict(value))
    if isinstance(value, dict): return {k:normalize(v) for k,v in value.items()}
    if isinstance(value, (tuple,list)): return [normalize(v) for v in value]
    return value


class NetworkStore:
    TABLES = {'meta','documents','jobs','network_state','events'}
    def __init__(self, path):
        self.path = Path(path).absolute()
        require(self.path.name.endswith('.network.sqlite3') and not self.path.is_symlink(), 'network_store_path_invalid')
        try: fd = os.open(self.path, os.O_CREAT|os.O_EXCL|os.O_WRONLY, 0o600)
        except FileExistsError:
            with closing(sqlite3.connect(self.path.as_uri()+'?mode=ro', uri=True)) as db:
                require({r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")} == self.TABLES
                        and db.execute('SELECT value FROM meta').fetchall() == [('offline-network-v3',)], 'foreign_network_store')
        else:
            os.close(fd)
            with closing(sqlite3.connect(self.path)) as db, db:
                db.executescript('''BEGIN IMMEDIATE;
                CREATE TABLE meta(value TEXT); INSERT INTO meta VALUES('offline-network-v3');
                CREATE TABLE documents(kind TEXT,id TEXT,payload TEXT,digest TEXT,PRIMARY KEY(kind,id));
                CREATE TABLE jobs(id TEXT PRIMARY KEY,approval TEXT,operation TEXT,payload_hash TEXT,
                    status TEXT,reason TEXT,receipt TEXT);
                CREATE TABLE network_state(approval TEXT PRIMARY KEY,stage TEXT,generation INTEGER,blocked INTEGER);
                CREATE TABLE events(sequence INTEGER PRIMARY KEY,job TEXT,code TEXT,UNIQUE(job,code));
                ''')
                for table in ('meta','documents','events'):
                    for action in ('UPDATE','DELETE'):
                        db.execute(f"CREATE TRIGGER {table}_{action} BEFORE {action} ON {table} BEGIN SELECT RAISE(ABORT,'immutable_network_journal'); END")
                db.execute("""CREATE TRIGGER job_binding BEFORE UPDATE ON jobs WHEN
                    NEW.id IS NOT OLD.id OR NEW.approval IS NOT OLD.approval OR NEW.operation IS NOT OLD.operation
                    OR NEW.payload_hash IS NOT OLD.payload_hash OR
                    (OLD.receipt IS NOT NULL AND (NEW.receipt IS NOT OLD.receipt OR NEW.status IS NOT OLD.status))
                    BEGIN SELECT RAISE(ABORT,'immutable_network_job'); END""")
                db.execute("CREATE TRIGGER job_delete BEFORE DELETE ON jobs BEGIN SELECT RAISE(ABORT,'immutable_network_job'); END")

    @contextmanager
    def transaction(self):
        db = sqlite3.connect(self.path, timeout=1); db.row_factory = sqlite3.Row
        try:
            db.execute('BEGIN IMMEDIATE'); yield db; db.commit()
        except BaseException: db.rollback(); raise
        finally: db.close()

    def put(self, db, kind, identifier, payload):
        payload = normalize(payload)
        raw = json.dumps(payload, sort_keys=True, separators=(',', ':'), allow_nan=False)
        require(len(raw) <= 65536, 'network_document_limit')
        old = db.execute('SELECT digest FROM documents WHERE kind=? AND id=?',(kind,identifier)).fetchone()
        if old: require(old[0] == digest(payload), 'network_document_conflict')
        else: db.execute('INSERT INTO documents VALUES(?,?,?,?)',(kind,identifier,raw,digest(payload)))

    def get(self, db, kind, identifier):
        row = db.execute('SELECT payload FROM documents WHERE kind=? AND id=?',(kind,identifier)).fetchone()
        require(row is not None, 'network_document_missing')
        return json.loads(row[0])

    def event(self, db, job, code):
        allowed = ('reserved','dispatched','owned','verified','quarantined','rollback_requested','recovered_ownership','matrix_verified')
        require(code in allowed, 'network_event_invalid')
        db.execute('INSERT OR IGNORE INTO events(job,code) VALUES(?,?)',(job,code))

    def stop(self):
        marker = self.path.with_suffix('.stop')
        try: fd = os.open(marker,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
        except FileExistsError: return
        try: os.write(fd,b'network-stop-v3\n'); os.fsync(fd)
        finally: os.close(fd)
        fd = os.open(marker.parent,os.O_RDONLY)
        try: os.fsync(fd)
        finally: os.close(fd)

    def stopped(self):
        marker = self.path.with_suffix('.stop')
        return marker.exists() or marker.is_symlink()
