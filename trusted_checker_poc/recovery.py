"""Exact-ID, cleanup-only reconciliation. No label discovery or force adoption."""
from dataclasses import asdict
from datetime import datetime
import json
from pathlib import Path
import queue
import sqlite3
import threading
import time
from uuid import UUID

from .contracts import Runner, Target, digest, full_id
from .docker_adapter import DedicatedDaemonApproval, DockerAdapter, Plan, intent_labels
from .registry import Policy
from .state import State

_EVENTS = threading.BoundedSemaphore(2)


class Quarantine(ValueError):
    pass


def snapshot(path, run_id):
    db = sqlite3.connect(Path(path).resolve().as_uri() + '?mode=ro', uri=True)
    db.row_factory = sqlite3.Row
    try:
        row = db.execute('SELECT * FROM runs WHERE id=?', (run_id,)).fetchone()
        tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        def read(table):
            if table not in tables:
                return None
            value = db.execute(f'SELECT body FROM {table} WHERE run_id=?', (run_id,)).fetchone()
            return json.loads(value['body']) if value else None
        return dict(row) if row else None, read('create_intents'), read('runner_ownership')
    finally:
        db.close()


def exact_events(client, container_id, since):
    """SDK events() overrides client timeout with None. Bound its reader explicitly.

    Reader is read-only, cannot attach ownership/delete anything after timeout.
    Two stuck readers at most per process; CLI exits with quarantine on timeout.
    """
    if not _EVENTS.acquire(blocking=False):
        raise Quarantine('daemon_audit_reader_capacity')
    result = queue.Queue(maxsize=1)
    until = int(time.time()) + 1
    def read():
        stream = None
        try:
            stream = client.events(since=int(since), until=until,
                filters={'container': container_id, 'event': 'create', 'type': 'container'}, decode=True)
            events, size = [], 0
            for event in stream:
                size += len(json.dumps(event))
                if len(events) >= 32 or size > 65536:
                    raise ValueError('audit_limit')
                events.append(event)
            result.put(events)
        except Exception:
            result.put(None)
        finally:
            if stream is not None:
                try:
                    stream.close()
                except Exception:
                    pass
            _EVENTS.release()
    threading.Thread(target=read, daemon=True).start()
    try:
        events = result.get(timeout=4)
    except queue.Empty:
        raise Quarantine('daemon_audit_timeout') from None
    if events is None:
        raise Quarantine('daemon_audit_unavailable')
    return events


