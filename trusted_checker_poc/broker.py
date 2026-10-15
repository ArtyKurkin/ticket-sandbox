"""Local, authenticated-by-caller PoC API. No HTTP listener and no Django hooks."""
from dataclasses import asdict, replace
import json
import queue
import secrets
import threading
import time

from .contracts import AdapterError, InvalidRequest, Result, Runner, Target, digest, timestamp, full_id
from .lifecycle import Lifecycle


class Broker:
    _threads = threading.BoundedSemaphore(4)

    def __init__(self, state, registry, adapter, *, scope, max_parallel=2):
        if not scope.startswith('poc-') or type(max_parallel) is not int or not 1 <= max_parallel <= 2:
            raise ValueError('isolated_broker_configuration_required')
        self.state, self.registry, self.adapter = state, registry, adapter
        self.scope, self.max_parallel = scope, max_parallel

    def issue(self, target_id, owner, policy_id):
        # owner is an authenticated transport identity, never trusted from JSON.
        policy = self.registry.get(policy_id)
        return self.state.issue(target_id, owner, policy_id, asdict(policy) if policy else None)

    def _result(self, row, policy, reason, *, result='unknown', failure='infrastructure',
                observed=None, runner=None, evidence=None, cleanup='recorded_separately', identity_bracketed=False):
        runtime = bool(policy and runner and runner.config_verified and
                       runner.image_id == policy.runner_image_id and runner.scope == self.scope and runner.run_id == row['id'])
        identity = identity_bracketed and observed == json.loads(row['target'])
        return Result(row['id'], policy.checker_id if policy else 'unknown', policy.checker_version if policy else 'unknown',
                      policy.adapter_id if policy else 'unknown', policy.adapter_version if policy else 'unknown',
                      json.loads(row['target']), observed, asdict(runner) if runner else None,
                      row['requested_at'], row['started_at'], timestamp(), result, failure,
                      {'checker_runtime': 'verified_configuration' if runtime else 'unknown',
                       'target_identity': 'matched_before_and_after' if identity else 'unknown',
                       'target_fixture': 'unknown', 'observation_consistency': 'bounded_probe_only' if identity else 'unknown',
                       'criteria_validity': 'synthetic_ipv4_behavior_only',
                       'cryptographic_attestation': False},
                      digest(evidence or {'reason':reason}), reason, cleanup, asdict(policy) if policy else {}).to_dict()

    def execute(self, request, *, owner):
        from .contracts import Request
        # Always revalidate, even when called with a manually constructed dataclass.
        request = Request.parse(asdict(request) if isinstance(request, Request) else request)
        policy = self.registry.get(request.policy_id)
        budget = policy.timeout if policy else 1.0
        status = self.state.admit(request, owner, self.max_parallel, time.time()+budget)
        row = self.state.read(request.run_id)
        if row['result']:
            return json.loads(row['result'])
        if status == 'running':
            # Recovery describes the originally issued policy, even if a new
            # operator process now uses a different timeout/artifact registry.
            from .registry import Policy
            saved_policy = json.loads(row['policy'])
            policy = Policy(**saved_policy) if saved_policy else None
            if row['deadline'] <= time.time():
                self.state.finish(request.run_id, self._result(row, policy, 'execution_outcome_unknown', failure='unknown_execution'))
                self.cleanup(request.run_id)
                return json.loads(self.state.read(request.run_id)['result'])
            return self._result(row, policy, 'execution_in_progress', failure='unknown_execution')
        if status != 'admitted':
            return self._result(row, policy, status, failure='broker_capacity')
        if json.loads(row['policy']) != (asdict(policy) if policy else None):
            from .registry import Policy
            issued_policy = Policy(**json.loads(row['policy'])) if json.loads(row['policy']) else None
            self.state.finish(request.run_id, self._result(row, issued_policy, 'policy_changed_since_issue', failure='policy'))
            self.state.release(request.run_id)
            return json.loads(self.state.read(request.run_id)['result'])
        if policy is None or policy.schema_version != request.schema_version:
            self.state.finish(request.run_id, self._result(row, policy, 'policy_unsupported', failure='policy'))
            self.state.release(request.run_id)
            return json.loads(self.state.read(request.run_id)['result'])
        if policy.runner_image_id is None:
            self.state.finish(request.run_id, self._result(row, policy, 'artifact_not_provisioned', failure='integrity'))
            self.state.release(request.run_id)
            return json.loads(self.state.read(request.run_id)['result'])
        if not self._threads.acquire(blocking=False):
            self.state.finish(request.run_id, self._result(row, policy, 'broker_thread_capacity', failure='broker_capacity'))
            self.state.release(request.run_id)
            return json.loads(self.state.read(request.run_id)['result'])
        expected = Target(**json.loads(row['target']))
        results = queue.Queue(maxsize=1)
        deadline = time.monotonic()+budget
        challenge = secrets.token_hex(32)
        approval = getattr(self.adapter, 'approval', None)
        lifecycle = Lifecycle(self.state, request.run_id, deadline,
                              approval.daemon_id if approval else 'fake-adapter',
                              getattr(self.adapter, 'integration_id', None),
                              getattr(self.adapter, 'record_prepare_event', None))

        def operation():
            observed, runner = None, None
            prepare_attempted = False
            try:
                observed = self.adapter.inspect_target(expected.container_id)
                if observed != expected or observed.scope != self.scope:
                    raise AdapterError('target_identity_mismatch', 'identity')
                lifecycle.check()
                plan = self.adapter.plan(policy, expected, request.run_id, challenge)
                intent = lifecycle.begin(challenge)
                plan = replace(plan, intent=intent, lifecycle=lifecycle)
                prepare_attempted = True  # A lost create response is ambiguous from here.
                runner = self.adapter.prepare(plan)
                # Real adapter records the raw ID before inspect. Fake/custom
                # adapters returning a handle are still tied to the same intent.
                if not lifecycle.trace.ownership_persisted:
                    lifecycle.received(runner.container_id)
                lifecycle.check()
                if not self.state.register_runner(request.run_id, runner):
                    raise AdapterError('execution_closed', 'unknown_execution')
                if (not full_id(runner.container_id) or not runner.config_verified or runner.image_id != policy.runner_image_id or
                        runner.run_id != request.run_id or runner.scope != self.scope):
                    raise AdapterError('runner_identity_mismatch', 'integrity')
                remaining = deadline-time.monotonic()
                if remaining <= 0:
                    raise AdapterError('runner_deadline_exceeded','timeout')
                lifecycle.check()
                outcome = self.adapter.run(plan, runner, remaining)
                lifecycle.check()
                after = self.adapter.inspect_target(expected.container_id)
                observed = after
                if after != expected:
                    raise AdapterError('target_changed_during_execution', 'identity')
                allowed = {'probe_passed':'passed','service_unreachable':'failed',
                           'unexpected_http_response':'failed','redirect_rejected':'failed',
                           'probe_timeout':'unknown','probe_transport_error':'unknown'}
                if allowed.get(outcome.reason) != outcome.result:
                    raise AdapterError('runner_protocol_invalid', 'runner')
                failure = 'none' if outcome.result == 'passed' else 'technical' if outcome.result == 'failed' else 'timeout' if outcome.reason == 'probe_timeout' else 'infrastructure'
                results.put((self._result(row, policy, outcome.reason, result=outcome.result, failure=failure,
                                         observed=asdict(observed), runner=runner, evidence=outcome.evidence, identity_bracketed=True), False))
            except Exception as error:
                lifecycle.trace.fail(error)
                reason = error.reason if isinstance(error, AdapterError) else 'adapter_failure'
                failure = error.failure_class if isinstance(error, AdapterError) else 'infrastructure'
                if failure == 'integrity' and runner is not None:
                    runner = replace(runner,config_verified=False)
                results.put((self._result(row, policy, reason, failure=failure,
                                         observed=asdict(observed) if observed else None, runner=runner), not prepare_attempted))
            finally:
                # A late ID is cleanup-only and can now be recovered after the
                # terminal receipt, without rewriting runs.runner or its verdict.
                try:
                    self.cleanup(request.run_id)
                except Exception:
                    pass  # Storage/API unavailable: durable ownership/lease remain for retry.
                finally:
                    self._threads.release()

        threading.Thread(target=operation, daemon=True).start()
        no_create_proven = False
        timeout_event = None
        try:
            result, no_create_proven = results.get(timeout=max(0, deadline-time.monotonic()))
            if time.monotonic() > deadline:
                raise queue.Empty
        except queue.Empty:
            lifecycle.cancelled.set()
            timeout_event = lifecycle.trace.snapshot('timeout', 'deadline_expired', update_stage=False)
            result = self._result(row, policy, 'runner_deadline_exceeded', failure='timeout')
        self.state.finish(request.run_id, result)  # CAS: never replace a recovered terminal result.
        if timeout_event is not None:
            lifecycle.trace.write(timeout_event)
        lifecycle.cancelled.set()
        if no_create_proven:
            # The operation returned before invoking prepare. A timed-out thread
            # still in inspect/prepare, or an unknown create, NEVER takes this path.
            self.state.release(request.run_id)
        self.cleanup(request.run_id)
        return json.loads(self.state.read(request.run_id)['result'])

    def cleanup(self, run_id):
        """Operator/internal API, exact recorded runner identity only. No list/prune."""
        row = self.state.read(run_id)
        if not row or row['status'] != 'finished':
            return False
        ownership = self.state.receipt('runner_ownership', run_id)
        if ownership:
            runner = Runner(ownership['container_id'], ownership['image_id'], run_id, ownership['scope'], False)
        elif row['runner']:
            runner = Runner(**json.loads(row['runner']))
        else:
            return False
        def remove_owned():
            if ownership and hasattr(self.adapter, 'cleanup_owned'):
                return self.adapter.cleanup_owned(runner, intent, ownership['daemon_id'])
            return self.adapter.cleanup(runner)
        intent = self.state.receipt('create_intents', run_id)
        try:
            return self.state.confirm_cleanup(run_id, remove_owned)
        except Exception:
            return False
