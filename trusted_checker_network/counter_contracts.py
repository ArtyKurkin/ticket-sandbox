"""nft_counter_probe_v1: immutable OFFLINE evidence; never a live gate token."""
from dataclasses import asdict, dataclass
import json

from trusted_checker_runtime.contracts import RuntimeApproval, full_id, stamp, uid
from trusted_checker_runtime.profiles import require
from trusted_checker_shadow.policy import digest
from .contracts import NetworkBinding
from .counter_inventory import ControlModel, expected_paths
from .counter_rules import compile_counter_rules, sample_plan

METHOD = 'nft_counter_probe_v1'
ORIGIN = 'offline_counter_fixture'
SCOPE = 'runner_external_ipv4_tcp_target_8080_with_peer_arp'
MAXIMUM = 2**63-1


@dataclass(frozen=True)
class CounterApproval:
    approval_uuid: str
    context_uuid: str
    operator: str
    runtime: RuntimeApproval
    binding: NetworkBinding
    control: ControlModel
    install_epoch_uuid: str
    install_generation: int
    object_handles: tuple[int, ...]
    rules_digest: str
    created_at: float
    expires_at: float
    dedicated_vm: bool = True
    method: str = METHOD
    version: int = 1
    origin: str = ORIGIN

    def __post_init__(self):
        from trusted_checker_runtime.contracts import atom
        uid(self.approval_uuid); uid(self.context_uuid); uid(self.install_epoch_uuid); atom(self.operator, 'operator:')
        require(type(self.runtime) is RuntimeApproval and type(self.binding) is NetworkBinding and
                type(self.control) is ControlModel, 'counter_approval_types')
        self.runtime.__post_init__(); self.binding.__post_init__(); self.control.__post_init__()
        full_id(self.rules_digest); stamp(self.created_at); stamp(self.expires_at)
        recipe = compile_counter_rules(self.approval_uuid, self.runtime, self.binding, self.context_uuid)
        require(self.rules_digest == recipe.digest and self.method == METHOD and type(self.version) is int and
                self.version == 1 and self.origin == ORIGIN and self.dedicated_vm is True and
                0 < self.expires_at-self.created_at <= 3600 and self.created_at >= self.runtime.created_at and
                self.expires_at <= self.runtime.expires_at and type(self.install_generation) is int and
                self.install_generation > 0, 'counter_approval_invalid')
        require(type(self.object_handles) is tuple and len(self.object_handles) == len(json.loads(recipe.json)['nftables'])
                and all(type(h) is int and h > 0 for h in self.object_handles) and
                len(set(self.object_handles)) == len(self.object_handles), 'counter_handle_binding_invalid')
        expected_paths(self.binding, self.runtime.network.subnet)

    @property
    def scope(self): return self.binding.scope
    @property
    def digest(self): return digest(asdict(self))


@dataclass(frozen=True)
class CounterValue:
    identity: str
    family: str
    table: str
    chain: str
    rule_handle: int
    expression_index: int
    packets: int
    bytes: int

    def __post_init__(self):
        full_id(self.identity)
        require(type(self.packets) is int and type(self.bytes) is int and 0 <= self.packets <= MAXIMUM and
                0 <= self.bytes <= MAXIMUM and type(self.rule_handle) is int and self.rule_handle > 0 and
                type(self.expression_index) is int and self.expression_index >= 0, 'counter_value_invalid')


@dataclass(frozen=True)
class ReadbackFixture:
    context_uuid: str
    scope: str
    approval_digest: str
    install_epoch_uuid: str
    generation: int
    started_at: float
    finished_at: float
    json: str
    origin: str = ORIGIN

    def __post_init__(self):
        uid(self.context_uuid); uid(self.install_epoch_uuid); full_id(self.approval_digest)
        stamp(self.started_at); stamp(self.finished_at)
        require(type(self.generation) is int and self.generation > 0 and self.origin == ORIGIN and
                0 <= self.finished_at-self.started_at <= 2 and type(self.json) is str and
                len(self.json.encode()) <= 262144, 'counter_readback_contract')


@dataclass(frozen=True)
class PacketFixture:
    context_uuid: str
    scope: str
    approval_digest: str
    install_epoch_uuid: str
    generation: int
    probe_index: int
    started_at: float
    finished_at: float
    events: tuple
    dropped: int = 0
    truncated: bool = False
    origin: str = ORIGIN

    def __post_init__(self):
        from .collector import PacketEvent
        uid(self.context_uuid); uid(self.install_epoch_uuid); full_id(self.approval_digest)
        stamp(self.started_at); stamp(self.finished_at)
        require(type(self.generation) is int and self.generation > 0 and type(self.probe_index) is int and
                0 <= self.probe_index < 15 and type(self.events) is tuple and len(self.events) <= 8 and
                all(type(e) is PacketEvent for e in self.events) and type(self.dropped) is int and self.dropped >= 0 and
                type(self.truncated) is bool and self.origin == ORIGIN and
                0 <= self.finished_at-self.started_at <= 2, 'counter_packet_contract')
        for e in self.events: e.__post_init__()


