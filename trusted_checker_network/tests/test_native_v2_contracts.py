"""V2-01 offline mutations always begin with a valid synthetic typed baseline."""
import ast
from dataclasses import FrozenInstanceError, asdict, replace
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import unittest

from trusted_checker_network import native_v2_contracts as v2
from trusted_checker_network.tests.native_v2_support import Fixture2, binding2, catalog2, hd, intent2, uid


class _FixtureCase(unittest.TestCase):
    def setUp(self):
        self.f = Fixture2.create()
        self.i, self.b, self.c = self.f.intent, self.f.binding, self.f.intent.catalog

    def deny(self, change, reason=None):
        # Every caller has a separately validated positive baseline from setUp.
        with self.assertRaises(v2.ContractViolation2) as caught:
            change()
        if reason:
            self.assertEqual(str(caught.exception), reason)


class BaselineTests(_FixtureCase):
    def test_positive_complete_offline_binding(self):
        self.assertIs(v2.validate_binding2(self.b, self.i), self.b)
        self.assertIs(v2.validate_same_installation2(self.b, self.b, self.i), self.b)
        self.assertEqual(len(self.b.rules), 5)
        self.assertFalse(self.b.ownership_proven)
        self.assertFalse(self.b.physical_probe_permitted)

    def test_table8_rule8_same_table_is_valid(self):
        table = self.b.tables[0]
        rule = self.b.rules[3]
        self.assertEqual((table.handle, rule.handle), (8, 8))
        self.assertEqual(rule.parent.parent, table)

    def test_chain1_in_different_tables_is_valid(self):
        self.assertEqual((self.b.chains[0].handle, self.b.chains[2].handle), (1, 1))
        self.assertNotEqual(self.b.chains[0].parent, self.b.chains[2].parent)

    def test_rule_handle_reuse_in_different_tables_same_family(self):
        intent = intent2(catalog=catalog2(second_family='bridge'))
        candidate = binding2(intent)
        self.assertEqual(candidate.rules[0].handle, candidate.rules[-1].handle)
        self.assertEqual(candidate.rules[0].parent.parent.family, candidate.rules[-1].parent.parent.family)
        v2.validate_binding2(candidate, intent)

    def test_duplicate_rule_handle_between_chains_of_same_table(self):
        rules = list(self.b.rules)
        rules[3] = replace(rules[3], handle=rules[0].handle)
        self.deny(lambda: replace(self.b, rules=tuple(rules)), 'v2_scope_collision')

    def test_duplicate_rule_handle_within_chain(self):
        rules = list(self.b.rules)
        rules[1] = replace(rules[1], handle=rules[0].handle)
        self.deny(lambda: replace(self.b, rules=tuple(rules)), 'v2_scope_collision')

    def test_duplicate_table_handle_within_family(self):
        i = intent2(catalog=catalog2(second_family='bridge'))
        b = binding2(i)
        v2.validate_binding2(b, i)
        self.deny(lambda: replace(b, tables=(b.tables[0], replace(b.tables[1], handle=b.tables[0].handle))),
                  'v2_scope_collision')

    def test_duplicate_chain_handle_within_table(self):
        chains = list(self.b.chains)
        chains[1] = replace(chains[1], handle=chains[0].handle)
        self.deny(lambda: replace(self.b, chains=tuple(chains)), 'v2_scope_collision')

    def test_conservative_chain_rule_collision_within_table(self):
        rules = list(self.b.rules)
        rules[0] = replace(rules[0], handle=self.b.chains[0].handle)
        self.deny(lambda: replace(self.b, rules=tuple(rules)), 'v2_scope_collision')

    def test_changed_table_handle_breaks_parent_references(self):
        self.deny(lambda: replace(self.b, tables=(replace(self.b.tables[0], handle=19), self.b.tables[1])),
                  'v2_parent_mismatch')

    def test_changed_chain_handle_breaks_parent_references(self):
        chains = (replace(self.b.chains[0], handle=19), *self.b.chains[1:])
        self.deny(lambda: replace(self.b, chains=chains), 'v2_parent_mismatch')

    def test_changed_rule_handle_breaks_counter_parent(self):
        rules = (replace(self.b.rules[0], handle=19), *self.b.rules[1:])
        self.deny(lambda: replace(self.b, rules=rules), 'v2_parent_mismatch')

    def test_coherent_handle_rewrite_fails_pinned_installation(self):
        candidate = binding2(self.i, table_handles=(18, 19), chain_handles=(11, 15, 11),
                             rule_handles=(12, 13, 14, 18, 12))
        v2.validate_binding2(candidate, self.i)  # Another unproven offline description.
        self.deny(lambda: v2.validate_same_installation2(candidate, self.b, self.i), 'v2_installation_changed')

    def test_parent_table_changed(self):
        chain = replace(self.b.chains[0], parent=replace(self.b.tables[0], handle=19))
        self.deny(lambda: replace(self.b, chains=(chain, *self.b.chains[1:])), 'v2_parent_mismatch')

    def test_parent_chain_changed_with_same_id(self):
        self.deny(lambda: replace(self.b.rules[0], parent=self.b.chains[1]), 'v2_rule_path_mismatch')

    def test_coherent_parent_chain_and_id_changed(self):
        rule = self.b.rules[0]
        chain = self.b.chains[1]
        rule = replace(rule, parent=chain, canonical_rule_id=v2.canonical_rule_id2(
                       chain.parent.family, chain.parent.name, chain.name, rule.ordinal))
        self.deny(lambda: replace(self.b, rules=(rule, *self.b.rules[1:])))

    def test_ordinal_changed(self):
        self.deny(lambda: replace(self.b.rules[0], ordinal=1), 'v2_rule_path_mismatch')

    def test_coherent_ordinal_and_id_changed(self):
        r = self.b.rules[0]
        t = r.parent.parent
        changed = replace(r, ordinal=7, canonical_rule_id=v2.canonical_rule_id2(t.family, t.name, r.parent.name, 7))
        self.deny(lambda: replace(self.b, rules=(changed, *self.b.rules[1:])), 'v2_rule_mismatch')

    def test_static_expression_digest_changed(self):
        changed = replace(self.b.rules[0], static_expression_digest=hd('different-static-expressions'))
        self.deny(lambda: replace(self.b, rules=(changed, *self.b.rules[1:])), 'v2_rule_mismatch')

    def test_rule_order_changed(self):
        rules = (self.b.rules[1], self.b.rules[0], *self.b.rules[2:])
        self.deny(lambda: replace(self.b, rules=rules), 'v2_rule_mismatch')

    def test_counter_position_changed_with_same_id(self):
        self.deny(lambda: replace(self.b.counters[0], expression_position=1), 'v2_counter_path_mismatch')

    def test_coherent_counter_position_and_id_changed(self):
        c = self.b.counters[0]
        changed = replace(c, expression_position=1, canonical_counter_id=v2.canonical_counter_id2(
            c.parent.canonical_rule_id, 1, c.purpose, c.probe_id))
        self.deny(lambda: replace(self.b, counters=(changed, *self.b.counters[1:])), 'v2_counter_mismatch')

    def test_counter_parent_changed(self):
        c = self.b.counters[0]
        rule = self.b.rules[1]
        changed = replace(c, parent=rule, canonical_counter_id=v2.canonical_counter_id2(
            rule.canonical_rule_id, c.expression_position, c.purpose, c.probe_id))
        self.deny(lambda: replace(self.b, counters=(changed, *self.b.counters[1:])), 'v2_parent_mismatch')

    def test_counter_purpose_changed(self):
        c = self.b.counters[0]
        changed = replace(c, purpose='terminal_drop', canonical_counter_id=v2.canonical_counter_id2(
            c.parent.canonical_rule_id, c.expression_position, 'terminal_drop', c.probe_id))
        self.deny(lambda: replace(self.b, counters=(changed, *self.b.counters[1:])), 'v2_counter_mismatch')

    def test_counter_probe_changed(self):
        c = self.b.counters[0]
        probe = self.c.allowed_probe_ids[1]
        changed = replace(c, probe_id=probe, canonical_counter_id=v2.canonical_counter_id2(
            c.parent.canonical_rule_id, c.expression_position, c.purpose, probe))
        self.deny(lambda: replace(self.b, counters=(changed, *self.b.counters[1:])), 'v2_counter_mismatch')

    def test_shared_counter_slot_is_rejected(self):
        counters = (self.b.counters[0], self.b.counters[0], *self.b.counters[2:])
        self.deny(lambda: replace(self.b, counters=counters), 'v2_scope_collision')

    def test_missing_or_extra_binding_rows(self):
        for field in ('tables', 'chains', 'rules', 'counters'):
            rows = getattr(self.b, field)
            for changed in (rows[:-1], rows + (rows[-1],)):
                with self.subTest(field=field, count=len(changed)):
                    self.deny(lambda: replace(self.b, **{field: changed}))

    def test_missing_unknown_and_lookalike_parent_types(self):
        for parent in (None, {}, asdict(self.b.tables[0]), self.b.rules[0]):
            with self.subTest(parent_type=type(parent)):
                self.deny(lambda: replace(self.b.chains[0], parent=parent), 'v2_type_invalid')

    def test_parent_subclasses_are_not_accepted(self):
        class ForgedNamespace(v2.NamespaceKey2):
            pass
        n = self.i.namespace
        forged = ForgedNamespace(n.host_boot_uuid, n.netns_inode, n.reader_session_uuid, n.namespace_binding_generation)
        self.deny(lambda: replace(self.b.tables[0], namespace=forged), 'v2_type_invalid')

    def test_epoch_and_generation_drift_reject_old_identities(self):
        for change in ({'install_epoch_uuid': uid(44)}, {'install_generation': 2}, {'writer_epoch_uuid': uid(33)}):
            with self.subTest(change=change):
                table = replace(self.b.tables[0], installation=replace(self.i.installation, **change))
                self.deny(lambda: replace(self.b, tables=(table, self.b.tables[1])), 'v2_generation_changed')

    def test_namespace_and_session_drift_reject_old_identities(self):
        for change in ({'host_boot_uuid': uid(11)}, {'netns_inode': 10000}, {'reader_session_uuid': uid(22)},
                       {'namespace_binding_generation': 2}):
            with self.subTest(change=change):
                table = replace(self.b.tables[0], namespace=replace(self.i.namespace, **change))
                self.deny(lambda: replace(self.b, tables=(table, self.b.tables[1])), 'v2_generation_changed')

    def test_replay_old_binding_under_new_generation(self):
        self.deny(lambda: v2.validate_binding2(self.b, intent2(generation=2)), 'v2_stale_binding')

    def test_replay_old_binding_under_new_epoch(self):
        self.deny(lambda: v2.validate_binding2(self.b, intent2(epoch=uid(44))), 'v2_stale_binding')

    def test_replay_old_binding_under_new_context_or_reader(self):
        for i in (intent2(context=uid(66)), intent2(session=uid(22))):
            self.deny(lambda: v2.validate_binding2(self.b, i), 'v2_stale_binding')

    def test_same_intent_is_idempotent_not_a_single_use_authority(self):
        self.assertEqual(v2.validate_binding2(self.b, self.i), v2.validate_binding2(self.b, self.i))
        self.assertFalse(self.b.ownership_proven)

    def test_missing_expected_intent_is_not_inferred(self):
        with self.assertRaises(TypeError):
            v2.validate_binding2(self.b)
        self.deny(lambda: v2.validate_binding2(self.b, self.b.intent.digest), 'v2_type_invalid')


