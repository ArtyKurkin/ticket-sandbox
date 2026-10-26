"""Pure offline nft 1.0.9 JSON1 decoding, graph normalization and exact comparison.

    No compiler/collector/installer, source authentication, ownership issuance,
    CT/raw semantic proof acceptance, topology or packet/byte verification.
"""
from dataclasses import dataclass, fields
import hashlib
import ipaddress
import re

from . import native_v2_contracts as c
from .native_v2_json import bounded_json2, MAX_BYTES


def _keys(value, names, reason='v2_native_schema_invalid'):
    c._require(type(value) is dict and set(value) == set(names), reason)


@dataclass(frozen=True, slots=True)
class NativeFormatProfile2(c._Offline2):
    nft_binary_digest: str
    profile_id: str = 'nft-1.0.9-json1-v2'
    nft_version: str = '1.0.9'
    release_name: str = 'Old Doc Yak #3'
    json_schema_version: int = 1

    def __post_init__(self):
        c._Offline2.__post_init__(self)
        c._hex(self.nft_binary_digest)
        c._require(type(self.json_schema_version) is int and self.json_schema_version == 1 and
                   self.profile_id == 'nft-1.0.9-json1-v2' and type(self.profile_id) is str and
                   type(self.nft_version) is str and self.nft_version == '1.0.9' and
                   type(self.release_name) is str and self.release_name == 'Old Doc Yak #3', 'v2_native_profile_mismatch')


@dataclass(frozen=True, slots=True)
class ReadbackContext2(c._Offline2):
    namespace: c.NamespaceKey2
    installation: c.InstallKey2
    native_profile_digest: str
    nft_binary_digest: str

    def __post_init__(self):
        c._Offline2.__post_init__(self)
        c._typed(self.namespace, c.NamespaceKey2)
        c._typed(self.installation, c.InstallKey2)
        c._hex(self.native_profile_digest)
        c._hex(self.nft_binary_digest)


@dataclass(frozen=True, slots=True)
class Meta2(c._Offline2):
    key: str

    def __post_init__(self):
        c._Offline2.__post_init__(self)
        c._enum(self.key, ('iif', 'oif', 'iifname', 'oifname', 'l4proto'))


@dataclass(frozen=True, slots=True)
class Payload2(c._Offline2):
    protocol: str
    field: str

    def __post_init__(self):
        c._Offline2.__post_init__(self)
        allowed = {'ether': ('type', 'saddr', 'daddr'), 'ip': ('saddr', 'daddr', 'protocol', 'frag-off'),
                   'tcp': ('sport', 'dport'), 'udp': ('sport', 'dport'),
                   'arp': ('operation', 'saddr ether', 'saddr ip', 'daddr ip')}
        c._enum(self.protocol, tuple(allowed))
        c._enum(self.field, allowed[self.protocol])


@dataclass(frozen=True, slots=True)
class Ct2(c._Offline2):
    key: str = 'state'

    def __post_init__(self):
        c._Offline2.__post_init__(self)
        c._enum(self.key, ('state',))


@dataclass(frozen=True, slots=True)
class FragmentMask2(c._Offline2):
    payload: Payload2
    mask: int

    def __post_init__(self):
        c._Offline2.__post_init__(self)
        c._typed(self.payload, Payload2)
        c._require((self.payload.protocol, self.payload.field) == ('ip', 'frag-off'), 'v2_expression_unsupported')
        c._integer(self.mask, 0, 65535)


@dataclass(frozen=True, slots=True)
class RawPayload2(c._Offline2):
    """Syntactic literal only: units/width/endian semantics remain unproven."""
    base: str
    offset: int
    length: int

    def __post_init__(self):
        c._Offline2.__post_init__(self)
        c._require(type(self.base) is str and self.base == 'll', 'v2_raw_payload_representation_unproven')
        c._integer(self.offset, 0)
        c._integer(self.length, 1, 128)


def _ipv4(value):
    c._require(type(value) is str, 'v2_literal_invalid')
    try:
        valid = str(ipaddress.IPv4Address(value)) == value
    except ipaddress.AddressValueError:
        valid = False
    c._require(valid, 'v2_literal_invalid')


