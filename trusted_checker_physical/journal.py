"""Separate journal, no schema migration or access to academic/runtime writers."""
from contextlib import contextmanager,closing
from pathlib import Path
import json
import os
import sqlite3
from trusted_checker_runtime.profiles import require
from trusted_checker_shadow.policy import digest


class PhysicalJournal:
    def __init__(self,path,origin):
        self.path=Path(path).absolute();self.origin=origin
        require(origin in ('physical_linux','offline_simulation') and self.path.name.endswith('.physical.sqlite3') and
                not self.path.is_symlink(),'physical_journal_path_invalid')
        try:fd=os.open(self.path,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
        except FileExistsError:
            with closing(sqlite3.connect(self.path.as_uri()+'?mode=ro',uri=True)) as db:
                require({r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}==
                        {'meta','docs','operations','control','audit'} and
                        db.execute('SELECT marker,origin FROM meta').fetchall()==[('physical-network-v4',origin)],
                        'foreign_physical_journal')
        else:
            os.close(fd)
            with closing(sqlite3.connect(self.path)) as db,db:
                db.executescript('''BEGIN IMMEDIATE;
                CREATE TABLE meta(marker TEXT,origin TEXT);
                CREATE TABLE docs(kind TEXT,id TEXT,body TEXT,hash TEXT,PRIMARY KEY(kind,id));
                CREATE TABLE operations(id TEXT PRIMARY KEY,fingerprint TEXT,phase TEXT,receipt TEXT);
                CREATE TABLE control(id INTEGER PRIMARY KEY CHECK(id=1),stage TEXT,generation INTEGER,handles TEXT,blocked INTEGER);
                INSERT INTO control VALUES(1,'new',0,NULL,0);
                CREATE TABLE audit(id INTEGER PRIMARY KEY,context TEXT,code TEXT,UNIQUE(context,code));''')
                db.execute('INSERT INTO meta VALUES(?,?)',('physical-network-v4',origin))
                for table in ('docs','audit','meta'):
                    for action in ('UPDATE','DELETE'):
                        db.execute(f"CREATE TRIGGER {table}_{action} BEFORE {action} ON {table} BEGIN SELECT RAISE(ABORT,'immutable_physical_record'); END")
                db.execute("""CREATE TRIGGER terminal_receipt BEFORE UPDATE ON operations WHEN
                    NEW.id IS NOT OLD.id OR NEW.fingerprint IS NOT OLD.fingerprint OR
                    (OLD.receipt IS NOT NULL AND (NEW.receipt IS NOT OLD.receipt OR NEW.phase IS NOT OLD.phase))
                    BEGIN SELECT RAISE(ABORT,'immutable_physical_receipt'); END""")
                db.execute("CREATE TRIGGER op_delete BEFORE DELETE ON operations BEGIN SELECT RAISE(ABORT,'immutable_physical_intent'); END")
    @contextmanager
    def transaction(self):
        db=sqlite3.connect(self.path,timeout=1);db.row_factory=sqlite3.Row
        try:db.execute('BEGIN IMMEDIATE');yield db;db.commit()
        except BaseException:db.rollback();raise
        finally:db.close()
    def put(self,db,kind,identifier,value):
        raw=json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False)
        require(len(raw)<=262144,'physical_document_limit')
        old=db.execute('SELECT hash FROM docs WHERE kind=? AND id=?',(kind,identifier)).fetchone()
        if old:require(old[0]==digest(value),'physical_document_conflict')
        else:db.execute('INSERT INTO docs VALUES(?,?,?,?)',(kind,identifier,raw,digest(value)))
    def get(self,db,kind,identifier):
        row=db.execute('SELECT body FROM docs WHERE kind=? AND id=?',(kind,identifier)).fetchone()
        require(row is not None,'physical_document_missing');return json.loads(row[0])
    def stop(self):
        path=self.path.with_suffix('.stop')
        try:fd=os.open(path,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
        except FileExistsError:return
        try:os.write(fd,b'physical-network-v4-stop\n');os.fsync(fd)
        finally:os.close(fd)
        fd=os.open(path.parent,os.O_RDONLY)
        try:os.fsync(fd)
        finally:os.close(fd)
    def stopped(self):
        path=self.path.with_suffix('.stop');return path.exists() or path.is_symlink()
