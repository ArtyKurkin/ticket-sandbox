"""Owned synthetic resources and diagnostics around the unmodified scored path."""
from dataclasses import asdict
import json
import threading
import time
from uuid import uuid4

from ..broker import Broker
from ..contracts import Runner, timestamp
from ..docker_adapter import DedicatedDaemonApproval, DockerAdapter
from ..registry import POLICY_ID, Registry
from ..state import State
from .evidence import configuration_observation
from .safety import Denied, resource_matches
from .health import SuiteHalted, snapshot, health_problem, request_metrics

# Static trusted diagnostic, executed only in an already validated owned runner.
# No shell, network, task code, secret reads, or writes to the checker bytes.
BEHAVIOR = '''import os,json,errno,hashlib
from pathlib import Path
s=Path('/proc/self/status').read_text().splitlines()
fields=dict(line.split(':',1) for line in s if ':' in line)
try:
 fd=os.open('/checker/runner.py',os.O_WRONLY);os.close(fd);blocked=False
except OSError as e:
 blocked=e.errno in (errno.EROFS,errno.EACCES,errno.EPERM)
print(json.dumps({'uid':os.getuid()==10001,'gid':os.getgid()==10001,
 'caps_zero':int(fields['CapEff'].strip(),16)==0,
 'nnp':fields['NoNewPrivs'].strip()=='1','checker_write_denied':blocked,
 'socket_absent':not Path('/var/run/docker.sock').exists(),
 'checker_digest':hashlib.sha256(Path('/checker/runner.py').read_bytes()).hexdigest()}))
'''
CONFIGURE = '''import json,sys,os
from pathlib import Path
p=Path('/fixture/service.json');t=p.with_suffix('.tmp')
t.write_text(json.dumps(json.loads(sys.argv[1])));os.replace(t,p)
'''
READY = "from pathlib import Path; print(Path('/fixture/ready.json').read_text() if Path('/fixture/ready.json').exists() else '{}')"
TARGET_MUTATE = '''from pathlib import Path
for p in ('/task/check.sh','/usr/local/bin/curl','/checker/runner.py'):
 q=Path(p);q.parent.mkdir(parents=True,exist_ok=True);q.write_text('synthetic hostile replacement')
print('fixture_mutated')
'''


class RecordingAdapter(DockerAdapter):
    def __init__(self, client, approval, journal):
        super().__init__(client, approval)
        self.journal = journal
        self.integration_id = journal.body['integration_id']
        self.live = threading.Event()
        self.behavior = False
        self.action = None
        self.mutex = journal.lock

    def record_prepare_event(self, event):
        self.journal.prepare_event(event)

    def _runner_valid(self, obj, plan, *, phase, connection=None):
        valid = super()._runner_valid(obj, plan, phase=phase, connection=connection)
        if not valid:
            with self.mutex:
                state = obj.attrs.get('State', {}).get('Status')
                self.journal.body['observations'].append({'run_id': plan.run_id,
                    'runner_id': obj.id, 'phase': phase + '_rejected',
                    'state': state if state in ('created', 'running', 'exited') else 'other',
                    'at': timestamp()})
                self.journal.save()
        return valid

    def observe_runner(self, obj, plan, phase):
        with self.mutex:
            observation = configuration_observation(obj, plan, phase)
            if phase == 'starting':
                starts = self.journal.body['start_attempts']
                starts[plan.run_id] = starts.get(plan.run_id, 0) + 1
            if phase == 'post_start':
                starts = self.journal.body['physical_starts']
                starts[plan.run_id] = starts.get(plan.run_id, 0) + 1
                self.live.set()
                if self.behavior:
                    try:
                        reply = obj.exec_run(['/usr/local/bin/python', '-I', '-c', BEHAVIOR], user='10001:10001')
                        parsed = json.loads(reply.output) if len(reply.output) <= 1024 and reply.exit_code == 0 else {}
                        keys = {'uid', 'gid', 'caps_zero', 'nnp', 'checker_write_denied', 'socket_absent'}
                        observation['behavior'] = {k: parsed.get(k) is True for k in sorted(keys)}
                        observation['behavior']['checker_digest_expected'] = parsed.get('checker_digest') == plan.policy.source_digest
                    except Exception:
                        observation['behavior'] = {'inconclusive': True}
                action, self.action = self.action, None
                if action:
                    action(obj, plan)
            self.journal.body['observations'].append(observation)
            self.journal.save()


