"""Offline v2 identity foundation. No parser, authentication or physical authority.

Typed fixture inputs describe a proposed installation, never establish ownership.
A future authenticated committed witness needs a separate reviewed boundary;
WitnessReference2 below is deliberately unverified and cannot confirm anything.
"""
from dataclasses import asdict, dataclass
import hashlib
import json
import re
from uuid import UUID


CONTRACT = 'tc-native-compatibility-v2'
METHOD = 'nft_counter_probe_v2'
DOMAIN = 'tc-nft-counter-probe-v2-offline'
ORIGIN = 'offline_native_compat_fixture'
MAX_INTEGER = 2**63 - 1
MAX_OBJECTS = 128
MAX_EXPRESSIONS = 64


class ContractViolation2(ValueError):
    """Finite error codes; no supplied input or diagnostic output."""


def _require(condition, reason):
    if not condition:
        raise ContractViolation2(reason)


def _integer(value, minimum=1, maximum=MAX_INTEGER):
    _require(type(value) is int and minimum <= value <= maximum, 'v2_integer_invalid')


def _uuid(value):
    try:
        valid = type(value) is str and str(UUID(value)) == value and UUID(value).int != 0
    except (ValueError, TypeError, AttributeError):
        valid = False
    _require(valid, 'v2_uuid_invalid')


def _hex(value):
    _require(type(value) is str and re.fullmatch('[0-9a-f]{64}', value) is not None, 'v2_digest_invalid')


def _name(value):
    _require(type(value) is str and re.fullmatch('[A-Za-z_][A-Za-z0-9_]{0,63}', value) is not None,
             'v2_name_invalid')


def _enum(value, values):
    _require(type(value) is str and value in values, 'v2_literal_invalid')


def _typed(value, cls):
    _require(type(value) is cls, 'v2_type_invalid')
    value.__post_init__()


def _rows(value, cls, minimum=1, maximum=MAX_OBJECTS):
    _require(type(value) is tuple and minimum <= len(value) <= maximum, 'v2_collection_invalid')
    for row in value:
        _typed(row, cls)


def _hash(kind, value):
    # This is a content digest, NOT HMAC verification or approval issuance.
    raw = json.dumps({'domain': DOMAIN, 'kind': kind, 'value': value},
                     sort_keys=True, separators=(',', ':'), allow_nan=False).encode()
    return hashlib.sha256(raw).hexdigest()


def _path(family, table, chain=None):
    _enum(family, ('bridge', 'inet'))
    _name(table)
    if chain is not None:
        _name(chain)
    return (family, table) if chain is None else (family, table, chain)


def canonical_rule_id2(family, table, chain, ordinal):
    """Deterministic compiler-path ID; no default/generated UUID or native handle."""
    path = _path(family, table, chain)
    _integer(ordinal, 0, MAX_OBJECTS - 1)
    return _hash('canonical_rule_path', (path, ordinal))


def canonical_counter_id2(rule_id, expression_position, purpose, probe_id):
    _hex(rule_id)
    _integer(expression_position, 0, MAX_EXPRESSIONS - 1)
    _purpose(purpose, probe_id)
    return _hash('canonical_counter_slot', (rule_id, expression_position, purpose, probe_id))


def _purpose(purpose, probe_id):
    _enum(purpose, ('ingress', 'terminal_drop', 'allow', 'guard_drop', 'fallback_drop'))
    if purpose in ('ingress', 'terminal_drop'):
        _hex(probe_id)
    else:
        _require(probe_id is None, 'v2_probe_invalid')