def _literal(left, value, op):
    c._enum(op, ('==', 'in') if type(left) is Ct2 else ('==',))
    if type(left) is Ct2:
        c._enum(value, ('new', 'established'))
    elif type(left) is RawPayload2:
        c._require(type(value) is str and re.fullmatch('0x[0-9a-f]{2,254}', value) is not None,
                   'v2_raw_payload_representation_unproven')
    elif type(left) is FragmentMask2:
        c._integer(value, 0, 65535)
    elif type(left) is Meta2:
        if left.key in ('iif', 'oif'):
            c._integer(value)
        elif left.key in ('iifname', 'oifname'):
            c._require(type(value) is str and re.fullmatch('[A-Za-z0-9_.:-]{1,15}', value) is not None,
                       'v2_literal_invalid')
        else:
            c._enum(value, ('tcp', 'udp', 'icmp', 'ipv6-icmp'))
    elif type(left) is Payload2:
        p, f = left.protocol, left.field
        if (p == 'ip' and f in ('saddr', 'daddr')) or (p == 'arp' and f in ('saddr ip', 'daddr ip')):
            _ipv4(value)
        elif (p == 'ether' and f in ('saddr', 'daddr')) or (p == 'arp' and f == 'saddr ether'):
            c._require(type(value) is str and re.fullmatch('(?:[0-9a-f]{2}:){5}[0-9a-f]{2}', value) is not None,
                       'v2_literal_invalid')
        elif p == 'ether':
            c._enum(value, ('ip', 'arp', 'ip6'))
        elif p == 'ip' and f == 'protocol':
            c._enum(value, ('tcp', 'udp', 'icmp'))
        elif p == 'arp':
            c._enum(value, ('request', 'reply'))
        else:
            c._integer(value, 0, 65535)


@dataclass(frozen=True, slots=True)
class Match2(c._Offline2):
    left: Meta2 | Payload2 | Ct2 | FragmentMask2 | RawPayload2
    op: str
    right: str | int

    def __post_init__(self):
        c._Offline2.__post_init__(self)
        c._require(type(self.left) in (Meta2, Payload2, Ct2, FragmentMask2, RawPayload2), 'v2_expression_unsupported')
        self.left.__post_init__()
        _literal(self.left, self.right, self.op)


@dataclass(frozen=True, slots=True)
class AnonymousCounter2(c._Offline2):
    pass


@dataclass(frozen=True, slots=True)
class Verdict2(c._Offline2):
    verdict: str

    def __post_init__(self):
        c._Offline2.__post_init__(self)
        c._enum(self.verdict, ('accept', 'drop'))


def _expressions(value):
    c._require(type(value) is tuple and 1 <= len(value) <= c.MAX_EXPRESSIONS, 'v2_expression_invalid')
    for node in value:
        c._require(type(node) in (Match2, AnonymousCounter2, Verdict2), 'v2_expression_unsupported')
        node.__post_init__()
    counters = [i for i, node in enumerate(value) if type(node) is AnonymousCounter2]
    verdicts = [i for i, node in enumerate(value) if type(node) is Verdict2]
    c._require(len(counters) <= 1 and (not verdicts or verdicts == [len(value) - 1]), 'v2_counter_layout_invalid')


def _tree(node):
    if type(node) in (Meta2, Payload2, Ct2, FragmentMask2, RawPayload2, Match2, AnonymousCounter2, Verdict2):
        return (type(node).__name__, tuple((f.name, _tree(getattr(node, f.name))) for f in fields(node)))
    c._require(node is None or type(node) in (str, int, bool), 'v2_expression_invalid')
    return node


def static_expression_digest2(expressions):
    _expressions(expressions)
    return c._hash('native_v2_static_expressions', tuple(_tree(node) for node in expressions))


@dataclass(frozen=True, slots=True)
class CounterNumbers2(c._Offline2):
    packets: int
    bytes: int

    def __post_init__(self):
        c._Offline2.__post_init__(self)
        c._integer(self.packets, 0)
        c._integer(self.bytes, 0)


@dataclass(frozen=True, slots=True)
class NativeTable2(c._Offline2):
    family: str
    name: str
    handle: int

    def __post_init__(self):
        c._Offline2.__post_init__(self)
        c._path(self.family, self.name)
        c._integer(self.handle)