class Runtime:
    def __init__(self, client, approval, journal):
        approval.validate(mutation=True)
        self.client, self.approval, self.journal = client, approval, journal
        self.scope = journal.body['scope']
        self.network = None
        self.state = State(journal.directory / 'state.sqlite')
        self.adapter = None
        self.registry = Registry(runner_image_id=approval.runner_image, timeout=8)
        self.broker = None
        self.returned_results = self.journal.body.setdefault('request_outcomes', [])

    def stop(self, reason, run_id=None):
        self.journal.body.setdefault('halt', {'reason': reason, 'run_id': run_id, 'at': timestamp()})
        try:
            self.journal.save()
        except Exception:
            pass
        raise SuiteHalted(self.journal.body['halt']['reason'])

    def ensure_healthy(self):
        if self.journal.body.get('halt'):
            raise SuiteHalted(self.journal.body['halt']['reason'])
        try:
            problem = health_problem(snapshot(self.state), self.journal)
        except Exception:
            self.stop('health_unavailable')
        if problem:
            self.stop(*problem)

    def refuse_if_halted(self):
        if self.journal.body.get('halt'):
            raise SuiteHalted(self.journal.body['halt']['reason'])

    def metrics(self, run_ids=None):
        return request_metrics(self.state, self.journal, self.returned_results, run_ids)

    def labels(self, record):
        labels = {'tc-poc.integration': self.journal.body['integration_id'], 'tc-poc.scope': self.scope,
                  'tc-poc.token': record['token'], 'tc-poc.role': record['kind']}
        if record['kind'] == 'target':
            labels.update({'tc-poc.generation': record['generation'], 'tc-poc.owner': 'synthetic-operator',
                           'tc-poc.task': 'synthetic-localhost'})
        return labels

    def network_create(self):
        self.ensure_healthy()
        record = self.journal.intent('network')
        obj = self.client.networks.create('tc-integration-' + record['token'], driver='bridge',
                                          internal=True, labels=self.labels(record))
        self.journal.recorded(record, obj.id)
        obj.reload()
        self.require_owned(obj, record)
        return record

    def provision(self):
        self.network = self.network_create()
        self.adapter = RecordingAdapter(self.client, DedicatedDaemonApproval(
            self.approval.daemon_id, self.network['id'], self.scope,
            'explicit isolated daemon approval for synthetic integration run'), self.journal)
        self.broker = Broker(self.state, self.registry, self.adapter, scope=self.scope)
        self.journal.body['policy_identity'] = asdict(self.registry.get(POLICY_ID))
        self.journal.save()

    def require_owned(self, obj, record):
        if not resource_matches(obj.attrs, record, self.journal.body['integration_id'], self.scope):
            self.stop('environmental_integrity_unproven')

    def target(self, enrollment_transform=None):
        self.ensure_healthy()
        record = self.journal.intent('target', image=self.approval.target_image, generation=str(uuid4()))
        obj = self.client.containers.create(image=record['image'], name='tc-integration-' + record['token'],
            entrypoint=['/usr/local/bin/python', '-I', '/fixture/server.py'], command=[],
            network=self.network['id'], labels=self.labels(record), user='0:0',
            mem_limit=64 * 1024 * 1024, nano_cpus=250_000_000, pids_limit=32,
            cap_drop=['ALL'], security_opt=['no-new-privileges:true'],
            log_config={'Type': 'json-file', 'Config': {'max-size': '16k', 'max-file': '1'}})
        self.journal.recorded(record, obj.id)
        obj.reload()
        self.require_owned(obj, record)
        obj.start()
        self.configure(record, {'bind': '127.0.0.1'})
        observed = self.adapter.inspect_target(record['id'])
        if observed.image_id != record['image'] or observed.generation != record['generation']:
            raise Denied('created_target_identity_mismatch')
        enrolled = enrollment_transform(observed) if enrollment_transform else observed
        self.state.enroll(enrolled)
        record['enrollment'] = asdict(enrolled)
        self.journal.save()
        return record

    def owned_target(self, record):
        obj = self.client.containers.get(record['id'])
        obj.reload()
        self.require_owned(obj, record)
        return obj

    def configure(self, record, config):
        self.refuse_if_halted()
        # This is fixture administration, NEVER the source of a scored verdict.
        from ..synthetic_target import config_digest
        obj = self.owned_target(record)
        reply = obj.exec_run(['/usr/local/bin/python', '-I', '-c', CONFIGURE, json.dumps(config)])
        if reply.exit_code != 0:
            raise Denied('fixture_configuration_failed')
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            reply = obj.exec_run(['/usr/local/bin/python', '-I', '-c', READY])
            if reply.exit_code == 0 and len(reply.output) < 256:
                try:
                    if json.loads(reply.output).get('config_digest') == config_digest(config):
                        return
                except (ValueError, AttributeError):
                    pass
            time.sleep(0.05)  # Fixture readiness polling, not checker validation.
        raise Denied('fixture_readiness_timeout')

    def issue(self, record, broker=None):
        self.ensure_healthy()
        return (broker or self.broker).issue(record['id'], 'synthetic-operator', POLICY_ID)

    def execute(self, request, broker=None):
        result = (broker or self.broker).execute(request, owner='synthetic-operator')
        self.returned_results.append({key: result[key] for key in ('run_id','result','reason','failure_class')})
        self.journal.body['request_metrics'] = self.metrics()
        self.journal.report()
        return result

    def remove_target(self, record):
        self.refuse_if_halted()
        obj = self.owned_target(record)
        obj.remove(force=True)
        record['status'] = 'removed'
        record['removed_at'] = timestamp()
        self.journal.save()

    def cleanup(self):
        """Terminal exact runner cleanup first, then only durably created fixtures."""
        from docker.errors import NotFound
        pending = False
        # Reconstruct only the approved per-run network/adapter, never discover resources.
        network_records = [r for r in self.journal.body['resources'] if r['kind'] == 'network']
        primary = network_records[0] if network_records else None
        with self.state.db() as db:
            runs = [dict(row) for row in db.execute('SELECT * FROM runs')]
        if runs and not self.broker:
            try:
                self.adapter = RecordingAdapter(self.client, DedicatedDaemonApproval(
                    self.approval.daemon_id, primary['id'], self.scope,
                    'explicit isolated cleanup approval'), self.journal)
                self.broker = Broker(self.state, self.registry, self.adapter, scope=self.scope)
            except Exception:
                pending = True
        for row in runs:
            if row['status'] == 'running' and row['deadline'] <= time.time() and self.broker:
                self.broker.execute(json.loads(row['request']), owner=row['owner'])
                row = self.state.read(row['id'])
            if row['status'] == 'finished' and (row['runner'] or self.state.receipt('runner_ownership', row['id'])) and self.broker:
                if not self.broker.cleanup(row['id']):
                    pending = True
        with self.state.db() as db:
            if db.execute('SELECT 1 FROM locks').fetchone():
                pending = True
        # Unrecorded create response is an unresolved orphan. Do not remove its
        # network/target or release its lease based on a label/name guess.
        if any(r['status'] == 'create_intent' for r in self.journal.body['resources']):
            pending = True
        if not pending:
            records = list(reversed(self.journal.body['resources']))
            # Extra networks can be created after a target for identity tests.
            # Always remove verified own targets before any network.
            records = [r for r in records if r['kind'] == 'target'] + [r for r in records if r['kind'] == 'network']
            for record in records:
                if record['status'] == 'removed':
                    continue
                try:
                    api = self.client.containers if record['kind'] == 'target' else self.client.networks
                    obj = api.get(record['id'])
                    obj.reload()
                    self.require_owned(obj, record)
                    if record['kind'] == 'network' and obj.attrs.get('Containers'):
                        pending = True
                        continue
                    if record['kind'] == 'target':
                        obj.remove(force=True)
                    else:
                        obj.remove()
                    record.update(status='removed', removed_at=timestamp())
                except NotFound:
                    # Full recorded ID has been checked absent by this daemon.
                    # Fixture absence is separate from a runner cleanup receipt.
                    record.update(status='removed', removed_at=timestamp(), removal='observed_absent')
                except Exception:
                    pending = True
                self.journal.save()
                if pending:
                    break
        self.journal.body['cleanup_status'] = 'cleanup_incomplete' if pending else 'cleanup_complete'
        self.journal.report()
        return not pending