@dataclass(frozen=True, slots=True, kw_only=True)
class _Offline2:
    contract: str = CONTRACT
    version: int = 2
    method: str = METHOD
    domain: str = DOMAIN
    origin: str = ORIGIN
    authentication: str = 'not_authenticated'
    ownership_proven: bool = False
    physical_probe_permitted: bool = False
    continuous_attestation: bool = False
    trace_delivery_complete: str = 'unproven'

    def __post_init__(self):
        for value, expected in ((self.contract, CONTRACT), (self.method, METHOD), (self.domain, DOMAIN),
                                (self.origin, ORIGIN), (self.authentication, 'not_authenticated'),
                                (self.trace_delivery_complete, 'unproven')):
            _require(type(value) is str and value == expected, 'v2_domain_rejected')
        _require(type(self.version) is int and self.version == 2, 'v2_version_invalid')
        _require(self.ownership_proven is False and self.physical_probe_permitted is False and
                 self.continuous_attestation is False, 'v2_authority_forbidden')

    @property
    def digest(self):
        self.__post_init__()
        return _hash(type(self).__name__, asdict(self))


@dataclass(frozen=True, slots=True)
class NamespaceKey2(_Offline2):
    host_boot_uuid: str
    netns_inode: int
    reader_session_uuid: str
    namespace_binding_generation: int

    def __post_init__(self):
        _Offline2.__post_init__(self)
        _uuid(self.host_boot_uuid)
        _uuid(self.reader_session_uuid)
        _integer(self.netns_inode)
        _integer(self.namespace_binding_generation)


@dataclass(frozen=True, slots=True)
class InstallKey2(_Offline2):
    approval_digest: str
    context_uuid: str
    binding_digest: str
    writer_epoch_uuid: str
    install_epoch_uuid: str
    install_generation: int

    def __post_init__(self):
        _Offline2.__post_init__(self)
        for value in (self.approval_digest, self.binding_digest):
            _hex(value)
        for value in (self.context_uuid, self.writer_epoch_uuid, self.install_epoch_uuid):
            _uuid(value)
        _integer(self.install_generation)


@dataclass(frozen=True, slots=True)
class TableIdentity2(_Offline2):
    namespace: NamespaceKey2
    installation: InstallKey2
    family: str
    name: str
    handle: int

    def __post_init__(self):
        _Offline2.__post_init__(self)
        _typed(self.namespace, NamespaceKey2)
        _typed(self.installation, InstallKey2)
        _path(self.family, self.name)
        _integer(self.handle)


def _chain_attributes(name, chain_type, hook, priority, policy):
    _name(name)
    _enum(chain_type, ('filter',))
    _enum(hook, ('prerouting', 'input', 'forward', 'output'))
    _integer(priority, -(2**31), 2**31 - 1)
    _enum(policy, ('accept', 'drop'))


@dataclass(frozen=True, slots=True)
class ChainIdentity2(_Offline2):
    parent: TableIdentity2
    name: str
    handle: int
    chain_type: str
    hook: str
    priority: int
    policy: str

    def __post_init__(self):
        _Offline2.__post_init__(self)
        _typed(self.parent, TableIdentity2)
        _integer(self.handle)
        _chain_attributes(self.name, self.chain_type, self.hook, self.priority, self.policy)


@dataclass(frozen=True, slots=True)
class RuleIdentity2(_Offline2):
    parent: ChainIdentity2
    handle: int
    canonical_rule_id: str
    ordinal: int
    static_expression_digest: str

    def __post_init__(self):
        _Offline2.__post_init__(self)
        _typed(self.parent, ChainIdentity2)
        _integer(self.handle)
        _hex(self.canonical_rule_id)
        _hex(self.static_expression_digest)
        t = self.parent.parent
        _require(self.canonical_rule_id == canonical_rule_id2(t.family, t.name, self.parent.name, self.ordinal),
                 'v2_rule_path_mismatch')


@dataclass(frozen=True, slots=True)
class CounterSlot2(_Offline2):
    parent: RuleIdentity2
    canonical_counter_id: str
    expression_position: int
    purpose: str
    probe_id: str | None

    def __post_init__(self):
        _Offline2.__post_init__(self)
        _typed(self.parent, RuleIdentity2)
        _hex(self.canonical_counter_id)
        expected = canonical_counter_id2(self.parent.canonical_rule_id, self.expression_position,
                                         self.purpose, self.probe_id)
        _require(self.canonical_counter_id == expected, 'v2_counter_path_mismatch')


