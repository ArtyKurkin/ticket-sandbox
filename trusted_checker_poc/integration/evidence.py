"""Private local journal. Atomic writes, exclusive operator session, safe exports."""
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import threading
from uuid import uuid4

from ..contracts import timestamp
from ..diagnostics import valid_event


def write_json(path, body):
    path = Path(path)
    temporary = path.with_suffix('.tmp')
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, 'w') as stream:
        json.dump(body, stream, sort_keys=True, indent=2, allow_nan=False)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)
    directory = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)


@contextmanager
def exclusive(directory):
    # Private trusted operator directory, never task-mounted/network FS.
    with (Path(directory) / 'session.lock').open('a') as stream:
        fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield


def source_digests():
    root = Path(__file__).resolve().parents[1]
    files = list(root.rglob('*.py')) + list(root.glob('images/*/Dockerfile'))
    return {str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(files)}


class Journal:
    def __init__(self, directory, *, create=False, approval=None, environment=None):
        self.directory = Path(directory).resolve()
        self.path = self.directory / 'journal.json'
        self.lock = threading.RLock()
        if create:
            self.directory.mkdir(mode=0o700, parents=False, exist_ok=False)
            run_id = str(uuid4())
            self.body = {'schema_version': 1, 'integration_id': run_id,
                         'scope': approval.scope + '-' + run_id[:8],
                         'started_at': timestamp(), 'finished_at': None,
                         'environment': environment, 'source_digests': source_digests(),
                         'resources': [], 'scenarios': [], 'observations': [],
                         'terminal_receipts': {}, 'cleanup_receipts': {},
                         'create_intents': {}, 'ownership_receipts': {}, 'recovery_audit': [],
                         'physical_starts': {}, 'start_attempts': {}, 'status': 'test_inconclusive',
                         'unverified': ['kernel/daemon compromise', 'supply-chain attestation',
                                        'target fixture integrity', 'all real L1 adapters',
                                        'orphan ownership without recorded full ID',
                                        'daemon outage/API response loss: fake-only',
                                        'host namespace breakout/penetration testing']}
            self.report()  # Initial JSON/Markdown also survive an early crash.
        else:
            self.body = json.loads(self.path.read_text())
            if self.body.get('schema_version') != 1:
                raise ValueError('unsupported_journal')

    def save(self):
        with self.lock:
            write_json(self.path, self.body)

    def prepare_event(self, event):
        if not valid_event(event):
            raise ValueError('invalid_prepare_event')
        with self.lock:
            try:
                # Sidecar is independent of SQLite: safe even inside start_once.
                path = self.directory / 'prepare-events.jsonl'
                if path.exists() and path.stat().st_size > 2*1024*1024:
                    raise ValueError('prepare_event_limit')
                fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
                with os.fdopen(fd, 'w') as stream:
                    stream.write(json.dumps(event, sort_keys=True, allow_nan=False)+'\n')
                    stream.flush()
                    os.fsync(stream.fileno())
            except Exception:
                self.body['diagnostics_write_failed'] = True
                raise

    def prepare_events(self):
        path = self.directory / 'prepare-events.jsonl'
        if not path.exists():
            return []
        if path.stat().st_size > 2*1024*1024:
            raise ValueError('prepare_event_limit')
        events = []
        with path.open() as stream:
            for line in stream:
                if len(events) >= 4096 or len(line) > 2048:
                    raise ValueError('prepare_event_limit')
                event = json.loads(line)
                if not valid_event(event):
                    raise ValueError('invalid_prepare_event')
                events.append(event)
        return events

    def intent(self, kind, **facts):
        record = {'kind': kind, 'token': str(uuid4()), 'status': 'create_intent', **facts}
        self.body['resources'].append(record)
        self.save()
        return record

    def recorded(self, record, identity):
        from ..contracts import full_id
        if not full_id(identity):
            raise ValueError('invalid_created_identity')
        record.update(id=identity, status='recorded')
        self.save()

    def receipts(self):
        path = self.directory / 'state.sqlite'
        if not path.exists():
            return
        db = sqlite3.connect(path.as_uri() + '?mode=ro', uri=True)
        try:
            for run_id, value in db.execute('SELECT id,result FROM runs WHERE result IS NOT NULL'):
                receipt = json.loads(value)
                previous = self.body['terminal_receipts'].setdefault(run_id, receipt)
                if previous != receipt:
                    raise ValueError('terminal_receipt_changed')
            exists = db.execute("SELECT 1 FROM sqlite_master WHERE name='cleanups'").fetchone()
            if exists:
                self.body['cleanup_receipts'].update({key: {'finished_at': value}
                    for key, value in db.execute('SELECT run_id,finished_at FROM cleanups')})
            tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            for table, field in (('create_intents','create_intents'), ('runner_ownership','ownership_receipts')):
                if table in tables:
                    output = self.body.setdefault(field, {})
                    for run_id, value in db.execute(f'SELECT run_id,body FROM {table}'):
                        receipt = json.loads(value)
                        if 'token' in receipt:
                            from ..contracts import digest
                            receipt['token_digest'] = digest(receipt.pop('token'))
                        output[run_id] = receipt
            if 'recovery_audit' in tables:
                self.body['recovery_audit'] = [json.loads(r[0]) for r in db.execute('SELECT body FROM recovery_audit ORDER BY rowid')]
        finally:
            db.close()

    def report(self):
        with self.lock:
            self._report()

    def _report(self):
        self.body['prepare_diagnostics'] = self.prepare_events()
        self.receipts()
        self.save()
        write_json(self.directory / 'report.json', self.body)
        body = self.body
        lines = ['# Trusted Checker integration', '', f"Run: `{body['integration_id']}`",
                 f"Status: **{body['status']}**", '',
                 'Unsigned local observations; no award/attestation.', '',
                 '| Scenario | Status | Reason |', '|---|---|---|']
        for item in body['scenarios']:
            lines.append(f"| {item['name']} | {item['status']} | {item['reason']} |")
        lines += ['', 'Unverified:'] + ['- ' + item for item in body['unverified']]
        lines += ['', 'Exact identities, policy, immutable terminal and separate cleanup receipts:',
                  '`report.json` in this private run directory.']
        fd = os.open(self.directory / 'report.md', os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, 'w') as stream:
            stream.write('\n'.join(lines) + '\n')