class CatalogTests(_FixtureCase):
    def test_drop_only_catalog_can_explicitly_have_no_probes(self):
        table = v2.CanonicalTableSpec2('bridge', 'bootstrap_fixture')
        chain = v2.CanonicalChainSpec2(table, 'input', 'filter', 'input', 0, 'drop', 1)
        rule = v2.CanonicalRuleSpec2(chain, v2.canonical_rule_id2('bridge', table.name, chain.name, 0),
                                    0, hd('synthetic-counter-drop'), 2, 0, 'fallback_drop', None)
        catalog = v2.CanonicalRuleCatalog2(hd('synthetic-drop-only'), (table,), (chain,), (rule,), ())
        intent = intent2(catalog=catalog)
        binding = binding2(intent)
        self.assertEqual(binding.counters[0].purpose, 'fallback_drop')
        self.assertEqual(binding.counters[0].expression_position, 0)
        v2.validate_binding2(binding, intent)

    def test_catalog_pinned_to_approval(self):
        changed = replace(self.c, canonical_recipe_digest=hd('another-recipe'))
        self.deny(lambda: replace(self.i, catalog=changed), 'v2_approval_mismatch')

    def test_catalog_missing_rule(self):
        self.deny(lambda: replace(self.c, rules=self.c.rules[:-1]), 'v2_catalog_incomplete')

    def test_catalog_missing_table(self):
        self.deny(lambda: replace(self.c, tables=self.c.tables[:-1]), 'v2_parent_missing')

    def test_catalog_missing_chain(self):
        self.deny(lambda: replace(self.c, chains=self.c.chains[1:]), 'v2_parent_missing')

    def test_catalog_duplicate_table_chain_rule_or_probe(self):
        for field in ('tables', 'chains', 'rules', 'allowed_probe_ids'):
            rows = getattr(self.c, field)
            with self.subTest(field=field):
                self.deny(lambda: replace(self.c, **{field: rows + (rows[0],)}), 'v2_scope_collision')

    def test_catalog_reordered_chain_rules(self):
        self.deny(lambda: replace(self.c, rules=(self.c.rules[1], self.c.rules[0], *self.c.rules[2:])),
                  'v2_catalog_incomplete')

    def test_catalog_unknown_probe(self):
        changed = replace(self.c.rules[0], probe_id=hd('unknown-probe'))
        self.deny(lambda: replace(self.c, rules=(changed, *self.c.rules[1:])), 'v2_probe_invalid')

    def test_catalog_unused_allowed_probe(self):
        self.deny(lambda: replace(self.c, allowed_probe_ids=self.c.allowed_probe_ids + (hd('unused-probe'),)),
                  'v2_catalog_incomplete')

    def test_catalog_source_cannot_be_native_readback(self):
        self.deny(lambda: replace(self.c, source='native_readback'), 'v2_catalog_source_invalid')

    def test_canonical_ids_depend_on_parent_and_ordinal_not_handles(self):
        a = v2.canonical_rule_id2('bridge', 'table_a', 'forward', 0)
        variants = (('inet', 'table_a', 'forward', 0), ('bridge', 'table_b', 'forward', 0),
                    ('bridge', 'table_a', 'input', 0), ('bridge', 'table_a', 'forward', 1))
        self.assertEqual(len({a, *(v2.canonical_rule_id2(*v) for v in variants)}), 5)
        self.assertEqual(a, v2.canonical_rule_id2('bridge', 'table_a', 'forward', 0))

    def test_counter_positions_bound_to_rule_shape(self):
        for rule in self.c.rules:
            with self.subTest(purpose=rule.purpose):
                self.deny(lambda: replace(rule, counter_position=0), 'v2_counter_position_invalid')

    def test_nonprobe_purpose_cannot_borrow_probe_id(self):
        self.deny(lambda: replace(self.c.rules[3], probe_id=self.c.allowed_probe_ids[0]), 'v2_probe_invalid')

    def test_probe_purpose_requires_explicit_probe_id(self):
        self.deny(lambda: replace(self.c.rules[0], probe_id=None), 'v2_digest_invalid')

    def test_competing_chain_hook_priority(self):
        chain = replace(self.c.chains[1], hook='prerouting')
        self.deny(lambda: replace(self.c, chains=(self.c.chains[0], chain, self.c.chains[2])), 'v2_scope_collision')