@dataclass(frozen=True, slots=True)
class CanonicalTableSpec2(_Offline2):
    family: str
    name: str

    def __post_init__(self):
        _Offline2.__post_init__(self)
        _path(self.family, self.name)


@dataclass(frozen=True, slots=True)
class CanonicalChainSpec2(_Offline2):
    parent: CanonicalTableSpec2
    name: str
    chain_type: str
    hook: str
    priority: int
    policy: str
    rule_count: int

    def __post_init__(self):
        _Offline2.__post_init__(self)
        _typed(self.parent, CanonicalTableSpec2)
        _chain_attributes(self.name, self.chain_type, self.hook, self.priority, self.policy)
        _integer(self.rule_count, 0, MAX_OBJECTS)


@dataclass(frozen=True, slots=True)
class CanonicalRuleSpec2(_Offline2):
    parent: CanonicalChainSpec2
    canonical_rule_id: str
    ordinal: int
    static_expression_digest: str
    expression_count: int
    counter_position: int
    purpose: str
    probe_id: str | None

    def __post_init__(self):
        _Offline2.__post_init__(self)
        _typed(self.parent, CanonicalChainSpec2)
        _hex(self.canonical_rule_id)
        _hex(self.static_expression_digest)
        t = self.parent.parent
        expected = canonical_rule_id2(t.family, t.name, self.parent.name, self.ordinal)
        _require(self.canonical_rule_id == expected and self.ordinal < self.parent.rule_count,
                 'v2_rule_path_mismatch')
        _integer(self.expression_count, 1, MAX_EXPRESSIONS)
        _integer(self.counter_position, 0, MAX_EXPRESSIONS - 1)
        _purpose(self.purpose, self.probe_id)
        tail = 1 if self.purpose == 'ingress' else 2
        _require(self.counter_position == self.expression_count - tail, 'v2_counter_position_invalid')
        if self.purpose == 'fallback_drop':
            _require(self.counter_position == 0, 'v2_counter_position_invalid')
        else:
            _require(self.counter_position > 0, 'v2_counter_position_invalid')

    @property
    def canonical_counter_id(self):
        return canonical_counter_id2(self.canonical_rule_id, self.counter_position, self.purpose, self.probe_id)


def _table_path(table):
    return (table.family, table.name)


def _chain_path(chain):
    return (*_table_path(chain.parent), chain.name)


def _unique(keys):
    _require(len(keys) == len(set(keys)), 'v2_scope_collision')


@dataclass(frozen=True, slots=True)
class CanonicalRuleCatalog2(_Offline2):
    """Trusted compiler/fixture specs, not a recipe validator or native reader."""
    canonical_recipe_digest: str
    tables: tuple[CanonicalTableSpec2, ...]
    chains: tuple[CanonicalChainSpec2, ...]
    rules: tuple[CanonicalRuleSpec2, ...]
    allowed_probe_ids: tuple[str, ...]
    source: str = 'trusted_offline_specification'

    def __post_init__(self):
        _Offline2.__post_init__(self)
        _hex(self.canonical_recipe_digest)
        _require(type(self.source) is str and self.source == 'trusted_offline_specification', 'v2_catalog_source_invalid')
        _rows(self.tables, CanonicalTableSpec2)
        _rows(self.chains, CanonicalChainSpec2)
        _rows(self.rules, CanonicalRuleSpec2)
        _require(len(self.tables) + len(self.chains) + len(self.rules) <= MAX_OBJECTS, 'v2_collection_invalid')
        _require(type(self.allowed_probe_ids) is tuple and len(self.allowed_probe_ids) <= 15,
                 'v2_probe_invalid')
        for probe in self.allowed_probe_ids:
            _hex(probe)
        _unique(list(self.allowed_probe_ids))
        _unique([_table_path(t) for t in self.tables])
        _unique([_chain_path(c) for c in self.chains])
        _unique([(c.parent.family, c.hook, c.priority) for c in self.chains])
        _unique([r.canonical_rule_id for r in self.rules])
        _unique([r.canonical_counter_id for r in self.rules])
        for t in self.tables:
            _require(any(c.parent == t for c in self.chains), 'v2_parent_missing')
        for c in self.chains:
            _require(c.parent in self.tables, 'v2_parent_missing')
            actual = tuple(r.ordinal for r in self.rules if r.parent == c)
            _require(actual == tuple(range(c.rule_count)), 'v2_catalog_incomplete')
        for r in self.rules:
            _require(r.parent in self.chains, 'v2_parent_missing')
            _require(r.probe_id is None or r.probe_id in self.allowed_probe_ids, 'v2_probe_invalid')
        _require(set(self.allowed_probe_ids) == {r.probe_id for r in self.rules if r.probe_id is not None},
                 'v2_catalog_incomplete')


