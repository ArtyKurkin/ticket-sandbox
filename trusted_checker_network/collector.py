"""Independent bounded capture verification. Sole I/O port is MockNetworkHost."""
from dataclasses import dataclass
from uuid import uuid4
import hashlib
import time
from trusted_checker_runtime.contracts import uid,full_id,stamp,scope
from trusted_checker_runtime.profiles import require,Denied
from .contracts import HostSnapshot,NetworkApproval,CASES,POLICY,MODE
from .host import MockNetworkHost
from .packets import plan, classify_reply, unpad
from .store import normalize


@dataclass(frozen=True)
class PacketEvent:
    sequence: int
    probe_id: str
    stage: str
    interface: str
    frame: bytes
    observed_at: float
    rules_digest: str
    generation: int

    def __post_init__(self):
        full_id(self.probe_id);full_id(self.rules_digest);stamp(self.observed_at)
        require(type(self.sequence) is int and self.sequence > 0 and self.stage in
                ('send','ingress','drop','target_ingress','response','runner_receive') and
                type(self.frame) is bytes and 14 <= len(self.frame) <= POLICY.frame_bytes and
                type(self.generation) is int and self.generation > 0 and type(self.interface) is str and
                len(self.interface) <= 15, 'packet_event_invalid')


@dataclass(frozen=True)
class Capture:
    context_uuid: str
    scope: str
    binding_digest: str
    generation: int
    rules_digest: str
    before: HostSnapshot
    after: HostSnapshot
    started_at: float
    finished_at: float
    packets_received: int
    packets_dropped: int
    netlink_lost: int
    truncated: bool
    endpoint_available: bool
    error: str
    events: tuple[PacketEvent,...]
    mode: str = MODE

    def __post_init__(self):
        uid(self.context_uuid);scope(self.scope);full_id(self.binding_digest);full_id(self.rules_digest)
        stamp(self.started_at);stamp(self.finished_at)
        require(type(self.before) is HostSnapshot and type(self.after) is HostSnapshot and
                type(self.events) is tuple and len(self.events) <= POLICY.packet_limit and
                all(type(e) is PacketEvent for e in self.events) and
                all(type(n) is int and n >= 0 for n in (self.packets_received,self.packets_dropped,self.netlink_lost,self.generation)) and
                type(self.truncated) is bool and type(self.endpoint_available) is bool and
                self.error in ('none','collector_error','endpoint_unavailable') and self.mode == MODE and
                0 <= self.finished_at-self.started_at <= POLICY.matrix_seconds, 'capture_contract_invalid')
        self.before.__post_init__();self.after.__post_init__()
        for event in self.events: event.__post_init__()


@dataclass(frozen=True)
class MatrixReceipt:
    receipt_uuid: str
    context_uuid: str
    scope: str
    binding_digest: str
    install_generation: int
    rules_digest: str
    capture_digest: str
    cases: tuple[str,...]
    outcomes: tuple[str,...]
    observed_at: float
    mode: str = MODE

    def __post_init__(self):
        uid(self.receipt_uuid);uid(self.context_uuid);scope(self.scope)
        for value in (self.binding_digest,self.rules_digest,self.capture_digest):full_id(value)
        stamp(self.observed_at)
        require(type(self.install_generation) is int and self.install_generation > 0 and self.cases == CASES and
                type(self.outcomes) is tuple and len(self.outcomes) == 15 and self.outcomes[0] in
                ('path_open_rst','path_open_synack') and all(v == 'blocked_at_hook' for v in self.outcomes[1:]) and
                self.mode == MODE, 'matrix_incomplete')


