"""Real-runtime scenarios. Results are observations, not security certification."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import json
import time

from ..broker import Broker
from ..contracts import Runner, timestamp
from ..registry import Registry
from .health import SuiteHalted


class Inconclusive(Exception):
    pass


def require(condition):
    # Runtime acceptance checks must survive PYTHONOPTIMIZE / python -O.
    if not condition:
        raise AssertionError('expectation_failed')


def expect(result, status, reason=None):
    if result['result'] != status:
        if result['result'] == 'unknown':
            raise Inconclusive(result['reason'])
        raise AssertionError('unexpected_verdict')
    if reason and result['reason'] != reason:
        if result['result'] == 'unknown':
            raise Inconclusive(result['reason'])
        raise AssertionError('unexpected_reason')


class Scenarios:
    def __init__(self, runtime, repetitions):
        self.r = runtime
        self.j = runtime.journal
        self.repetitions = repetitions
        self.stopped = bool(self.j.body.get('halt'))

    def case(self, name, operation):
        if self.stopped:
            self.j.body['scenarios'].append({'name': name, 'status': 'NOT RUN',
                'reason': 'suite_halted', 'started_at': None, 'finished_at': None})
            self.j.report()
            return
        item = {'name': name, 'started_at': None}
        try:
            self.r.ensure_healthy()
            item['started_at'] = timestamp()
            operation()
            item.update(status='test_passed', reason='expected_observations')
        except SuiteHalted:
            item.update(status='test_inconclusive' if item['started_at'] else 'NOT RUN', reason='suite_halted')
            self.stopped = True
        except Inconclusive:
            item.update(status='test_inconclusive', reason='runtime_or_infrastructure_unknown')
        except AssertionError:
            item.update(status='test_failed', reason='assertion_failed')
        except Exception:
            # Do not export exceptions/HTTP/Docker bodies/host paths.
            item.update(status='test_inconclusive', reason='operation_unconfirmed')
        finally:
            self.r.adapter.behavior = False
            self.r.adapter.action = None
        try:
            self.r.ensure_healthy()
        except SuiteHalted:
            self.stopped = True
            if item['status'] not in ('test_failed','NOT RUN'):
                item.update(status='test_inconclusive', reason='suite_halted')
        if self.stopped and name == 'short_runner_repetitions' and 'short_runner_summary' in self.j.body:
            for repetition in self.j.body['short_runner_summary']['not_run']:
                repetition['reason'] = 'suite_halted'
        item['finished_at'] = timestamp() if item['started_at'] else None
        self.j.body['scenarios'].append(item)
        self.j.report()

    def basic(self):
        r = self.r
        target = r.target()
        original = r.adapter.inspect_target(target['id'])
        first = r.issue(target)
        receipt = r.execute(first)
        expect(receipt, 'failed', 'service_unreachable')
        r.configure(target, {'bind': '0.0.0.0'})
        second = r.issue(target)
        require(second.run_id != first.run_id)
        expect(r.execute(second), 'passed', 'probe_passed')
        require(r.execute(first) == receipt)
        require(r.adapter.inspect_target(target['id']) == original)
        require(r.broker.cleanup(first.run_id) and r.broker.cleanup(second.run_id))
        require(self.j.body['physical_starts'].get(first.run_id) == 1)
        require(self.j.body['start_attempts'].get(first.run_id) == 1)
        require(self.j.body['physical_starts'].get(second.run_id) == 1)
        from docker.errors import NotFound
        for request in (first, second):
            runner = json.loads(r.state.read(request.run_id)['runner'])
            try:
                r.client.containers.get(runner['container_id'])
            except NotFound:
                continue
            raise AssertionError('runner_still_present')

    def create_register_race(self):
        """Real create, locally held response; daemon itself is never paused.

        This deliberately widens the create-response/register window, while
        leaving the actual Docker request and cleanup on the approved daemon.
        """
        import threading
        r = self.r
        target = r.target()
        broker = Broker(r.state, Registry(runner_image_id=r.approval.runner_image, timeout=0.7), r.adapter, scope=r.scope)
        request = r.issue(target, broker)
        created, release = threading.Event(), threading.Event()
        original = r.client.api.create_container
        def held_response(*args, **kwargs):
            response = original(*args, **kwargs)  # One real Docker create.
            created.set()
            release.wait(5)
            return response
        r.client.api.create_container = held_response
        try:
            with ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(broker.execute, request, owner='synthetic-operator')
                if not created.wait(3):
                    raise Inconclusive('create_not_observed')
                terminal = future.result(timeout=3)
                expect(terminal, 'unknown', 'runner_deadline_exceeded')
                require(r.state.read(request.run_id)['runner'] is None)
                require(r.state.receipt('create_intents', request.run_id) is not None)
                require(r.state.receipt('runner_ownership', request.run_id) is None)
        finally:
            release.set()
            r.client.api.create_container = original
        deadline = time.monotonic() + 6
        complete = False
        while time.monotonic() < deadline:
            ownership = r.state.receipt('runner_ownership', request.run_id)
            if ownership and broker.cleanup(request.run_id):
                complete = True
                break
            time.sleep(0.05)
        if not complete:
            raise Inconclusive('late_ownership_or_cleanup_unconfirmed')
        require(r.execute(request, broker) == terminal)
        require(request.run_id not in self.j.body['start_attempts'])
        with r.state.db() as db:
            require(db.execute('SELECT 1 FROM runner_starts WHERE run_id=?', (request.run_id,)).fetchone() is None)
            require(db.execute('SELECT 1 FROM locks WHERE run_id=?', (request.run_id,)).fetchone() is None)
        self.j.body['create_register_race'] = {'run_id': request.run_id,
            'runner_id': ownership['container_id'], 'injection': 'held_real_create_response',
            'terminal_unchanged': True, 'late_start': False, 'cleanup_confirmed': True}

    def repetitions_case(self):
        r = self.r
        target = r.target()
        r.configure(target, {'bind': '0.0.0.0'})
        measurements = []
        for _ in range(self.repetitions):
            r.ensure_healthy()
            start = time.monotonic()
            request = r.issue(target)
            result = r.execute(request)
            measurements.append({'run_id': request.run_id, 'result': result['result'],
                                 'reason': result['reason'], 'seconds': round(time.monotonic() - start, 4)})
            self.j.body['short_runner_measurements'] = measurements
            self.short_summary(measurements)
            self.j.save()
            r.ensure_healthy()  # Stop immediately; no second issued UUID/fixture.
        self.short_summary(measurements)
        # Unknown remains visible even if all other iterations passed.
        for item in measurements:
            expect(item, 'passed', 'probe_passed')

    def short_summary(self, measurements):
        early_exit = sum(o['phase'] == 'post_start_rejected' and o.get('state') == 'exited'
                         and o['run_id'] in {m['run_id'] for m in measurements}
                         for o in self.j.body['observations'])
        self.j.body['short_runner_summary'] = {'runs': len(measurements),
            'passed': sum(m['result'] == 'passed' for m in measurements),
            'unknown': sum(m['result'] == 'unknown' for m in measurements),
            'exited_before_validation_observed': early_exit,
            'handshake_review_needed': early_exit > 0,
            'not_run_repetitions': self.repetitions-len(measurements),
            'not_run': [{'index':index,'status':'NOT RUN','reason':'not_started'}
                        for index in range(len(measurements)+1,self.repetitions+1)],
            'request_metrics': self.r.metrics({m['run_id'] for m in measurements})}
        self.j.save()

    def diagnostic_prepare(self):
        """One owned target, one issued UUID, no repeats or injected faults."""
        r = self.r
        target = r.target()
        r.configure(target, {'bind': '0.0.0.0'})
        request = r.issue(target)
        result = r.execute(request)
        self.j.body['diagnostic_run_id'] = request.run_id
        r.ensure_healthy()
        expect(result, 'passed', 'probe_passed')

    def run_diagnostic(self):
        self.case('single_create_prepare_diagnostic', self.diagnostic_prepare)
        status = self.j.body['scenarios'][-1]['status']
        self.j.body['status'] = 'test_inconclusive' if status == 'NOT RUN' else status
        self.j.body['finished_at'] = timestamp()
        self.j.report()

    def security(self):
        from .runtime import TARGET_MUTATE
        r = self.r
        target = r.target()
        r.configure(target, {'bind': '0.0.0.0', 'response_delay': 1.0})
        # Mutate only this writable synthetic fixture. The target does not share
        # checker filesystem/socket; the checker still comes from approved image.
        reply = r.owned_target(target).exec_run(['/usr/local/bin/python', '-I', '-c', TARGET_MUTATE])
        require(reply.exit_code == 0)
        r.adapter.behavior = True
        request = r.issue(target)
        expect(r.execute(request), 'passed', 'probe_passed')
        live = [o for o in self.j.body['observations'] if o['run_id'] == request.run_id and o['phase'] == 'post_start']
        require(len(live) == 1)
        checks = live[0].get('behavior', {})
        if checks.get('inconclusive') or not checks:
            raise Inconclusive('behavior_not_observed')
        require(all(checks.values()) and len(checks) == 7)

    def identity(self, mode):
        r = self.r
        # Seed a stale enrollment BEFORE issue; do not rewrite issued snapshots
        # or pretend Docker can update a running container's immutable labels.
        transform = None
        if mode == 'started_at':
            transform = lambda target: replace(target, started_at='2000-01-01T00:00:00Z')
        elif mode == 'generation':
            transform = lambda target: replace(target, generation='wrong-generation')
        target = r.target(enrollment_transform=transform)
        request = r.issue(target)
        if mode == 'stopped':
            r.owned_target(target).stop(timeout=1)
        elif mode == 'restart':
            r.owned_target(target).restart(timeout=1)
        elif mode == 'stale_id':
            r.remove_target(target)
        elif mode in ('wrong_network', 'extra_network'):
            extra = r.network_create()
            obj = r.owned_target(target)
            network = r.client.networks.get(extra['id'])
            network.reload()
            r.require_owned(network, extra)
            network.connect(obj.id)
            if mode == 'wrong_network':
                original = r.client.networks.get(r.network['id'])
                original.reload()
                r.require_owned(original, r.network)
                original.disconnect(obj.id)
        elif mode == 'disappear_during':
            r.configure(target, {'bind': '0.0.0.0', 'response_delay': 1})
            r.adapter.action = lambda *_: r.remove_target(target)
        result = r.execute(request)
        if result['result'] != 'unknown':
            raise AssertionError('identity_mismatch_accepted')
        allowed = {'target_identity_mismatch', 'target_changed_during_execution', 'target_unavailable'}
        if result['reason'] not in allowed:
            raise Inconclusive(result['reason'])

    def concurrency(self):
        r = self.r
        target = r.target()
        r.configure(target, {'bind': '0.0.0.0', 'response_delay': 1.2})
        first, second = r.issue(target), r.issue(target)
        r.adapter.live.clear()
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(r.broker.execute, first, owner='synthetic-operator')
            if not r.adapter.live.wait(timeout=6):
                raise Inconclusive('no_live_runner')
            same = r.broker.execute(first, owner='synthetic-operator')
            busy = r.broker.execute(second, owner='synthetic-operator')
            expect(same, 'unknown', 'execution_in_progress')
            expect(busy, 'unknown', 'target_busy')
            result = future.result(timeout=12)
        expect(result, 'passed', 'probe_passed')
        require(r.execute(first) == result)
        restarted = Broker(r.state, r.registry, r.adapter, scope=r.scope)
        require(r.execute(first, restarted) == result)
        require(self.j.body['physical_starts'].get(first.run_id) == 1)
        require(self.j.body['start_attempts'].get(first.run_id) == 1)
        require(second.run_id not in self.j.body['physical_starts'])

    def timeout(self):
        r = self.r
        target = r.target()
        r.configure(target, {'bind': '0.0.0.0', 'response_delay': 3})
        broker = Broker(r.state, Registry(runner_image_id=r.approval.runner_image, timeout=1), r.adapter, scope=r.scope)
        request = r.issue(target, broker)
        result = r.execute(request, broker)
        if result['result'] != 'unknown' or result['reason'] not in ('runner_deadline_exceeded', 'probe_timeout'):
            raise Inconclusive('deadline_not_observed')
        # Wait for the bounded SDK/probe operation, not the daemon. Late result
        # must not replace the durable terminal verdict.
        time.sleep(3.2)
        require(r.execute(request, broker) == result)
        require(self.j.body['start_attempts'].get(request.run_id, 0) <= 1)
        if self.j.body['physical_starts'].get(request.run_id) != 1:
            raise Inconclusive('no_live_runner_observed_before_deadline')
        r.broker.cleanup(request.run_id)

    def crash(self):
        r = self.r
        target = r.target()
        r.configure(target, {'bind': '0.0.0.0', 'response_delay': 1})
        # obj is the validated full-ID, broker-recorded runner, never target.
        r.adapter.action = lambda obj, _: obj.kill(signal='SIGKILL')
        result = r.execute(r.issue(target))
        expect(result, 'unknown', 'runner_crash')

    def hung_runner(self):
        r = self.r
        target = r.target()
        r.configure(target, {'bind': '0.0.0.0', 'response_delay': 1})
        broker = Broker(r.state, Registry(runner_image_id=r.approval.runner_image, timeout=1.5),
                        r.adapter, scope=r.scope)
        r.adapter.action = lambda obj, _: obj.kill(signal='SIGSTOP')
        request = r.issue(target, broker)
        result = r.execute(request, broker)
        expect(result, 'unknown', 'runner_deadline_exceeded')
        if self.j.body['physical_starts'].get(request.run_id) != 1:
            raise Inconclusive('no_live_runner_to_suspend')
        require(broker.cleanup(request.run_id))

    def cleanup_guards(self):
        r = self.r
        target = r.target()
        r.configure(target, {'bind': '0.0.0.0', 'response_delay': 1})
        def guard(obj, plan):
            handle = Runner(obj.id, r.approval.runner_image, plan.run_id, r.scope, True)
            checks = [not r.adapter.cleanup(replace(handle, container_id=target['id'], image_id=r.approval.target_image)),
                      not r.adapter.cleanup(replace(handle, image_id='sha256:' + '0' * 64)),
                      not r.adapter.cleanup(replace(handle, scope='poc-foreign')),
                      not r.adapter.cleanup(replace(handle, run_id='00000000-0000-4000-8000-000000000000'))]
            self.j.body['cleanup_guard_checks'] = checks
        r.adapter.action = guard
        request = r.issue(target)
        result = r.execute(request)
        checks = self.j.body.get('cleanup_guard_checks')
        if checks is not None:
            require(len(checks) == 4 and all(checks))
        expect(result, 'passed', 'probe_passed')
        require(r.broker.cleanup(request.run_id))
        require(r.broker.cleanup(request.run_id))
        r.owned_target(target)  # Guard probes did not remove the target.

    def run(self):
        self.case('create_register_race_late_ownership_cleanup', self.create_register_race)
        self.case('localhost_then_network_bind', self.basic)
        self.case('short_runner_repetitions', self.repetitions_case)
        self.case('security_configuration_and_behavior', self.security)
        for mode in ('stopped', 'restart', 'started_at', 'generation', 'stale_id',
                     'disappear_during', 'wrong_network', 'extra_network'):
            self.case('identity_' + mode, lambda mode=mode: self.identity(mode))
        self.case('duplicate_concurrent_busy_and_restart', self.concurrency)
        self.case('deadline_and_late_result', self.timeout)
        self.case('runner_crash', self.crash)
        self.case('suspended_runner_deadline_cleanup', self.hung_runner)
        self.case('exact_cleanup_guards_and_replay', self.cleanup_guards)
        for name in ('docker_api_timeout', 'start_failure', 'lost_create_response',
                     'lost_cleanup_response', 'unregistered_orphan_reconciliation'):
            self.j.body['scenarios'].append({'name': name, 'status': 'NOT RUN',
                'reason': 'suite_halted' if self.stopped else 'fake_only_not_injected_into_daemon',
                'started_at': None, 'finished_at': None})
        statuses = {item['status'] for item in self.j.body['scenarios']}
        self.j.body['status'] = ('test_failed' if 'test_failed' in statuses else
                                'test_inconclusive' if statuses & {'test_inconclusive','NOT RUN'} else 'test_passed')
        self.j.body['finished_at'] = timestamp()
        self.j.report()
