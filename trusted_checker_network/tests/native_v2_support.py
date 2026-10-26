"""Synthetic v2 specs only. No v1 compiler, readback or installation evidence."""
from dataclasses import dataclass
import hashlib

from trusted_checker_network.native_v2_contracts import (
    NamespaceKey2, InstallKey2, TableIdentity2, ChainIdentity2, RuleIdentity2,
    CounterSlot2, CanonicalTableSpec2, CanonicalChainSpec2, CanonicalRuleSpec2,
    CanonicalRuleCatalog2, OfflineApproval2, InstallIntent2, WitnessReference2,
    InstallationBinding2, canonical_rule_id2, validate_binding2,
)


def uid(number):
    return '00000000-0000-0000-0000-%012d' % number


def hd(label):
    return hashlib.sha256(label.encode()).hexdigest()


def catalog2(*, second_family='inet'):
    tables = (CanonicalTableSpec2('bridge', 'v2_bridge_fixture'),
              CanonicalTableSpec2(second_family, 'v2_second_fixture'))
    chains = (CanonicalChainSpec2(tables[0], 'prerouting', 'filter', 'prerouting', 0, 'drop', 3),
              CanonicalChainSpec2(tables[0], 'forward', 'filter', 'forward', 0, 'drop', 1),
              CanonicalChainSpec2(tables[1], 'output', 'filter', 'output',
                                  -310 if second_family == 'inet' else 0,
                                  'accept' if second_family == 'inet' else 'drop', 1))
    probes = (hd('synthetic-probe-0'), hd('synthetic-probe-1'))
    rules = []
    for chain, ordinal, purpose, probe in ((chains[0], 0, 'ingress', probes[0]),
        (chains[0], 1, 'ingress', probes[1]), (chains[0], 2, 'terminal_drop', probes[1]),
        (chains[1], 0, 'allow', None), (chains[2], 0, 'guard_drop', None)):
        t = chain.parent
        rule_id = canonical_rule_id2(t.family, t.name, chain.name, ordinal)
        rules.append(CanonicalRuleSpec2(chain, rule_id, ordinal, hd('synthetic-expressions:' + rule_id),
                     3 if purpose == 'ingress' else 4, 2, purpose, probe))
    return CanonicalRuleCatalog2(hd('synthetic-spec-not-a-compiled-recipe'), tables, chains, tuple(rules), probes)


def intent2(*, generation=1, epoch=None, context=None, session=None, catalog=None):
    # Defaults exist only in this explicit synthetic setup, never production DTOs.
    catalog = catalog or catalog2()
    approval = OfflineApproval2(uid(5), context or uid(6), 'offline-native-v2-fixture',
        catalog.canonical_recipe_digest, catalog.digest, hd('synthetic-network-binding'),
        hd('synthetic-native-profile'), hd('synthetic-topology-profile'))
    namespace = NamespaceKey2(uid(1), 9999, session or uid(2), 1)
    installation = InstallKey2(approval.digest, approval.context_uuid, approval.binding_digest,
                               uid(3), epoch or uid(4), generation)
    return InstallIntent2(approval, namespace, installation, catalog, uid(7), hd('offline-creation-reference'))


def binding2(intent, *, table_handles=(8, 9), chain_handles=(1, 5, 1), rule_handles=(2, 3, 4, 8, 2)):
    catalog = intent.catalog
    tables = tuple(TableIdentity2(intent.namespace, intent.installation, t.family, t.name, h)
                   for t, h in zip(catalog.tables, table_handles))
    chains = tuple(ChainIdentity2(tables[catalog.tables.index(c.parent)], c.name, h,
                   c.chain_type, c.hook, c.priority, c.policy) for c, h in zip(catalog.chains, chain_handles))
    rules = tuple(RuleIdentity2(chains[catalog.chains.index(r.parent)], h, r.canonical_rule_id,
                  r.ordinal, r.static_expression_digest) for r, h in zip(catalog.rules, rule_handles))
    counters = tuple(CounterSlot2(r, spec.canonical_counter_id, spec.counter_position, spec.purpose, spec.probe_id)
                     for r, spec in zip(rules, catalog.rules))
    witness = WitnessReference2(intent.digest, intent.installation.digest, intent.transaction_uuid,
                                hd('unverified-future-witness-reference'))
    return InstallationBinding2(intent, witness, hd('unverified-independent-readback-reference'),
                                 tables, chains, rules, counters)


@dataclass
class Fixture2:
    intent: InstallIntent2
    binding: InstallationBinding2

    @classmethod
    def create(cls):
        intent = intent2()
        binding = binding2(intent)
        validate_binding2(binding, intent)
        return cls(intent, binding)