@dataclass(frozen=True, slots=True)
class NativeChain2(c._Offline2):
    family: str
    table: str
    name: str
    handle: int
    chain_type: str
    hook: str
    priority: int
    policy: str

    def __post_init__(self):
        c._Offline2.__post_init__(self)
        c._path(self.family, self.table)
        c._integer(self.handle)
        c._chain_attributes(self.name, self.chain_type, self.hook, self.priority, self.policy)


@dataclass(frozen=True, slots=True)
class NativeRule2(c._Offline2):
    family: str
    table: str
    chain: str
    handle: int
    expressions: tuple
    counter: CounterNumbers2 | None

    def __post_init__(self):
        c._Offline2.__post_init__(self)
        c._path(self.family, self.table, self.chain)
        c._integer(self.handle)
        _expressions(self.expressions)
        present = any(type(n) is AnonymousCounter2 for n in self.expressions)
        if present:
            c._typed(self.counter, CounterNumbers2)
        else:
            c._require(self.counter is None, 'v2_counter_layout_invalid')

    @property
    def counter_position(self):
        return next((i for i, n in enumerate(self.expressions) if type(n) is AnonymousCounter2), None)


@dataclass(frozen=True, slots=True)
class DecodedNative2(c._Offline2):
    profile: NativeFormatProfile2
    context: ReadbackContext2
    objects: tuple
    raw_digest: str
    raw_byte_count: int
    stage: str = 'format_decoded'

    def __post_init__(self):
        c._Offline2.__post_init__(self)
        c._typed(self.profile, NativeFormatProfile2)
        c._typed(self.context, ReadbackContext2)
        c._require(self.context.native_profile_digest == self.profile.digest and
                   self.context.nft_binary_digest == self.profile.nft_binary_digest, 'v2_native_profile_mismatch')
        c._hex(self.raw_digest)
        c._integer(self.raw_byte_count, 1, MAX_BYTES)
        c._require(type(self.stage) is str and self.stage == 'format_decoded' and type(self.objects) is tuple and
                   len(self.objects) <= c.MAX_OBJECTS - 1, 'v2_native_schema_invalid')
        for obj in self.objects:
            c._require(type(obj) in (NativeTable2, NativeChain2, NativeRule2), 'v2_native_schema_invalid')
            obj.__post_init__()

    @property
    def metainfo(self):
        return (self.profile.nft_version, self.profile.release_name, self.profile.json_schema_version)


def _left(value):
    c._require(type(value) is dict and len(value) == 1, 'v2_expression_unsupported')
    kind, data = next(iter(value.items()))
    if kind in ('meta', 'ct'):
        _keys(data, ('key',))
        return Meta2(data['key']) if kind == 'meta' else Ct2(data['key'])
    if kind == 'payload':
        if type(data) is dict and ('base' in data or 'offset' in data or 'len' in data):
            _keys(data, ('base', 'offset', 'len'), 'v2_raw_payload_representation_unproven')
            return RawPayload2(data['base'], data['offset'], data['len'])
        _keys(data, ('protocol', 'field'))
        return Payload2(data['protocol'], data['field'])
    if kind == '&':
        c._require(type(data) is list and len(data) == 2, 'v2_expression_unsupported')
        return FragmentMask2(_left(data[0]), data[1])
    raise c.ContractViolation2('v2_expression_unsupported')


def _decode_expressions(items):
    c._require(type(items) is list and 1 <= len(items) <= c.MAX_EXPRESSIONS, 'v2_expression_invalid')
    result, numbers = [], None
    for item in items:
        c._require(type(item) is dict and len(item) == 1, 'v2_expression_unsupported')
        kind, data = next(iter(item.items()))
        if kind == 'match':
            _keys(data, ('left', 'op', 'right'))
            result.append(Match2(_left(data['left']), data['op'], data['right']))
        elif kind == 'counter':
            c._require(numbers is None, 'v2_counter_layout_invalid')
            _keys(data, ('packets', 'bytes'), 'v2_counter_layout_invalid')
            numbers = CounterNumbers2(data['packets'], data['bytes'])
            result.append(AnonymousCounter2())
        elif kind in ('accept', 'drop'):
            c._require(data is None, 'v2_expression_invalid')
            result.append(Verdict2(kind))
        else:
            raise c.ContractViolation2('v2_expression_unsupported')
    return tuple(result), numbers


