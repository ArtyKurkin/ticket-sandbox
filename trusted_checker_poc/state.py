"""Standalone SQLite receipts. Fail closed across processes and broker restarts."""
from contextlib import contextmanager
import json
import os
import sqlite3
import secrets
import time
from dataclasses import asdict
from uuid import uuid4
from .contracts import InvalidRequest, Request, Target, timestamp, full_id, digest


class State:
    def __init__(self, path):
        self.path = str(path)
        if self.path == ':memory:':
            raise ValueError('durable_path_required')
        with self.db() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS targets(id TEXT PRIMARY KEY, body TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS runs(
                    id TEXT PRIMARY KEY, owner TEXT NOT NULL, request TEXT NOT NULL,
                    target TEXT NOT NULL, requested_at TEXT NOT NULL, policy TEXT,
                    status TEXT NOT NULL, deadline REAL, started_at TEXT,
                    runner TEXT, result TEXT);
                CREATE TABLE IF NOT EXISTS locks(target_id TEXT PRIMARY KEY, run_id TEXT UNIQUE NOT NULL);
                CREATE TABLE IF NOT EXISTS create_intents(run_id TEXT PRIMARY KEY, body TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS runner_ownership(
                    run_id TEXT PRIMARY KEY, container_id TEXT UNIQUE NOT NULL, body TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS recovery_audit(id TEXT PRIMARY KEY, run_id TEXT NOT NULL, body TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS runner_starts(run_id TEXT PRIMARY KEY, body TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS cleanups(run_id TEXT PRIMARY KEY, finished_at TEXT NOT NULL);
            ''')
            for table in ('create_intents', 'runner_ownership', 'recovery_audit', 'runner_starts', 'cleanups'):
                for operation in ('UPDATE', 'DELETE'):
                    db.execute(f"CREATE TRIGGER IF NOT EXISTS {table}_no_{operation.lower()} BEFORE {operation} ON {table} "
                               "BEGIN SELECT RAISE(ABORT, 'append_only_receipt'); END")

    @contextmanager
    def db(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        try:
            db.execute('PRAGMA busy_timeout=10000')
            db.execute('BEGIN IMMEDIATE')
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def enroll(self, target):
        """Operator-only fixture enrollment, not a public request method."""
        target.validate()
        with self.db() as db:
            db.execute('INSERT INTO targets VALUES (?,?)', (target.container_id, json.dumps(asdict(target))))

    def issue(self, target_id, owner, policy_id, policy=None):
        with self.db() as db:
            row = db.execute('SELECT body FROM targets WHERE id=?', (target_id,)).fetchone()
            if not row:
                raise InvalidRequest('target_not_enrolled')
            target = Target(**json.loads(row['body']))
            if owner != target.owner:
                raise InvalidRequest('owner_mismatch')
            request = Request(str(uuid4()), policy_id, target_id, target.generation, target.synthetic_task_id)
            db.execute('INSERT INTO runs(id,owner,request,target,requested_at,status,policy) VALUES (?,?,?,?,?,?,?)',
                       (request.run_id, owner, json.dumps(asdict(request)), row['body'], timestamp(), 'issued', json.dumps(policy)))
            return request

    def read(self, run_id):
        with self.db() as db:
            row = db.execute('SELECT * FROM runs WHERE id=?', (run_id,)).fetchone()
            return dict(row) if row else None

    def admit(self, request, owner, limit, deadline):
        with self.db() as db:
            row = db.execute('SELECT * FROM runs WHERE id=?', (request.run_id,)).fetchone()
            if not row or row['owner'] != owner or json.loads(row['request']) != asdict(request):
                raise InvalidRequest('unissued_or_conflicting_request')
            if row['status'] != 'issued':
                return row['status']
            if db.execute('SELECT 1 FROM locks WHERE target_id=?', (request.target_id,)).fetchone():
                return 'target_busy'
            if db.execute('SELECT COUNT(*) FROM locks').fetchone()[0] >= limit:
                return 'capacity_exhausted'
            db.execute('INSERT INTO locks VALUES (?,?)', (request.target_id, request.run_id))
            db.execute("UPDATE runs SET status='running', deadline=?, started_at=? WHERE id=?", (deadline, timestamp(), request.run_id))
            return 'admitted'

    def register_runner(self, run_id, runner):
        with self.db() as db:
            ownership = db.execute('SELECT container_id FROM runner_ownership WHERE run_id=?', (run_id,)).fetchone()
            if ownership and ownership['container_id'] != runner.container_id:
                return False
            return db.execute("UPDATE runs SET runner=? WHERE id=? AND status='running' AND runner IS NULL AND deadline>?",
                              (json.dumps(asdict(runner)), run_id, time.time())).rowcount == 1

    def receipt(self, table, run_id):
        if table not in ('create_intents', 'runner_ownership'):
            raise ValueError('invalid_receipt_table')
        with self.db() as db:
            row = db.execute(f'SELECT body FROM {table} WHERE run_id=?', (run_id,)).fetchone()
            return json.loads(row['body']) if row else None

    def create_intent(self, run_id, daemon_id, integration_id, challenge):
        with self.db() as db:
            row = db.execute('SELECT * FROM runs WHERE id=?', (run_id,)).fetchone()
            if row and row['deadline'] is not None and row['deadline'] <= time.time():
                raise InvalidRequest('runner_deadline_exceeded')
            if not row or row['status'] != 'running':
                raise InvalidRequest('execution_cancelled')
            if db.execute('SELECT 1 FROM create_intents WHERE run_id=?', (run_id,)).fetchone():
                raise InvalidRequest('create_already_requested')
            target, policy = json.loads(row['target']), json.loads(row['policy'])
            body = {'schema_version': 1, 'intent_id': str(uuid4()), 'run_id': run_id,
                    'integration_id': integration_id, 'daemon_id': daemon_id,
                    'generation': str(uuid4()), 'token': secrets.token_hex(32),
                    'scope': target['scope'], 'target_id': target['container_id'],
                    'target_generation': target['generation'], 'network_id': target['network_id'],
                    'image_id': policy['runner_image_id'], 'policy_digest': digest(policy),
                    'challenge_digest': digest(challenge), 'created_at': timestamp(),
                    'created_epoch': time.time(), 'deadline': row['deadline']}
            db.execute('INSERT INTO create_intents VALUES (?,?)', (run_id, json.dumps(body)))
            return body

    def own_runner(self, run_id, runner, *, daemon_id, integration_id, source, intent_id=None):
        """Trusted create-response/reconciliation boundary; never an internet API.

        Immutable ownership is independent of running/finished and config trust.
        This method never enables execution or modifies a technical receipt.
        """
        if not full_id(runner.container_id):
            raise InvalidRequest('invalid_runner_identity')
        with self.db() as db:
            row = db.execute('SELECT * FROM runs WHERE id=?', (run_id,)).fetchone()
            if not row:
                raise InvalidRequest('run_missing')
            target, policy = json.loads(row['target']), json.loads(row['policy'])
            if (runner.run_id != run_id or runner.scope != target['scope'] or
                    runner.image_id != policy['runner_image_id']):
                raise InvalidRequest('ownership_binding_mismatch')
            intent_row = db.execute('SELECT body FROM create_intents WHERE run_id=?', (run_id,)).fetchone()
            if intent_row:
                intent = json.loads(intent_row['body'])
                if (intent_id != intent['intent_id'] or daemon_id != intent['daemon_id'] or
                        integration_id != intent['integration_id']):
                    raise InvalidRequest('ownership_intent_mismatch')
            elif intent_id is not None or source.get('kind') != 'legacy_journal_and_daemon_create':
                raise InvalidRequest('ownership_intent_missing')
            if row['runner'] and json.loads(row['runner'])['container_id'] != runner.container_id:
                raise InvalidRequest('ownership_conflict')
            previous = db.execute('SELECT body FROM runner_ownership WHERE run_id=?', (run_id,)).fetchone()
            if previous:
                body = json.loads(previous['body'])
                if (body['container_id'] != runner.container_id or body['daemon_id'] != daemon_id or
                        body['integration_id'] != integration_id or body['intent_id'] != intent_id):
                    raise InvalidRequest('ownership_conflict')
                return body
            body = {'run_id': run_id, 'container_id': runner.container_id, 'image_id': runner.image_id,
                    'scope': runner.scope, 'daemon_id': daemon_id, 'integration_id': integration_id,
                    'intent_id': intent_id, 'received_at': timestamp(), 'source': source}
            db.execute('INSERT INTO runner_ownership VALUES (?,?,?)', (run_id, runner.container_id, json.dumps(body)))
            return body

    def start_once(self, run_id, callback):
        """Serialize start invocation against finish, including other processes.

        Only this bounded SDK call holds the SQLite write lock. If it has already
        been sent to Docker, cancellation cannot unsend it. Finish commits after
        this call returns; no new start is invoked after terminal closure.
        """
        error = None
        with self.db() as db:
            row = db.execute('SELECT * FROM runs WHERE id=?', (run_id,)).fetchone()
            ownership = db.execute('SELECT container_id FROM runner_ownership WHERE run_id=?', (run_id,)).fetchone()
            if row and row['deadline'] is not None and row['deadline'] <= time.time():
                raise InvalidRequest('runner_deadline_exceeded')
            if (not row or row['status'] != 'running' or
                    not row['runner'] or not ownership or
                    json.loads(row['runner'])['container_id'] != ownership['container_id']):
                raise InvalidRequest('execution_cancelled')
            if db.execute('SELECT 1 FROM runner_starts WHERE run_id=?', (run_id,)).fetchone():
                raise InvalidRequest('start_already_requested')
            db.execute('INSERT INTO runner_starts VALUES (?,?)', (run_id, json.dumps({'requested_at': timestamp()})))
            try:
                callback()
            except BaseException as caught:
                error = caught  # Preserve ambiguous start intent even on SDK failure.
        if error is not None:
            raise error

    def audit_recovery(self, run_id, decision, evidence_digest, *, candidate_id=None, daemon_id=None):
        body = {'audit_id': str(uuid4()), 'run_id': run_id, 'decision': decision,
                'candidate_id': candidate_id, 'daemon_id': daemon_id, 'actor_uid': os.getuid(),
                'process_id': os.getpid(), 'evidence_digest': evidence_digest, 'created_at': timestamp()}
        with self.db() as db:
            db.execute('INSERT INTO recovery_audit VALUES (?,?,?)', (body['audit_id'], run_id, json.dumps(body)))
        return body

    def confirm_cleanup(self, run_id, callback):
        # Serialize concurrent cleanup across processes. SDK callback MUST be
        # bounded and must not reenter State. Crash rolls back the confirmation;
        # an ambiguous remove retains quarantine rather than inventing success.
        with self.db() as db:
            row = db.execute('SELECT status FROM runs WHERE id=?', (run_id,)).fetchone()
            if not row or row['status'] != 'finished':
                return False
            if not db.execute('SELECT 1 FROM cleanups WHERE run_id=?', (run_id,)).fetchone():
                if not callback():
                    return False
                db.execute('INSERT INTO cleanups VALUES (?,?)', (run_id, timestamp()))
            db.execute('DELETE FROM locks WHERE run_id=?', (run_id,))
            return True

    def finish(self, run_id, result):
        with self.db() as db:
            return db.execute("UPDATE runs SET result=?, status='finished' WHERE id=? AND status='running'",
                              (json.dumps(result), run_id)).rowcount == 1

    def release(self, run_id):
        with self.db() as db:
            db.execute('DELETE FROM locks WHERE run_id=?', (run_id,))