@dataclass(frozen=True, slots=True)
class OfflineApproval2(_Offline2):
    """Explicit trusted fixture input; neither signature nor runtime approval."""
    approval_uuid: str
    context_uuid: str
    scope: str
    canonical_recipe_digest: str
    catalog_digest: str
    binding_digest: str
    native_profile_digest: str
    topology_profile_digest: str

    def __post_init__(self):
        _Offline2.__post_init__(self)
        _uuid(self.approval_uuid)
        _uuid(self.context_uuid)
        _require(type(self.scope) is str and re.fullmatch('offline-native-v2-[a-z0-9]{1,32}', self.scope) is not None,
                 'v2_scope_invalid')
        for value in (self.canonical_recipe_digest, self.catalog_digest, self.binding_digest,
                      self.native_profile_digest, self.topology_profile_digest):
            _hex(value)


@dataclass(frozen=True, slots=True)
class InstallIntent2(_Offline2):
    approval: OfflineApproval2
    namespace: NamespaceKey2
    installation: InstallKey2
    catalog: CanonicalRuleCatalog2
    transaction_uuid: str
    creation_record_digest: str
    operation: str = 'exclusive_create_only'

    def __post_init__(self):
        _Offline2.__post_init__(self)
        _typed(self.approval, OfflineApproval2)
        _typed(self.namespace, NamespaceKey2)
        _typed(self.installation, InstallKey2)
        _typed(self.catalog, CanonicalRuleCatalog2)
        _uuid(self.transaction_uuid)
        _hex(self.creation_record_digest)
        _require(type(self.operation) is str and self.operation == 'exclusive_create_only', 'v2_operation_invalid')
        a, i = self.approval, self.installation
        _require(i.approval_digest == a.digest and i.context_uuid == a.context_uuid and
                 i.binding_digest == a.binding_digest and a.catalog_digest == self.catalog.digest and
                 a.canonical_recipe_digest == self.catalog.canonical_recipe_digest, 'v2_approval_mismatch')


@dataclass(frozen=True, slots=True)
class WitnessReference2(_Offline2):
    """Pointer reserved for future witness review, NEVER a committed witness."""
    intent_digest: str
    installation_key_digest: str
    transaction_uuid: str
    reference_digest: str
    status: str = 'unverified_reference'

    def __post_init__(self):
        _Offline2.__post_init__(self)
        for value in (self.intent_digest, self.installation_key_digest, self.reference_digest):
            _hex(value)
        _uuid(self.transaction_uuid)
        _require(type(self.status) is str and self.status == 'unverified_reference', 'v2_witness_unproven')


