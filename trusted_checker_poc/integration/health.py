"""SELECT-only suite health and counts. No Docker operations or lease changes."""
import json
from pathlib import Path
import sqlite3


class SuiteHalted(RuntimeError):
    pass


def snapshot(state):
    db = sqlite3.connect(Path(state.path).resolve().as_uri()+'?mode=ro', uri=True, timeout=1)
    db.row_factory = sqlite3.Row
    try:
        db.execute('BEGIN')
        rows = [dict(row) for row in db.execute('''SELECT r.id,r.status,r.result,r.runner,
            EXISTS(SELECT 1 FROM locks l WHERE l.run_id=r.id) AS leased,
            EXISTS(SELECT 1 FROM create_intents i WHERE i.run_id=r.id) AS intent,
            EXISTS(SELECT 1 FROM runner_ownership o WHERE o.run_id=r.id) AS owned,
            EXISTS(SELECT 1 FROM cleanups c WHERE c.run_id=r.id) AS cleaned,
            EXISTS(SELECT 1 FROM runner_starts s WHERE s.run_id=r.id) AS start_requested
            FROM runs r ORDER BY r.rowid''')]
        return rows
    finally:
        db.close()


def health_problem(rows, journal):
    if journal.body.get('diagnostics_write_failed'):
        return 'diagnostics_unavailable', None
    if any(r['status'] == 'create_intent' for r in journal.body['resources']):
        return 'unresolved_fixture_create', None
    for row in rows:
        if row['status'] == 'running':
            return 'active_execution_not_closed', row['id']
        if row['status'] == 'finished':
            if row['intent'] and not row['owned']:
                return 'unresolved_create_outcome', row['id']
            if row['leased'] and not (row['owned'] or row['runner']):
                return 'lease_without_ownership', row['id']
            if row['leased'] or ((row['owned'] or row['runner']) and not row['cleaned']):
                return 'cleanup_incomplete', row['id']
            result = json.loads(row['result']) if row['result'] else {}
            if result.get('failure_class') == 'integrity':
                return 'environmental_integrity_unproven', row['id']
            if result.get('reason') == 'runner_prepare_unknown':
                return 'prepare_failure', row['id']
    if journal.body.get('cleanup_status') == 'cleanup_incomplete':
        return 'cleanup_incomplete', None
    return None


def request_metrics(state, journal, returned=(), run_ids=None):
    rows = snapshot(state)
    if run_ids is not None:
        rows = [row for row in rows if row['id'] in run_ids]
    selected = {row['id'] for row in rows}
    events = journal.prepare_events()
    live = {o['run_id'] for o in journal.body['observations'] if o.get('phase') == 'post_start' and o['run_id'] in selected}
    invoked = {e['run_id'] for e in events if e['start_invoked'] and e['run_id'] in selected}
    terminal = [json.loads(row['result']) for row in rows if row['result']]
    blocked = {item['run_id'] for item in returned if item['run_id'] in selected and item.get('reason') in ('target_busy','capacity_exhausted')}
    return {'issued': len(rows), 'admitted': sum(r['status'] != 'issued' for r in rows),
            'not_admitted': sum(r['status'] == 'issued' for r in rows),
            'blocked_by_active_lease': len(blocked),
            'start_requests': sum(r['start_requested'] for r in rows),
            'start_invocations': len(invoked), 'physically_started_observed': len(live),
            'start_outcome_unobserved': len(invoked-live),
            'infrastructure_unknown': sum(r['result'] == 'unknown' and r['failure_class'] in
                ('infrastructure','unknown_execution') for r in terminal),
            'timeout': sum(r['failure_class'] == 'timeout' for r in terminal),
            'post_start_validation_failure': len({o['run_id'] for o in journal.body['observations']
                if o.get('phase') == 'post_start_rejected' and o['run_id'] in selected}),
            'terminal_receipts': len(terminal)}