class IndependentCollector:
    def __init__(self, store, host, installer, signer, verifier, clock, *, monotonic=time.monotonic):
        require(type(host) is MockNetworkHost and installer.host is host and signer.principal.role == 'validator' and
                signer.principal.name != host.signer.principal.name, 'mock_independent_collector_required')
        self.store,self.host,self.installer,self.signer,self.verifier,self.clock = store,host,installer,signer,verifier,clock
        self.monotonic = monotonic

    def _alive(self, approval, deadline):
        require(not self.store.stopped() and self.clock() < min(deadline,approval.expires_at), 'matrix_cancelled_or_expired')

    def measure(self, approval, context_uuid, deadline):
        uid(context_uuid)
        try:
            self._alive(approval,deadline)
            monotonic_end = self.monotonic()+min(POLICY.matrix_seconds,deadline-self.clock())
            installed = self.installer.check(approval,active=True)
            probes = plan(approval.binding,context_uuid)
            signed = self.host.capture(approval,{'context_uuid':context_uuid,'probes':probes,'deadline':deadline,
                                               'generation':installed.generation,'rules_digest':installed.rules_digest})
            capture = self.verifier.verify(signed,'capture',Capture,approval.scope)
            self._alive(approval,deadline)
            outcomes = self.validate(approval,context_uuid,installed,capture,probes)
            self.installer.check(approval,active=True)  # Independent readback after capture too.
            self._alive(approval,deadline)
            require(self.monotonic() < monotonic_end,'matrix_cancelled_or_expired')
            # Raw packet bytes/signatures are never archived or exported.
            receipt = MatrixReceipt(str(uuid4()),context_uuid,approval.scope,approval.binding.digest,
                                    installed.generation,installed.rules_digest,
                                    hashlib.sha256(signed.signature.encode()).hexdigest(),CASES,outcomes,self.clock())
            signed_receipt = self.signer.sign('matrix',receipt)
            with self.store.transaction() as db:
                self.store.put(db,'matrix',context_uuid,receipt)
                self.store.event(db,context_uuid,'matrix_verified')
            return signed_receipt
        except Exception as error:
            # Any incomplete proof closes the whole scope; no silent retries.
            self.store.stop()
            reasons = {'capture_loss','stale_capture','capture_binding_mismatch','capture_endpoint_unavailable',
                       'capture_collector_error','attachment_event_during_capture','capture_identity_drift',
                       'probe_packet_chain_incomplete','forged_network_receipt','matrix_cancelled_or_expired',
                       'independent_rules_readback_mismatch','capture_sequence_gap','foreign_packet_trace',
                       'drop_trace_unproven','allow_packet_delivery_unproven','reply_flow_invalid','reply_l2_invalid',
                       'reply_ipv4_invalid'}
            # Only constants generated by our validators, never exception text
            # from a backend/driver. No signature, frames, stderr or API body.
            reason = str(error) if type(error) is Denied and str(error) in reasons else 'collector_boundary_unknown'
            with self.store.transaction() as db:
                self.store.put(db,'matrix_unknown',context_uuid,{'result':'unknown','reason':reason,
                    'binding':approval.binding.digest,'at':self.clock()})
            raise Denied('network_matrix_unknown') from None

    def validate(self, approval, context_uuid, installed, capture, probes):
        require((capture.context_uuid,capture.binding_digest,capture.generation,capture.rules_digest) ==
                (context_uuid,approval.binding.digest,installed.generation,installed.rules_digest), 'capture_binding_mismatch')
        require(capture.endpoint_available and capture.error != 'endpoint_unavailable','capture_endpoint_unavailable')
        require(capture.error == 'none','capture_collector_error')
        require(not capture.truncated and capture.packets_dropped == 0 and capture.netlink_lost == 0 and
                capture.packets_received == len(capture.events) and len(capture.events) > 0, 'capture_loss')
        require(0 <= self.clock()-capture.finished_at <= POLICY.observation_age and
                approval.created_at <= capture.started_at <= capture.finished_at <= self.clock(), 'stale_capture')
        for snapshot in (capture.before,capture.after):
            snapshot.__post_init__()
            require(snapshot.binding == approval.binding and snapshot.netlink_lost == 0 and
                    not snapshot.foreign_bridge_hooks and
                    capture.started_at <= snapshot.observed_at <= capture.finished_at and
                    snapshot.netlink_sequence_start == snapshot.netlink_sequence_end, 'capture_identity_drift')
        require(capture.before.netlink_sequence_end == capture.after.netlink_sequence_start,'attachment_event_during_capture')
        require(tuple(e.sequence for e in capture.events) == tuple(range(1,len(capture.events)+1)), 'capture_sequence_gap')
        ids = {p.probe_id for p in probes}
        require(all(e.probe_id in ids and e.generation == capture.generation and e.rules_digest == capture.rules_digest and
                    capture.started_at <= e.observed_at <= capture.finished_at for e in capture.events), 'foreign_packet_trace')
        outcomes = []
        b = approval.binding
        for probe in probes:
            events = tuple(e for e in capture.events if e.probe_id == probe.probe_id)
            stages = tuple(e.stage for e in events)
            expected = ('send','ingress','target_ingress','response','runner_receive') if probe.response_required else ('send','ingress','drop')
            require(stages == expected,'probe_packet_chain_incomplete')
            for e in events[:2]:
                require(unpad(e.frame) == probe.frame and e.interface == b.runner.interface,'probe_ingress_mismatch')
            if probe.response_required:
                require(unpad(events[2].frame) == probe.frame and events[2].interface == b.target.interface and
                        events[3].interface == b.target.interface and events[4].interface == b.runner.interface and
                        unpad(events[3].frame) == unpad(events[4].frame),'allow_packet_delivery_unproven')
                outcomes.append(classify_reply(probe,b,events[4].frame))
            else:
                require(unpad(events[2].frame) == probe.frame and events[2].interface == b.runner.interface,'drop_trace_unproven')
                outcomes.append('blocked_at_hook')
        return tuple(outcomes)