class BoundaryTests(_FixtureCase):
    def test_all_contracts_are_frozen_and_have_no_mutable_fields(self):
        objects = (self.i, self.i.approval, self.i.namespace, self.i.installation, self.c, self.b,
                   self.b.witness_reference, *self.c.tables, *self.c.chains, *self.c.rules,
                   *self.b.tables, *self.b.chains, *self.b.rules, *self.b.counters)
        for obj in objects:
            with self.subTest(type=type(obj).__name__), self.assertRaises(FrozenInstanceError):
                obj.version = 1
            self.assertFalse(hasattr(obj, '__dict__'))

    def test_versions_domains_origins_are_exact(self):
        for change in ({'version': True}, {'version': 1}, {'version': 2.0},
                       {'contract': 'tc-native-compatibility-v1'}, {'method': 'nft_counter_probe_v1'},
                       {'domain': 'tc-nft-counter-probe-v1-offline'}, {'origin': 'physical_linux'},
                       {'authentication': 'authenticated'}, {'trace_delivery_complete': 'proven'}):
            with self.subTest(change=change):
                self.deny(lambda: replace(self.b, **change))

    def test_physical_and_ownership_flags_cannot_be_true_or_int(self):
        for field in ('physical_probe_permitted', 'ownership_proven', 'continuous_attestation'):
            for value in (True, 0, 1, None, 'false'):
                with self.subTest(field=field, value=value):
                    self.deny(lambda: replace(self.b, **{field: value}), 'v2_authority_forbidden')

    def test_invalid_uuid_never_generates_replacement(self):
        for value in (None, '', 'abc', uid(1).upper().replace('00000000', 'ABCDEF00'), 1,
                      '00000000-0000-0000-0000-000000000000'):
            with self.subTest(value=value):
                self.deny(lambda: replace(self.i.namespace, host_boot_uuid=value), 'v2_uuid_invalid')

    def test_required_uuid_is_not_defaulted(self):
        with self.assertRaises(TypeError):
            v2.NamespaceKey2(netns_inode=1, reader_session_uuid=uid(2), namespace_binding_generation=1)

    def test_invalid_digests_are_rejected(self):
        for value in (None, '', 'a'*63, 'A'*64, 'g'*64, 'sha256:' + 'a'*64, True):
            with self.subTest(value=value):
                self.deny(lambda: replace(self.i.approval, catalog_digest=value), 'v2_digest_invalid')

    def test_bool_negative_zero_float_and_overflow_handles(self):
        for obj in (self.b.tables[0], self.b.chains[0], self.b.rules[0]):
            for value in (True, False, -1, 0, 1.0, '8', 2**63):
                with self.subTest(type=type(obj).__name__, value=value):
                    self.deny(lambda: replace(obj, handle=value), 'v2_integer_invalid')

    def test_integer_upper_bound_is_accepted_for_identity_shape(self):
        self.assertEqual(replace(self.b.tables[0], handle=v2.MAX_INTEGER).handle, v2.MAX_INTEGER)

    def test_generation_inode_ordinal_and_position_bounds(self):
        fields = ((self.i.namespace, 'netns_inode'), (self.i.namespace, 'namespace_binding_generation'),
                  (self.i.installation, 'install_generation'))
        for obj, field in fields:
            for value in (True, 0, -1, 2**63):
                with self.subTest(field=field, value=value):
                    self.deny(lambda: replace(obj, **{field: value}), 'v2_integer_invalid')
        for value in (True, -1, 128):
            self.deny(lambda: replace(self.b.rules[0], ordinal=value), 'v2_integer_invalid')
        for value in (True, -1, 64):
            self.deny(lambda: replace(self.b.counters[0], expression_position=value), 'v2_integer_invalid')

    def test_priority_types_and_bounds(self):
        for value in (True, 0.0, '-310', -(2**31)-1, 2**31):
            with self.subTest(value=value):
                self.deny(lambda: replace(self.b.chains[0], priority=value), 'v2_integer_invalid')

    def test_immutable_tuple_required_not_lists_or_generators(self):
        for value in (list(self.b.rules), iter(self.b.rules), {}, None):
            self.deny(lambda: replace(self.b, rules=value), 'v2_collection_invalid')

    def test_unknown_fields_are_not_accepted(self):
        with self.assertRaises(TypeError):
            replace(self.b.rules[0], label='same-name')
        with self.assertRaises(TypeError):
            replace(self.b, confirmed=True)

    def test_witness_cannot_be_marked_committed(self):
        for status in ('confirmed', 'committed', True, None):
            self.deny(lambda: replace(self.b.witness_reference, status=status), 'v2_witness_unproven')

    def test_missing_or_dict_witness_cannot_confirm_binding(self):
        for value in (None, {}, asdict(self.b.witness_reference)):
            self.deny(lambda: replace(self.b, witness_reference=value), 'v2_type_invalid')

    def test_wrong_witness_intent_transaction_or_generation_reference(self):
        for change in ({'intent_digest': hd('other-intent')}, {'installation_key_digest': hd('old-generation')},
                       {'transaction_uuid': uid(77)}):
            witness = replace(self.b.witness_reference, **change)
            self.deny(lambda: replace(self.b, witness_reference=witness), 'v2_witness_reference_mismatch')

    def test_same_name_handle_recipe_and_readback_hash_are_not_ownership(self):
        witness = replace(self.b.witness_reference, reference_digest=self.b.independent_readback_reference_digest)
        candidate = replace(self.b, witness_reference=witness)
        self.assertEqual(candidate.witness_reference.status, 'unverified_reference')
        self.assertFalse(candidate.ownership_proven)
        self.assertFalse(candidate.physical_probe_permitted)

    def test_binding_status_cannot_claim_confirmation(self):
        self.deny(lambda: replace(self.b, status='confirmed_installation'), 'v2_witness_unproven')

    def test_intent_operation_cannot_authorize_existing_object_adoption(self):
        for operation in ('adopt', 'replace', 'delete', 'install_and_collect'):
            self.deny(lambda: replace(self.i, operation=operation), 'v2_operation_invalid')

    def test_approval_install_key_refs_are_exact(self):
        for change in ({'approval_digest': hd('v1-approval')}, {'binding_digest': hd('foreign-binding')},
                       {'context_uuid': uid(66)}):
            key = replace(self.i.installation, **change)
            self.deny(lambda: replace(self.i, installation=key), 'v2_approval_mismatch')

    def test_v1_and_runtime_approvals_cannot_be_installed_as_v2(self):
        from trusted_checker_network.tests.counter_support import CounterLab
        lab = CounterLab()
        self.addCleanup(lab.close)
        for old in (lab.approval, lab.runtime, lab.base.approval, lab.sign(lab.approval, 'approval')):
            self.deny(lambda: replace(self.i, approval=old), 'v2_type_invalid')

    def test_v1_hmac_boundary_rejects_v2_types(self):
        from trusted_checker_network.counter_auth import canonical
        from trusted_checker_runtime.profiles import Denied
        with self.assertRaises(Denied):
            canonical('approval', 'operator:counter', self.i.approval)

    def test_legacy_physical_gate_rejects_binding(self):
        from trusted_checker_physical.collector import PhysicalProbeGate
        from trusted_checker_runtime.profiles import Denied
        with self.assertRaisesRegex(Denied, 'physical_network_boundary_not_accepted'):
            PhysicalProbeGate.permit(self.b)

    def test_dict_import_is_not_a_binding_api(self):
        self.deny(lambda: v2.validate_binding2(asdict(self.b), self.i), 'v2_type_invalid')
        with self.assertRaises(v2.ContractViolation2):
            v2.InstallationBinding2(**asdict(self.b))
        self.assertFalse(hasattr(v2, 'from_dict'))

    def test_content_digest_changes_and_does_not_authenticate(self):
        self.assertEqual(len(self.b.digest), 64)
        changed = replace(self.b, independent_readback_reference_digest=hd('different-capture-ref'))
        self.assertNotEqual(self.b.digest, changed.digest)
        self.assertEqual(changed.authentication, 'not_authenticated')
        self.deny(lambda: v2.validate_same_installation2(changed, self.b, self.i), 'v2_installation_changed')


