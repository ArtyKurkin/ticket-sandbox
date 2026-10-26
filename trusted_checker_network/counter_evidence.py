"""Pure fixture verification with process-local OFF/lease/terminal fences.

No physical backend, store migration, installer call, HTTP release or runtime
authorization port. Restart cannot resume a measurement or import its receipts.
"""
from dataclasses import asdict, dataclass
import json
import threading
import time

from trusted_checker_runtime.contracts import stamp
from trusted_checker_runtime.profiles import require, Denied
from .counter_auth import FixtureAuthenticator, SignedCounter
from .counter_contracts import CounterApproval, CounterEvidence, SampleResult, UNKNOWN_REASONS
from .counter_inventory import check_topology
from .counter_readback import validate_readback
from .counter_rules import compile_counter_rules, sample_plan
from .packets import classify_reply, unpad
from trusted_checker_shadow.policy import digest


@dataclass(frozen=True)
class SampleFixture:
    before: object
    packets: object
    after: object


@dataclass(frozen=True)
class MeasurementFixture:
    topology_before: object
    samples: tuple[SampleFixture, ...]
    topology_after: object


class OfflineCounterVerifier:
    def __init__(self, auth, signed_approval, *, clock=time.time, monotonic=time.monotonic):
        require(type(auth) is FixtureAuthenticator and type(signed_approval) is SignedCounter and
                type(signed_approval.payload) is CounterApproval,
                'counter_fixture_boundary_required')
        self.approval = auth.verify(signed_approval, 'approval', signed_approval.payload.scope)
        self.auth, self.clock, self.monotonic = auth, clock, monotonic
        self.enabled = False; self.epoch = 0; self.stopped = False; self.circuit = False
        self._lock = threading.RLock(); self._reservation = None; self._terminal = None
        self._last_wall = clock()

    def set_enabled(self, enabled):
        require(type(enabled) is bool, 'counter_flag_invalid')
        with self._lock:
            self.enabled = enabled; self.epoch += 1

    def kill(self):
        with self._lock:
            self.stopped = True; self.enabled = False; self.epoch += 1

    def _gate(self):
        now = self.clock(); stamp(now)
        require(now >= self._last_wall, 'counter_clock_rollback'); self._last_wall = now
        require(not self.stopped and self.enabled, 'counter_killed')
        a = self.approval
        require(a.created_at <= now < a.expires_at and a.runtime.created_at <= now < a.runtime.expires_at,
                'counter_deadline')
        if self._reservation:
            start, deadline, monotonic_end, epoch = self._reservation
            require(self.epoch == epoch, 'counter_killed')
            require(now < deadline and self.monotonic() < monotonic_end, 'counter_deadline')
        return now

    def begin(self, absolute_deadline):
        """One reservation for the approved context; no side effects or retries."""
        with self._lock:
            self._gate(); stamp(absolute_deadline)
            require(not self.circuit and self._reservation is None and self._terminal is None,
                    'counter_measurement_in_progress_or_closed')
            now = self.clock()
            require(now < absolute_deadline <= min(now+2, self.approval.expires_at), 'counter_deadline')
            self._reservation = (now, absolute_deadline, self.monotonic()+absolute_deadline-now, self.epoch)
            return self.approval.context_uuid

    def _context(self, observation):
        a = self.approval
        require(observation.context_uuid == a.context_uuid and observation.scope == a.scope and
                observation.approval_digest == a.digest and observation.install_epoch_uuid == a.install_epoch_uuid and
                observation.generation == a.install_generation, 'counter_generation_changed')

    def _sample(self, fixture, index):
        a = self.approval
        require(type(fixture) is SampleFixture, 'counter_evidence_invalid')
        before = self.auth.verify(fixture.before, 'readback', a.scope)
        packets = self.auth.verify(fixture.packets, 'packets', a.scope)
        after = self.auth.verify(fixture.after, 'readback', a.scope)
        self._context(packets)
        require(packets.probe_index == index and packets.dropped == 0 and packets.truncated is False,
                'counter_packet_incomplete')
        require(before.finished_at <= packets.started_at <= packets.finished_at <= after.started_at,
                'counter_evidence_invalid')
        values_before, values_after = validate_readback(before, a), validate_readback(after, a)
        probe = sample_plan(a.binding, a.context_uuid)[index]
        stages = ('send', 'ingress', 'target_ingress', 'response', 'runner_receive') if index == 0 else ('send', 'ingress')
        require(len(packets.events) == len(stages) and tuple(e.stage for e in packets.events) == stages,
                'counter_packet_incomplete')
        require(tuple(e.sequence for e in packets.events) == tuple(range(1, len(stages)+1)), 'counter_packet_incomplete')
        outcome = 'terminal_drop_observed'; reply = None
        for e in packets.events:
            require(e.probe_id == probe.probe_id and e.rules_digest == a.rules_digest and
                    e.generation == a.install_generation and packets.started_at <= e.observed_at <= packets.finished_at,
                    'counter_packet_incomplete')
            interface = a.binding.target.interface if e.stage in ('target_ingress', 'response') else a.binding.runner.interface
            require(e.interface == interface, 'counter_packet_incomplete')
            if e.stage in ('response', 'runner_receive'):
                observed = classify_reply(probe, a.binding, e.frame)
                require(reply is None or unpad(e.frame) == reply, 'counter_packet_incomplete')
                reply = unpad(e.frame); outcome = observed
            else: require(unpad(e.frame) == probe.frame, 'counter_packet_incomplete')
        recipe = compile_counter_rules(a.approval_uuid, a.runtime, a.binding, a.context_uuid)
        commands = json.loads(recipe.json)['nftables']
        changes = {}
        for spec in recipe.counters:
            if spec.probe_index == index and spec.purpose in ('ingress', 'terminal_drop'):
                changes[spec.identity] = (1, len(probe.frame))
            elif index == 0 and spec.purpose == 'allow':
                rule = commands[spec.object_index]['add']['rule']
                # Exactly four TCP allow counters: request/return at both hooks.
                fields = [m.get('match', {}).get('left', {}).get('payload', {}) for m in rule['expr']]
                if {'protocol': 'tcp', 'field': 'dport'} in fields:
                    changes[spec.identity] = (1, len(probe.frame))
                elif {'protocol': 'tcp', 'field': 'sport'} in fields:
                    changes[spec.identity] = (1, len(reply))
        for x,y in zip(values_before, values_after):
            require((y.packets >= x.packets and y.bytes >= x.bytes), 'counter_reset_or_wrap')
            require((y.packets-x.packets, y.bytes-x.bytes) == changes.get(x.identity, (0, 0)),
                    'counter_delta_unexplained')
        return SampleResult(probe.probe_id, probe.case, outcome, before.started_at, after.finished_at,
                            values_before, values_after)

    def finish(self, fixture):
        with self._lock:
            if self._terminal is not None: return self._terminal
            require(self._reservation is not None, 'counter_measurement_not_issued')
            results = []; reason = 'offline_counter_model_verified'; result = 'verified'
            topology_before = topology_after = None
            try:
                self._gate()
                require(type(fixture) is MeasurementFixture and type(fixture.samples) is tuple and
                        len(fixture.samples) == 15, 'counter_evidence_invalid')
                a = self.approval
                before = self.auth.verify(fixture.topology_before, 'topology', a.scope)
                after = self.auth.verify(fixture.topology_after, 'topology', a.scope)
                try: check_topology(before, a); check_topology(after, a)
                except Denied: raise Denied('counter_topology_unproven') from None
                topology_before, topology_after = digest(asdict(before)), digest(asdict(after))
                require(self._reservation[0] <= before.observed_at <= after.observed_at <= self.clock() and
                        after.observed_at-before.observed_at <= 2, 'counter_evidence_invalid')
                previous = None
                for index, sample in enumerate(fixture.samples):
                    self._gate()
                    measured = self._sample(sample, index)
                    require(before.observed_at <= measured.started_at <= measured.finished_at <= after.observed_at,
                            'counter_evidence_invalid')
                    if previous is not None:
                        require(previous.finished_at <= measured.started_at, 'counter_evidence_invalid')
                        require(previous.after == measured.before, 'counter_delta_unexplained')
                    results.append(measured); previous = measured
                self._gate()
            except Denied as error:
                result = 'unknown'; reason = str(error) if str(error) in UNKNOWN_REASONS else 'counter_evidence_invalid'
            except Exception:
                result = 'unknown'; reason = 'counter_evidence_invalid'
            # No raw input, exception text or packet bodies survive into report.
            now = self.clock(); start, deadline, _, _ = self._reservation
            finished = max(start, min(now, deadline))
            self._terminal = CounterEvidence(self.approval.context_uuid, self.approval, tuple(results),
                                              start, finished, result, reason, deadline, now,
                                              topology_before, topology_after)
            self.circuit = result == 'unknown'
            return self._terminal

    def expire(self):
        """Closes an issued run after kill/deadline without accepting late evidence."""
        with self._lock:
            require(self._reservation is not None, 'counter_measurement_not_issued')
            if self._terminal is not None: return self._terminal
            try: self._gate()
            except Denied: return self.finish(None)
            raise Denied('counter_measurement_not_expired')

    def issued_report(self, signed):
        report = self.auth.verify(signed, 'evidence', self.approval.scope)
        require(self._terminal is not None and report.digest == self._terminal.digest, 'counter_report_not_issued')
        return self._terminal