def decode_native2(raw, profile, context):
    c._typed(profile, NativeFormatProfile2)
    c._typed(context, ReadbackContext2)
    c._require(context.native_profile_digest == profile.digest and context.nft_binary_digest == profile.nft_binary_digest,
               'v2_native_profile_mismatch')
    data = bounded_json2(raw)
    _keys(data, ('nftables',))
    items = data['nftables']
    c._require(type(items) is list and 1 <= len(items) <= c.MAX_OBJECTS, 'v2_native_schema_invalid')
    _keys(items[0], ('metainfo',))
    meta = items[0]['metainfo']
    _keys(meta, ('version', 'release_name', 'json_schema_version'))
    c._require(type(meta['json_schema_version']) is int and
               (meta['version'], meta['release_name'], meta['json_schema_version']) ==
               (profile.nft_version, profile.release_name, profile.json_schema_version), 'v2_native_profile_mismatch')
    objects = []
    for item in items[1:]:
        c._require(type(item) is dict and len(item) == 1, 'v2_native_schema_invalid')
        kind, obj = next(iter(item.items()))
        if kind == 'table':
            _keys(obj, ('family', 'name', 'handle'))
            objects.append(NativeTable2(obj['family'], obj['name'], obj['handle']))
        elif kind == 'chain':
            _keys(obj, ('family', 'table', 'name', 'handle', 'type', 'hook', 'prio', 'policy'))
            objects.append(NativeChain2(obj['family'], obj['table'], obj['name'], obj['handle'],
                                       obj['type'], obj['hook'], obj['prio'], obj['policy']))
        elif kind == 'rule':
            _keys(obj, ('family', 'table', 'chain', 'handle', 'expr'))
            expressions, counter = _decode_expressions(obj['expr'])
            objects.append(NativeRule2(obj['family'], obj['table'], obj['chain'], obj['handle'], expressions, counter))
        else:
            raise c.ContractViolation2('v2_native_schema_invalid')
    return DecodedNative2(profile, context, tuple(objects), hashlib.sha256(raw).hexdigest(), len(raw))


@dataclass(frozen=True, slots=True)
class NormalizedRule2(c._Offline2):
    identity: c.RuleIdentity2
    expressions: tuple
    counter: CounterNumbers2 | None

    def __post_init__(self):
        c._Offline2.__post_init__(self)
        c._typed(self.identity, c.RuleIdentity2)
        _expressions(self.expressions)
        c._require(self.identity.static_expression_digest == static_expression_digest2(self.expressions),
                   'v2_rule_mismatch')
        if any(type(n) is AnonymousCounter2 for n in self.expressions):
            c._typed(self.counter, CounterNumbers2)
        else:
            c._require(self.counter is None, 'v2_counter_layout_invalid')


@dataclass(frozen=True, slots=True)
class NormalizedChain2(c._Offline2):
    identity: c.ChainIdentity2
    rules: tuple[NormalizedRule2, ...]

    def __post_init__(self):
        c._Offline2.__post_init__(self)
        c._typed(self.identity, c.ChainIdentity2)
        c._rows(self.rules, NormalizedRule2, 0)
        c._require(all(r.identity.parent == self.identity and r.identity.ordinal == i for i, r in enumerate(self.rules)),
                   'v2_parent_mismatch')


@dataclass(frozen=True, slots=True)
class NormalizedTable2(c._Offline2):
    identity: c.TableIdentity2
    chains: tuple[NormalizedChain2, ...]

    def __post_init__(self):
        c._Offline2.__post_init__(self)
        c._typed(self.identity, c.TableIdentity2)
        c._rows(self.chains, NormalizedChain2, 0)
        c._require(all(ch.identity.parent == self.identity for ch in self.chains), 'v2_parent_mismatch')