def verify(client, approval, journal, run_id, container_id):
    if not full_id(container_id) or str(UUID(run_id)) != run_id:
        raise Quarantine('exact_identity_required')
    row, intent, ownership = snapshot(journal.directory / 'state.sqlite', run_id)
    if not row or row['status'] != 'finished' or not row['result']:
        raise Quarantine('terminal_run_required')
    terminal = json.loads(row['result'])
    if terminal['result'] != 'unknown':
        raise Quarantine('terminal_unknown_required')
    target, policy = Target(**json.loads(row['target'])), Policy(**json.loads(row['policy']))
    if (target.scope != journal.body['scope'] or policy.runner_image_id != approval.runner_image or
            client.info()['ID'] != approval.daemon_id):
        raise Quarantine('recovery_binding_mismatch')
    adapter = DockerAdapter(client, DedicatedDaemonApproval(approval.daemon_id, target.network_id,
        target.scope, 'operator approved exact-ID reconciliation'))
    obj = client.containers.get(container_id)
    obj.reload()
    attrs = obj.attrs
    if obj.id != container_id or attrs.get('Id') != container_id:
        raise Quarantine('candidate_identity_mismatch')
    env = dict(item.split('=', 1) for item in attrs['Config'].get('Env', []))
    nonce = env.get('POC_CHALLENGE', '')
    if len(nonce) != 64 or any(c not in '0123456789abcdef' for c in nonce):
        raise Quarantine('candidate_configuration_mismatch')
    if intent:
        if (intent['daemon_id'] != approval.daemon_id or intent['integration_id'] != journal.body['integration_id'] or
                intent['scope'] != target.scope or intent['image_id'] != policy.runner_image_id or
                intent['target_id'] != target.container_id or intent['target_generation'] != target.generation or
                intent['network_id'] != target.network_id or intent['policy_digest'] != digest(asdict(policy)) or
                intent['challenge_digest'] != digest(nonce)):
            raise Quarantine('intent_binding_mismatch')
        expected_labels = intent_labels(intent)
        since = intent['created_epoch']
        source_kind = 'intent_and_daemon_create'
        trace = {'intent_digest': digest(intent)}
    else:
        # Historical #19 hook records obj.id returned by SDK, not task claims.
        # Without this independent persisted create-response trace, matching
        # inspect/event labels alone DO NOT prove old ownership.
        traces = [entry for entry in journal.body.get('observations', [])
                  if entry.get('phase') == 'pre_start' and entry.get('run_id') == run_id and
                  entry.get('runner_id') == container_id and entry.get('image_id') == policy.runner_image_id]
        checks = ('uid_gid_10001', 'readonly_rootfs', 'unprivileged', 'cap_drop_all',
                  'no_new_privileges', 'no_host_mounts', 'private_namespaces', 'scratch_expected', 'labels_expected')
        traces = [entry for entry in traces if all(entry.get(key) is True for key in checks) and
                  entry.get('network_count') == 1 and entry.get('memory_bytes') == policy.memory_bytes and
                  entry.get('cpu_nanos') == policy.cpu_nanos and entry.get('pids') == policy.pids]
        if not traces:
            raise Quarantine('durable_create_response_trace_missing')
        since = datetime.fromisoformat(row['started_at']).timestamp()
        if not any(since <= datetime.fromisoformat(entry['at']).timestamp() <= time.time() for entry in traces):
            raise Quarantine('legacy_trace_time_mismatch')
        trace = {'journal_observation_digest': digest(traces)}
        expected_labels = {}
        source_kind = 'legacy_journal_and_daemon_create'
    plan = Plan(policy, target, run_id, nonce, intent=intent)
    # Unknown-ID adoption is restricted to a never-started created runner.
    # Full launch security invariants are retained, no empty running NetworkID.
    if not adapter._runner_valid(obj, plan, phase='pre_start'):
        raise Quarantine('candidate_configuration_mismatch')
    labels = {'tc-poc.scope': target.scope, 'tc-poc.role': 'runner', 'tc-poc.run': run_id, **expected_labels}
    candidates = exact_events(client, container_id, since)
    events = [event for event in candidates if event.get('Type') == 'container' and event.get('Action') == 'create'
              and event.get('Actor', {}).get('ID') == container_id
              and type(event.get('timeNano')) is int and since <= event['timeNano'] / 1e9 <= time.time()
              and all(event.get('Actor', {}).get('Attributes', {}).get(key) == value for key,value in labels.items())
              and event.get('Actor', {}).get('Attributes', {}).get('image') == policy.runner_image_id]
    if len(events) != 1 or client.info()['ID'] != approval.daemon_id:
        raise Quarantine('independent_daemon_create_evidence_missing')
    if ownership and ownership['container_id'] != container_id:
        raise Quarantine('ownership_conflict')
    return adapter, Runner(container_id, policy.runner_image_id, run_id, target.scope, False), intent, {
        'kind': source_kind, **trace, 'daemon_create_event_digest': digest(events[0])}


def reconcile(client, approval, journal, run_id, container_id, *, apply=False):
    """Dry-run does not construct writable State or call remove/start/create."""
    approval.validate(mutation=apply)
    try:
        if not full_id(container_id) or str(UUID(run_id)) != run_id:
            raise ValueError
    except (ValueError, AttributeError):
        return {'status': 'quarantine', 'applied': False, 'reason': 'exact_identity_required'}
    result = {'status': 'quarantine', 'run_id': run_id, 'runner_id': container_id,
              'applied': False, 'reason': 'evidence_unconfirmed'}
    try:
        adapter, runner, intent, source = verify(client, approval, journal, run_id, container_id)
        result.update(status='recovery_dry_run_passed', reason='ownership_evidence_verified',
                      evidence_digest=digest(source))
    except Exception as error:
        if isinstance(error, Quarantine):
            result['reason'] = str(error)
        if apply:
            state = State(journal.directory / 'state.sqlite')
            state.audit_recovery(run_id, result['reason'], digest(result), candidate_id=container_id, daemon_id=approval.daemon_id)
        return result
    if apply:
        state = State(journal.directory / 'state.sqlite')
        try:
            state.own_runner(run_id, runner, daemon_id=approval.daemon_id,
                integration_id=journal.body['integration_id'], source=source,
                intent_id=intent['intent_id'] if intent else None)
        except Exception:
            state.audit_recovery(run_id, 'ownership_conflict', digest(source), candidate_id=container_id, daemon_id=approval.daemon_id)
            return {**result, 'status': 'quarantine', 'reason': 'ownership_conflict'}
        state.audit_recovery(run_id, 'ownership_recovered_cleanup_only', digest(source), candidate_id=container_id, daemon_id=approval.daemon_id)
        # No implicit execution or automatic delete in reconciliation.
        result.update(status='ownership_recovered', applied=True)
    return result