@dataclass(frozen=True)
class SampleResult:
    probe_id: str
    case: str
    outcome: str
    started_at: float
    finished_at: float
    before: tuple[CounterValue, ...]
    after: tuple[CounterValue, ...]

    def __post_init__(self):
        full_id(self.probe_id); stamp(self.started_at); stamp(self.finished_at)
        require(self.outcome in ('path_open_rst', 'path_open_synack', 'terminal_drop_observed') and
                0 <= self.finished_at-self.started_at <= 2 and type(self.before) is tuple and
                type(self.after) is tuple and 0 < len(self.before) == len(self.after) <= 128,
                'counter_sample_result_invalid')
        for collection in (self.before, self.after):
            require(all(type(v) is CounterValue for v in collection) and
                    len({v.identity for v in collection}) == len(collection), 'counter_sample_result_invalid')
            for v in collection: v.__post_init__()
        require(all((x.identity,x.family,x.table,x.chain,x.rule_handle,x.expression_index) ==
                    (y.identity,y.family,y.table,y.chain,y.rule_handle,y.expression_index)
                    for x,y in zip(self.before,self.after)), 'counter_sample_result_invalid')


@dataclass(frozen=True)
class CounterEvidence:
    context_uuid: str
    approval: CounterApproval
    samples: tuple[SampleResult, ...]
    started_at: float
    finished_at: float
    result: str
    reason: str
    absolute_deadline: float
    finalized_at: float
    topology_before_digest: str | None = None
    topology_after_digest: str | None = None
    method: str = METHOD
    version: int = 1
    verification_scope: str = SCOPE
    topology_assumptions: str = 'trusted_exclusive_control_plane_offline_review_fixture'
    continuous_attestation: bool = False
    trace_delivery_complete: str = 'unproven'
    physical_probe_permitted: bool = False
    byte_accounting: str = 'offline_frame_bytes_not_kernel_verified'
    origin: str = ORIGIN

    def __post_init__(self):
        uid(self.context_uuid); require(type(self.approval) is CounterApproval, 'counter_report_approval')
        self.approval.__post_init__(); stamp(self.started_at); stamp(self.finished_at)
        stamp(self.absolute_deadline); stamp(self.finalized_at)
        require(self.context_uuid == self.approval.context_uuid and self.method == METHOD and
                type(self.version) is int and self.version == 1 and self.verification_scope == SCOPE and
                self.topology_assumptions == 'trusted_exclusive_control_plane_offline_review_fixture' and
                self.continuous_attestation is False and self.trace_delivery_complete == 'unproven' and
                self.physical_probe_permitted is False and self.origin == ORIGIN and type(self.samples) is tuple and
                self.byte_accounting == 'offline_frame_bytes_not_kernel_verified' and
                len(self.samples) <= 15 and all(type(s) is SampleResult for s in self.samples) and
                0 <= self.finished_at-self.started_at <= 2, 'counter_evidence_contract')
        for sample in self.samples: sample.__post_init__()
        for value in (self.topology_before_digest, self.topology_after_digest):
            if value is not None: full_id(value)
        expected = sample_plan(self.approval.binding, self.context_uuid)
        require(all((s.probe_id, s.case) == (p.probe_id, p.case) for s,p in zip(self.samples, expected)) and
                self.started_at < self.absolute_deadline <= self.started_at+2,
                'counter_evidence_contract')
        require((self.result == 'verified' and self.reason == 'offline_counter_model_verified' and len(self.samples) == 15)
                or (self.result == 'unknown' and self.reason in UNKNOWN_REASONS), 'counter_evidence_result')
        if self.result == 'verified':
            require(self.topology_before_digest is not None and self.topology_after_digest is not None and
                    self.finished_at <= self.finalized_at < self.absolute_deadline and
                    self.samples[0].outcome in ('path_open_rst','path_open_synack') and
                    all(s.outcome == 'terminal_drop_observed' for s in self.samples[1:]), 'counter_evidence_result')

    @property
    def scope(self): return self.approval.scope
    @property
    def sample_plan(self):
        return tuple((p.probe_id, p.case, digest(p.frame.hex())) for p in sample_plan(self.approval.binding, self.context_uuid))
    @property
    def digest(self): return digest(asdict(self))

    def operator_report(self):
        """Compact allowlisted export: one identity catalog, indexed counter rows."""
        self.__post_init__()
        body = {k:v for k,v in asdict(self).items() if k != 'samples'}
        body['sample_plan'] = self.sample_plan
        catalog = self.samples[0].before if self.samples else ()
        body['counter_identities'] = [{k:v for k,v in asdict(c).items() if k not in ('packets','bytes')}
                                      for c in catalog]
        body['samples'] = [{'probe_id':s.probe_id, 'case':s.case, 'outcome':s.outcome,
            'started_at':s.started_at, 'finished_at':s.finished_at,
            'before': [(c.packets,c.bytes) for c in s.before], 'after': [(c.packets,c.bytes) for c in s.after]}
            for s in self.samples]
        require(len(json.dumps(body, separators=(',', ':'), allow_nan=False).encode()) <= 65536,
                'counter_report_limit')
        return body


UNKNOWN_REASONS = (
    'counter_evidence_invalid', 'counter_readback_invalid', 'counter_generation_changed',
    'counter_reset_or_wrap', 'counter_delta_unexplained', 'counter_packet_incomplete',
    'counter_topology_unproven', 'counter_deadline', 'counter_killed', 'counter_clock_rollback',
)