def _build_graph(decoded):
    tables, chains, rules = {}, {}, {}
    table_handles, chain_handles, rule_handles, hooks = set(), set(), set(), set()
    ns, install = decoded.context.namespace, decoded.context.installation
    def add(seen, key):
        c._require(key not in seen, 'v2_scope_collision')
        seen.add(key)
    for obj in decoded.objects:
        if type(obj) is NativeTable2:
            key = (obj.family, obj.name)
            c._require(key not in tables, 'v2_scope_collision')
            add(table_handles, (obj.family, obj.handle))
            tables[key] = c.TableIdentity2(ns, install, obj.family, obj.name, obj.handle)
        elif type(obj) is NativeChain2:
            parent = (obj.family, obj.table)
            c._require(parent in tables, 'v2_parent_missing')
            key = (*parent, obj.name)
            c._require(key not in chains, 'v2_scope_collision')
            add(chain_handles, (*parent, obj.handle))
            add(hooks, (obj.family, obj.hook, obj.priority))
            chains[key] = c.ChainIdentity2(tables[parent], obj.name, obj.handle, obj.chain_type, obj.hook, obj.priority, obj.policy)
            rules[key] = []
        else:
            key = (obj.family, obj.table, obj.chain)
            c._require(key in chains, 'v2_parent_missing')
            add(rule_handles, (obj.family, obj.table, obj.handle))
            ordinal = len(rules[key])
            rid = c.canonical_rule_id2(*key, ordinal)
            identity = c.RuleIdentity2(chains[key], obj.handle, rid, ordinal, static_expression_digest2(obj.expressions))
            rules[key].append(NormalizedRule2(identity, obj.expressions, obj.counter))
    c._require(not chain_handles.intersection(rule_handles), 'v2_scope_collision')
    # Only table/chain keyed map order is canonicalized. Rule lists are untouched.
    return tuple(NormalizedTable2(tables[path], tuple(
        NormalizedChain2(chains[key], tuple(rules[key])) for key in sorted(chains) if key[:2] == path))
        for path in sorted(tables))


@dataclass(frozen=True, slots=True)
class NormalizedRules2(c._Offline2):
    decoded: DecodedNative2
    tables: tuple[NormalizedTable2, ...]
    stage: str = 'graph_normalized'

    def __post_init__(self):
        c._Offline2.__post_init__(self)
        c._typed(self.decoded, DecodedNative2)
        c._rows(self.tables, NormalizedTable2, 0)
        c._require(type(self.stage) is str and self.stage == 'graph_normalized', 'v2_native_schema_invalid')
        c._require(self.tables == _build_graph(self.decoded), 'v2_graph_mismatch')


def normalize_rules2(decoded):
    c._typed(decoded, DecodedNative2)
    return NormalizedRules2(decoded, _build_graph(decoded))


@dataclass(frozen=True, slots=True)
class ExpectedRuleExpressions2(c._Offline2):
    canonical_rule_id: str
    expressions: tuple

    def __post_init__(self):
        c._Offline2.__post_init__(self)
        c._hex(self.canonical_rule_id)
        _expressions(self.expressions)


def expected_recipe_digest2(catalog, expressions):
    c._typed(catalog, c.CanonicalRuleCatalog2)
    c._rows(expressions, ExpectedRuleExpressions2)
    return c._hash('native_v2_expected_recipe', (
        tuple((t.family, t.name) for t in catalog.tables),
        tuple((c._chain_path(ch), ch.chain_type, ch.hook, ch.priority, ch.policy, ch.rule_count) for ch in catalog.chains),
        tuple((r.canonical_rule_id, r.ordinal, r.static_expression_digest, r.expression_count,
               r.counter_position, r.purpose, r.probe_id) for r in catalog.rules),
        catalog.allowed_probe_ids,
        tuple((r.canonical_rule_id, tuple(_tree(n) for n in r.expressions)) for r in expressions)))


@dataclass(frozen=True, slots=True)
class ExpectedRecipe2(c._Offline2):
    intent: c.InstallIntent2
    profile: NativeFormatProfile2
    rules: tuple[ExpectedRuleExpressions2, ...]

    def __post_init__(self):
        c._Offline2.__post_init__(self)
        c._typed(self.intent, c.InstallIntent2)
        c._typed(self.profile, NativeFormatProfile2)
        c._rows(self.rules, ExpectedRuleExpressions2)
        catalog = self.intent.catalog
        c._require(self.intent.approval.native_profile_digest == self.profile.digest, 'v2_native_profile_mismatch')
        c._require(len(self.rules) == len(catalog.rules), 'v2_catalog_incomplete')
        for expr, spec in zip(self.rules, catalog.rules):
            c._require(expr.canonical_rule_id == spec.canonical_rule_id and
                       len(expr.expressions) == spec.expression_count and
                       static_expression_digest2(expr.expressions) == spec.static_expression_digest, 'v2_rule_mismatch')
            positions = [i for i, n in enumerate(expr.expressions) if type(n) is AnonymousCounter2]
            c._require(positions == [spec.counter_position], 'v2_counter_layout_invalid')
            verdicts = [n.verdict for n in expr.expressions if type(n) is Verdict2]
            wanted = [] if spec.purpose == 'ingress' else ['accept' if spec.purpose == 'allow' else 'drop']
            c._require(verdicts == wanted, 'v2_counter_layout_invalid')
        c._require(catalog.canonical_recipe_digest == expected_recipe_digest2(catalog, self.rules), 'v2_recipe_digest_mismatch')


