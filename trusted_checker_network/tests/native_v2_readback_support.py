"""Independent typed synthetic expected AST, then a test-only native renderer.

Five-rule fixture is complete for its supplied catalog, not a kernel run or the
future full 49-rule compiler. Never builds expected data from the tested JSON.
"""
from dataclasses import dataclass, replace
import json

from trusted_checker_network import native_v2_contracts as c
from trusted_checker_network import native_v2_readback as r
from .native_v2_support import catalog2, intent2, binding2, hd


def native_left(node):
    if type(node) is r.Meta2:
        return {'meta': {'key': node.key}}
    if type(node) is r.Ct2:
        return {'ct': {'key': node.key}}
    if type(node) is r.Payload2:
        return {'payload': {'protocol': node.protocol, 'field': node.field}}
    if type(node) is r.FragmentMask2:
        return {'&': [native_left(node.payload), node.mask]}
    if type(node) is r.RawPayload2:
        return {'payload': {'base': node.base, 'offset': node.offset, 'len': node.length}}
    raise AssertionError(type(node))


def native_expr(node, number):
    if type(node) is r.Match2:
        return {'match': {'left': native_left(node.left), 'op': node.op, 'right': node.right}}
    if type(node) is r.AnonymousCounter2:
        return {'counter': {'packets': number, 'bytes': number * 60}}
    if type(node) is r.Verdict2:
        return {node.verdict: None}
    raise AssertionError(type(node))


@dataclass
class ReadbackFixture2:
    expected: r.ExpectedRecipe2
    binding: c.InstallationBinding2
    context: r.ReadbackContext2

    @classmethod
    def create(cls, *, ct=None, raw=False):
        old = catalog2()
        specs, exprs = [], []
        for spec in old.rules:
            if spec.purpose == 'guard_drop':
                nodes = [r.Match2(r.Meta2('oifname'), '==', 'tcsh0')]
            else:
                port = 8081 if spec.probe_id == old.allowed_probe_ids[1] else 8080
                nodes = [r.Match2(r.Meta2('iif'), '==', 7),
                         r.Match2(r.Meta2('iifname'), '==', 'vethRunner'),
                         r.Match2(r.Payload2('ether', 'type'), '==', 'ip'),
                         r.Match2(r.Payload2('ether', 'saddr'), '==', '02:00:00:00:00:01'),
                         r.Match2(r.Payload2('ip', 'saddr'), '==', '172.30.0.3'),
                         r.Match2(r.Payload2('ip', 'daddr'), '==', '172.30.0.2'),
                         r.Match2(r.FragmentMask2(r.Payload2('ip', 'frag-off'), 16383), '==', 0),
                         r.Match2(r.Meta2('l4proto'), '==', 'tcp'),
                         r.Match2(r.Payload2('tcp', 'dport'), '==', port)]
                if spec.purpose == 'allow' and ct:
                    nodes.append(r.Match2(r.Ct2(), ct, 'established'))
                if spec.purpose == 'allow' and raw:
                    nodes.append(r.Match2(r.RawPayload2('ll', 0, 16), '==', '0x0001'))
            position = len(nodes)
            nodes.append(r.AnonymousCounter2())
            if spec.purpose != 'ingress':
                nodes.append(r.Verdict2('accept' if spec.purpose == 'allow' else 'drop'))
            nodes = tuple(nodes)
            specs.append(replace(spec, static_expression_digest=r.static_expression_digest2(nodes),
                                 expression_count=len(nodes), counter_position=position))
            exprs.append(r.ExpectedRuleExpressions2(spec.canonical_rule_id, nodes))
        catalog = replace(old, rules=tuple(specs))
        catalog = replace(catalog, canonical_recipe_digest=r.expected_recipe_digest2(catalog, tuple(exprs)))
        profile = r.NativeFormatProfile2(hd('synthetic-nft-binary-not-inspected'))
        intent = intent2(catalog=catalog)
        approval = replace(intent.approval, native_profile_digest=profile.digest)
        installation = replace(intent.installation, approval_digest=approval.digest)
        intent = replace(intent, approval=approval, installation=installation)
        expected = r.ExpectedRecipe2(intent, profile, tuple(exprs))
        binding = binding2(intent)
        context = r.ReadbackContext2(intent.namespace, installation, profile.digest, profile.nft_binary_digest)
        fixture = cls(expected, binding, context)
        fixture.validate()  # Every mutation starts with a valid stage baseline.
        return fixture

    def document(self, *, grouping='serialized'):
        profile = self.expected.profile
        header = {'metainfo': {'version': profile.nft_version, 'release_name': profile.release_name,
                               'json_schema_version': profile.json_schema_version}}
        tables, chains, rules = [], [], []
        for table in self.binding.tables:
            tables.append({'table': {'family': table.family, 'name': table.name, 'handle': table.handle}})
        for chain in self.binding.chains:
            chains.append({'chain': {'family': chain.parent.family, 'table': chain.parent.name, 'name': chain.name,
                'handle': chain.handle, 'type': chain.chain_type, 'hook': chain.hook,
                'prio': chain.priority, 'policy': chain.policy}})
        for number, (rule, expected) in enumerate(zip(self.binding.rules, self.expected.rules), 1):
            rules.append({'rule': {'family': rule.parent.parent.family, 'table': rule.parent.parent.name,
                'chain': rule.parent.name, 'handle': rule.handle,
                'expr': [native_expr(node, number) for node in expected.expressions]}})
        if grouping == 'serialized':
            return {'nftables': [header, *tables, *chains, *rules]}
        objects = [header]
        for table in tables:
            objects.append(table)
            t = table['table']
            for chain in chains:
                ch = chain['chain']
                if (ch['family'], ch['table']) != (t['family'], t['name']):
                    continue
                objects.append(chain)
                objects.extend(rule for rule in rules if
                    (rule['rule']['family'], rule['rule']['table'], rule['rule']['chain']) ==
                    (t['family'], t['name'], ch['name']))
        return {'nftables': objects}

    def decode(self, document=None):
        raw = json.dumps(self.document() if document is None else document, separators=(',', ':')).encode()
        return r.decode_native2(raw, self.expected.profile, self.context)

    def normalize(self, document=None):
        return r.normalize_rules2(self.decode(document))

    def validate(self, document=None):
        return r.validate_recipe2(self.normalize(document), self.expected, self.binding, self.expected.intent)