class NativeIdentityShapeTests(unittest.TestCase):
    def test_actual_same_family_table_and_rule_handle_reuse(self):
        root = Path(__file__).parent / 'fixtures/kernel_6_8_nft_1_0_9/native'
        raw = (root / 'nft_ruleset_final.json').read_bytes()
        manifest = json.loads((root / 'provenance.json').read_text())
        self.assertEqual(hashlib.sha256(raw).hexdigest(), manifest['files']['nft_ruleset_final.json']['sha256'])
        data = json.loads(raw)['nftables']
        tables = [item['table'] for item in data if 'table' in item]
        chains = [item['chain'] for item in data if 'chain' in item]
        strict_rule8 = next(item['rule'] for item in data if item.get('rule', {}).get('table') == 'tc_strict_lab'
                            and item['rule']['handle'] == 8)
        self.assertEqual([t['handle'] for t in tables], [6, 8])
        self.assertEqual([c['handle'] for c in chains], [1, 1])
        self.assertEqual(strict_rule8['handle'], tables[1]['handle'])
        # Borrow only observed NUMBERS into an explicitly synthetic typed baseline.
        # Neither lab names/policies/expressions nor cumulative rows are approved.
        intent = intent2(catalog=catalog2(second_family='bridge'))
        baseline = binding2(intent)
        v2.validate_binding2(baseline, intent)
        candidate = binding2(intent, table_handles=tuple(t['handle'] for t in tables),
                             chain_handles=(chains[0]['handle'], 5, chains[1]['handle']),
                             rule_handles=(2, 3, 4, 8, strict_rule8['handle']))
        v2.validate_binding2(candidate, intent)
        self.assertFalse({t.name for t in candidate.tables} & {'tc_ct_lab', 'tc_strict_lab'})
        self.assertEqual(candidate.tables[1].handle, candidate.rules[-1].handle)
        self.assertFalse(candidate.ownership_proven)


class IsolationTests(unittest.TestCase):
    def test_module_has_no_parser_io_writers_or_id_discovery(self):
        path = Path(v2.__file__)
        tree = ast.parse(path.read_text())
        imports = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imports.add(node.module)
            if isinstance(node, ast.Call):
                name = node.func.id if isinstance(node.func, ast.Name) else node.func.attr if isinstance(node.func, ast.Attribute) else ''
                self.assertNotIn(name, ('open', 'loads', 'load', 'uuid4', 'uuid1', 'eval', 'exec', '__import__'))
        self.assertEqual(imports, {'dataclasses', 'hashlib', 'json', 're', 'uuid'})

    def test_fresh_import_does_not_import_runtime_or_call_network_process(self):
        code = '''import socket, subprocess, os
def forbidden(*args, **kwargs): raise AssertionError("physical operation")
socket.socket = forbidden
subprocess.Popen = forbidden
if hasattr(os, "setns"): os.setns = forbidden
import trusted_checker_network.native_v2_contracts
import sys
assert not any(n in sys.modules for n in ("docker", "django", "trusted_checker_runtime.contracts", "trusted_checker_network.counter_contracts"))
'''
        subprocess.run([sys.executable, '-c', code], check=True, capture_output=True, timeout=10)