def _compare(normalized, expected, binding, expected_intent):
    c._typed(normalized, NormalizedRules2)
    c._typed(expected, ExpectedRecipe2)
    c.validate_binding2(binding, expected_intent)
    c._require(expected.intent == expected_intent, 'v2_stale_binding')
    ctx = normalized.decoded.context
    c._require(ctx.namespace == expected_intent.namespace and ctx.installation == expected_intent.installation,
               'v2_generation_changed')
    c._require(normalized.decoded.profile == expected.profile, 'v2_native_profile_mismatch')
    actual_tables = {c._table_path(t.identity): t for t in normalized.tables}
    c._require(set(actual_tables) == {c._table_path(t) for t in binding.tables}, 'v2_recipe_mismatch')
    actual_chains, actual_rules = {}, {}
    for pinned in binding.tables:
        table = actual_tables[c._table_path(pinned)]
        c._require(table.identity == pinned, 'v2_identity_mismatch')
        for chain in table.chains:
            actual_chains[c._chain_path(chain.identity)] = chain
            for rule in chain.rules:
                actual_rules[rule.identity.canonical_rule_id] = rule
    c._require(set(actual_chains) == {c._chain_path(ch) for ch in binding.chains} and
               set(actual_rules) == {r.canonical_rule_id for r in binding.rules}, 'v2_recipe_mismatch')
    for pinned in binding.chains:
        c._require(actual_chains[c._chain_path(pinned)].identity == pinned, 'v2_identity_mismatch')
    for pinned, slot, expr in zip(binding.rules, binding.counters, expected.rules):
        actual = actual_rules[pinned.canonical_rule_id]
        c._require(actual.expressions == expr.expressions, 'v2_expression_mismatch')
        c._require(actual.identity == pinned, 'v2_identity_mismatch')
        positions = [i for i, node in enumerate(actual.expressions) if type(node) is AnonymousCounter2]
        c._require(positions == [slot.expression_position] and actual.counter is not None, 'v2_counter_layout_invalid')
    has_ct = any(type(node) is Match2 and type(node.left) is Ct2 for expr in expected.rules for node in expr.expressions)
    has_raw = any(type(node) is Match2 and type(node.left) is RawPayload2 for expr in expected.rules for node in expr.expressions)
    return 'raw_payload_representation_unproven' if has_raw else 'ct_semantics_unproven' if has_ct else 'offline_structural_recipe_matched'


@dataclass(frozen=True, slots=True)
class ValidatedRecipe2(c._Offline2):
    normalized: NormalizedRules2
    expected: ExpectedRecipe2
    pinned_binding: c.InstallationBinding2
    expected_intent: c.InstallIntent2
    measurement_verified: bool = False
    topology_verified: bool = False
    byte_accounting: str = 'unproven'
    installation_witness: str = 'unverified_reference'

    def __post_init__(self):
        c._Offline2.__post_init__(self)
        c._require(self.measurement_verified is False and self.topology_verified is False and
                   type(self.byte_accounting) is str and self.byte_accounting == 'unproven' and
                   type(self.installation_witness) is str and self.installation_witness == 'unverified_reference',
                   'v2_authority_forbidden')
        _compare(self.normalized, self.expected, self.pinned_binding, self.expected_intent)

    @property
    def reason(self):
        return _compare(self.normalized, self.expected, self.pinned_binding, self.expected_intent)

    @property
    def result(self):
        return 'recipe_matched' if self.reason == 'offline_structural_recipe_matched' else 'recipe_unproven'


def validate_recipe2(normalized, expected, pinned_binding, expected_intent):
    return ValidatedRecipe2(normalized, expected, pinned_binding, expected_intent)