@dataclass(frozen=True, slots=True)
class InstallationBinding2(_Offline2):
    """Structurally bound OFFLINE candidate; ownership remains unproven forever."""
    intent: InstallIntent2
    witness_reference: WitnessReference2
    independent_readback_reference_digest: str
    tables: tuple[TableIdentity2, ...]
    chains: tuple[ChainIdentity2, ...]
    rules: tuple[RuleIdentity2, ...]
    counters: tuple[CounterSlot2, ...]
    status: str = 'offline_structure_bound_ownership_unproven'

    def __post_init__(self):
        _Offline2.__post_init__(self)
        _typed(self.intent, InstallIntent2)
        _typed(self.witness_reference, WitnessReference2)
        _hex(self.independent_readback_reference_digest)
        _require(type(self.status) is str and self.status == 'offline_structure_bound_ownership_unproven',
                 'v2_witness_unproven')
        w, intent = self.witness_reference, self.intent
        _require(w.intent_digest == intent.digest and w.installation_key_digest == intent.installation.digest and
                 w.transaction_uuid == intent.transaction_uuid, 'v2_witness_reference_mismatch')
        _rows(self.tables, TableIdentity2)
        _rows(self.chains, ChainIdentity2)
        _rows(self.rules, RuleIdentity2)
        _rows(self.counters, CounterSlot2)
        catalog = intent.catalog
        _require((len(self.tables), len(self.chains), len(self.rules), len(self.counters)) ==
                 (len(catalog.tables), len(catalog.chains), len(catalog.rules), len(catalog.rules)),
                 'v2_catalog_incomplete')
        _unique([_table_path(t) for t in self.tables])
        _unique([(t.family, t.handle) for t in self.tables])
        _unique([_chain_path(c) for c in self.chains])
        chain_handles = [(*_table_path(c.parent), c.handle) for c in self.chains]
        rule_handles = [(*_table_path(r.parent.parent), r.handle) for r in self.rules]
        _unique(chain_handles)
        _unique(rule_handles)  # Table-wide, deliberately NOT per-chain.
        _require(not set(chain_handles).intersection(rule_handles), 'v2_scope_collision')
        _unique([r.canonical_rule_id for r in self.rules])
        _unique([c.canonical_counter_id for c in self.counters])
        for t, spec in zip(self.tables, catalog.tables):
            _require(t.namespace == intent.namespace and t.installation == intent.installation,
                     'v2_generation_changed')
            _require(_table_path(t) == _table_path(spec), 'v2_parent_mismatch')
        for c, spec in zip(self.chains, catalog.chains):
            _require(c.parent in self.tables and _chain_path(c) == _chain_path(spec), 'v2_parent_mismatch')
            _require((c.chain_type, c.hook, c.priority, c.policy) ==
                     (spec.chain_type, spec.hook, spec.priority, spec.policy), 'v2_chain_mismatch')
        for r, spec in zip(self.rules, catalog.rules):
            _require(r.parent in self.chains and _chain_path(r.parent) == _chain_path(spec.parent),
                     'v2_parent_mismatch')
            _require((r.canonical_rule_id, r.ordinal, r.static_expression_digest) ==
                     (spec.canonical_rule_id, spec.ordinal, spec.static_expression_digest), 'v2_rule_mismatch')
        for c, rule, spec in zip(self.counters, self.rules, catalog.rules):
            _require(c.parent == rule, 'v2_parent_mismatch')
            _require((c.canonical_counter_id, c.expression_position, c.purpose, c.probe_id) ==
                     (spec.canonical_counter_id, spec.counter_position, spec.purpose, spec.probe_id),
                     'v2_counter_mismatch')


def validate_binding2(binding, expected_intent):
    """Pure match against an explicitly supplied trusted current intent.

    Not a replay journal, freshness check, signature check or ownership permit.
    Same-intent identical values are idempotent; a new epoch/session/context is
    a different intent and cannot accept the previous binding.
    """
    _typed(binding, InstallationBinding2)
    _typed(expected_intent, InstallIntent2)
    _require(binding.intent == expected_intent, 'v2_stale_binding')
    return binding


def validate_same_installation2(binding, expected_binding, expected_intent):
    """Compare with an independently pinned offline installation description.

    Rebuilding a coherent graph with different handles/parents is not continuity.
    This does not prove the pinned fixture was ever installed in a kernel.
    """
    validate_binding2(binding, expected_intent)
    validate_binding2(expected_binding, expected_intent)
    _require(binding == expected_binding, 'v2_installation_changed')
    return binding