def configuration_observation(obj, plan, phase):
    """Allowlist, not an inspect dump; no environment values or arbitrary paths."""
    attrs = obj.attrs
    host, config = attrs['HostConfig'], attrs['Config']
    networks = list(attrs['NetworkSettings']['Networks'].values())
    from .safety import IMAGE
    return {'run_id': plan.run_id, 'runner_id': obj.id, 'phase': phase,
            'image_id': attrs['Image'] if IMAGE.fullmatch(attrs.get('Image', '')) else 'invalid',
            'uid_gid_10001': config.get('User') == '10001:10001',
            'readonly_rootfs': host.get('ReadonlyRootfs') is True,
            'unprivileged': host.get('Privileged') is False,
            'cap_drop_all': host.get('CapDrop') == ['ALL'] and not host.get('CapAdd'),
            'no_new_privileges': 'no-new-privileges:true' in host.get('SecurityOpt', []),
            'no_host_mounts': not host.get('Binds') and not host.get('VolumesFrom') and
                             all(m.get('Type') == 'tmpfs' and m.get('Destination') == '/scratch'
                                 for m in attrs.get('Mounts', [])),
            'private_namespaces': host.get('PidMode', '') == '' and
                                  host.get('IpcMode', 'private') in ('', 'private') and
                                  host.get('NetworkMode') == plan.target.network_id,
            'network_count': len(networks), 'network_exact': len(networks) == 1 and
                           networks[0].get('NetworkID') == plan.target.network_id,
            'memory_bytes': host.get('Memory'), 'cpu_nanos': host.get('NanoCpus'),
            'pids': host.get('PidsLimit'), 'scratch_expected': host.get('Tmpfs') ==
                {'/scratch': 'rw,noexec,nosuid,nodev,size=1m,uid=10001,gid=10001,mode=0700'},
            'labels_expected': all(config.get('Labels', {}).get(k) == v for k, v in {
                'tc-poc.scope': plan.target.scope, 'tc-poc.role': 'runner', 'tc-poc.run': plan.run_id}.items()),
            'at': timestamp()}
