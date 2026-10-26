"""Offline V2-02 stage-specific positives/mutations; no kernel operations."""
import ast
from copy import deepcopy
from dataclasses import FrozenInstanceError, replace
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import unittest

from trusted_checker_network import native_v2_contracts as c
from trusted_checker_network import native_v2_json as j
from trusted_checker_network import native_v2_readback as r
from .native_v2_support import hd, uid
from .native_v2_readback_support import ReadbackFixture2


class _FixtureCase(unittest.TestCase):
    def setUp(self):
        self.f = ReadbackFixture2.create()

    def deny(self, change, reason=None, stage='validate'):
        document = self.f.document()
        change(document)
        with self.assertRaises(c.ContractViolation2) as caught:
            getattr(self.f, stage)(document)
        if reason:
            self.assertEqual(str(caught.exception), reason)

    @staticmethod
    def rules(document):
        return [obj['rule'] for obj in document['nftables'] if 'rule' in obj]

    @staticmethod
    def chains(document):
        return [obj['chain'] for obj in document['nftables'] if 'chain' in obj]


class DecodeTests(_FixtureCase):
    def test_distinct_stage_types_do_not_auto_validate(self):
        decoded = self.f.decode()
        normalized = r.normalize_rules2(decoded)
        validated = self.f.validate()
        self.assertIs(type(decoded), r.DecodedNative2)
        self.assertIs(type(normalized), r.NormalizedRules2)
        self.assertIs(type(validated), r.ValidatedRecipe2)
        self.assertEqual(decoded.stage, 'format_decoded')
        self.assertEqual(normalized.stage, 'graph_normalized')
        self.assertEqual(validated.result, 'recipe_matched')
        self.assertFalse(hasattr(decoded, 'result'))

    def test_exact_metadata_and_raw_fingerprint_preserved(self):
        raw = json.dumps(self.f.document()).encode()
        result = r.decode_native2(raw, self.f.expected.profile, self.f.context)
        self.assertEqual(result.metainfo, ('1.0.9', 'Old Doc Yak #3', 1))
        self.assertEqual((result.raw_digest, result.raw_byte_count), (hashlib.sha256(raw).hexdigest(), len(raw)))

    def test_missing_metadata(self):
        self.deny(lambda d: d['nftables'].pop(0), stage='decode')

    def test_duplicate_metadata(self):
        self.deny(lambda d: d['nftables'].insert(1, deepcopy(d['nftables'][0])), stage='decode')

    def test_metadata_not_first(self):
        self.deny(lambda d: d['nftables'].append(d['nftables'].pop(0)), stage='decode')

    def test_extra_metadata_field(self):
        self.deny(lambda d: d['nftables'][0]['metainfo'].__setitem__('build', 'supplied-build'), stage='decode')

    def test_wrong_version_release_schema(self):
        for field, value in (('version', '1.1.0'), ('release_name', 'other'), ('json_schema_version', 2),
                             ('json_schema_version', '1')):
            with self.subTest(field=field, value=value):
                self.deny(lambda d: d['nftables'][0]['metainfo'].__setitem__(field, value),
                          'v2_native_profile_mismatch', stage='decode')

    def test_wrong_binary_witness_not_inferred_from_metadata(self):
        context = replace(self.f.context, nft_binary_digest=hd('foreign-build'))
        with self.assertRaisesRegex(c.ContractViolation2, 'v2_native_profile_mismatch'):
            r.decode_native2(json.dumps(self.f.document()).encode(), self.f.expected.profile, context)

    def test_profile_cannot_be_selected_from_input(self):
        with self.assertRaises(c.ContractViolation2):
            replace(self.f.expected.profile, nft_version='1.1.0')
        self.deny(lambda d: d.__setitem__('profile', 'permissive'), stage='decode')

    def test_duplicate_key_including_escaped_equivalent(self):
        raw = json.dumps(self.f.document()).replace('"handle": 8', '"handle": 8, "han\\u0064le": 8', 1).encode()
        with self.assertRaisesRegex(c.ContractViolation2, 'v2_json_duplicate_key'):
            r.decode_native2(raw, self.f.expected.profile, self.f.context)

    def test_bool_as_handle_priority_and_counter(self):
        for change in (lambda d: d['nftables'][1]['table'].__setitem__('handle', True),
                       lambda d: self.chains(d)[0].__setitem__('prio', False),
                       lambda d: self.rules(d)[0]['expr'][-1]['counter'].__setitem__('packets', True)):
            self.deny(change, 'v2_json_integer_invalid', stage='decode')

    def test_float_nonfinite_numbers(self):
        for value in (1.0, float('nan'), float('inf'), -float('inf')):
            with self.subTest(value=value):
                self.deny(lambda d: self.chains(d)[0].__setitem__('prio', value), stage='decode')

    def test_counter_integer_bounds(self):
        for value in (-1, 2**63, '1'):
            self.deny(lambda d: self.rules(d)[0]['expr'][-1]['counter'].__setitem__('bytes', value), stage='decode')
        document = self.f.document()
        self.rules(document)[0]['expr'][-1]['counter'] = {'packets': 2**63 - 1, 'bytes': 2**63 - 1}
        self.assertEqual(self.f.validate(document).result, 'recipe_matched')

    def test_unknown_objects_and_transaction_wrappers(self):
        for kind in ('set', 'map', 'flowtable', 'object', 'add', 'create', 'delete'):
            self.deny(lambda d: d['nftables'].append({kind: {}}), stage='decode')

    def test_extra_table_chain_rule_fields(self):
        for kind in ('table', 'chain', 'rule'):
            def mutate(d):
                next(o[kind] for o in d['nftables'] if kind in o)['unexpected'] = 1
            self.deny(mutate, stage='decode')

    def test_supplied_validation_or_recipe_data_is_rejected(self):
        for key, value in (('validated', True), ('recipe_digest', hd('caller')), ('expected_rules', [])):
            self.deny(lambda d: d.__setitem__(key, value), stage='decode')

    def test_invalid_counter_named_shared_or_extra_fields(self):
        for counter in ('shared', None, {'packets': 1}, {'packets': 1, 'bytes': 60, 'name': 'shared'}):
            self.deny(lambda d: self.rules(d)[0]['expr'][-1].__setitem__('counter', counter), stage='decode')

    def test_unknown_expression_and_payload_field(self):
        self.deny(lambda d: self.rules(d)[0]['expr'].__setitem__(0, {'queue': {'num': 1}}), stage='decode')
        self.deny(lambda d: self.rules(d)[0]['expr'][2]['match']['left']['payload'].__setitem__('field', 'unknown'), stage='decode')

    def test_named_arp_fields_decode_without_changing_expected_recipe(self):
        document = self.f.document()
        rule = self.rules(document)[3]
        pairs = [('ether', 'type', 'arp'), ('ether', 'daddr', '02:00:00:00:00:02'),
                 ('arp', 'operation', 'request'), ('arp', 'saddr ether', '02:00:00:00:00:01'),
                 ('arp', 'saddr ip', '172.30.0.3'), ('arp', 'daddr ip', '172.30.0.2')]
        rule['expr'] = [{'match': {'op': '==', 'left': {'payload': {'protocol': p, 'field': f}}, 'right': value}}
                        for p, f, value in pairs] + [{'counter': {'packets': 1, 'bytes': 42}}, {'accept': None}]
        decoded = self.f.decode(document)
        arp_rule = [o for o in decoded.objects if type(o) is r.NativeRule2][3]
        self.assertEqual(arp_rule.counter_position, 6)
        self.assertEqual(arp_rule.counter.bytes, 42)
        with self.assertRaises(c.ContractViolation2):
            self.f.validate(document)


class GraphTests(_FixtureCase):
    def test_both_object_groupings_match_same_graph(self):
        a = self.f.normalize(self.f.document(grouping='serialized'))
        b = self.f.normalize(self.f.document(grouping='native'))
        self.assertEqual(a.tables, b.tables)
        self.assertNotEqual(a.decoded.raw_digest, b.decoded.raw_digest)
        self.assertEqual(r.validate_recipe2(b, self.f.expected, self.f.binding, self.f.expected.intent).result, 'recipe_matched')

    def test_key_order_whitespace_escapes_do_not_change_policy(self):
        raw = json.dumps(self.f.document(), sort_keys=True, indent=2).replace('vethRunner', 'veth\\u0052unner').encode()
        graph = r.normalize_rules2(r.decode_native2(raw, self.f.expected.profile, self.f.context))
        self.assertEqual(graph.tables, self.f.normalize().tables)

    def test_missing_or_extra_table(self):
        self.deny(lambda d: d['nftables'].pop(1), 'v2_parent_missing', stage='normalize')
        self.deny(lambda d: d['nftables'].append({'table': {'family': 'bridge', 'name': 'foreign', 'handle': 99}}))

    def test_missing_or_extra_chain(self):
        self.deny(lambda d: d['nftables'].remove(next(o for o in d['nftables'] if 'chain' in o)), stage='normalize')
        def extra(d):
            ch = deepcopy(self.chains(d)[0])
            ch.update(name='foreign', handle=90, hook='input')
            d['nftables'].append({'chain': ch})
        self.deny(extra)

    def test_rule_before_parent_declaration(self):
        def change(d):
            index = next(i for i, obj in enumerate(d['nftables']) if 'rule' in obj)
            d['nftables'].insert(1, d['nftables'].pop(index))
        self.deny(change, 'v2_parent_missing', stage='normalize')

    def test_dangling_rule_parent(self):
        self.deny(lambda d: self.rules(d)[0].__setitem__('chain', 'missing'), 'v2_parent_missing', stage='normalize')

    def test_competing_hooks_priorities(self):
        self.deny(lambda d: self.chains(d)[1].__setitem__('hook', 'prerouting'), 'v2_scope_collision', stage='normalize')

    def test_duplicate_table_or_chain_object(self):
        for kind in ('table', 'chain'):
            self.deny(lambda d: d['nftables'].append(deepcopy(next(o for o in d['nftables'] if kind in o))),
                      'v2_scope_collision', stage='normalize')

    def test_table_and_rule_handle8_are_different_scopes(self):
        graph = self.f.normalize()
        table = next(t for t in graph.tables if t.identity.family == 'bridge')
        self.assertEqual(table.identity.handle, 8)
        self.assertIn(8, [rule.identity.handle for ch in table.chains for rule in ch.rules])

    def test_duplicate_table_handle_under_distinct_name_same_family(self):
        self.deny(lambda d: d['nftables'].append({'table': {'family': 'bridge', 'name': 'other', 'handle': 8}}),
                  'v2_scope_collision', stage='normalize')

    def test_table_handle_reuse_different_family_is_shape_valid_but_not_pinned(self):
        document = self.f.document()
        next(o['table'] for o in document['nftables'] if o.get('table', {}).get('family') == 'inet')['handle'] = 8
        graph = self.f.normalize(document)
        self.assertEqual([t.identity.handle for t in graph.tables], [8, 8])
        with self.assertRaisesRegex(c.ContractViolation2, 'v2_identity_mismatch'):
            self.f.validate(document)

    def test_rule_handle_duplicate_across_chains_in_table(self):
        self.deny(lambda d: self.rules(d)[3].__setitem__('handle', self.rules(d)[0]['handle']),
                  'v2_scope_collision', stage='normalize')

    def test_duplicate_chain_handle_in_table(self):
        self.deny(lambda d: self.chains(d)[1].__setitem__('handle', self.chains(d)[0]['handle']),
                  'v2_scope_collision', stage='normalize')

    def test_chain_rule_handle_collision_in_table(self):
        self.deny(lambda d: self.rules(d)[0].__setitem__('handle', self.chains(d)[0]['handle']),
                  'v2_scope_collision', stage='normalize')

    def test_no_loss_or_forging_normalized_tables(self):
        graph = self.f.normalize()
        with self.assertRaisesRegex(c.ContractViolation2, 'v2_graph_mismatch'):
            replace(graph, tables=graph.tables[:-1])

    def test_normalized_ordinal_cannot_be_forged(self):
        graph = self.f.normalize()
        ch = next(ch for table in graph.tables for ch in table.chains if ch.identity.name == 'prerouting')
        identity = ch.rules[0].identity
        table = identity.parent.parent
        changed = replace(identity, ordinal=7, canonical_rule_id=c.canonical_rule_id2(
            table.family, table.name, identity.parent.name, 7))
        changed_rule = replace(ch.rules[0], identity=changed)
        with self.assertRaisesRegex(c.ContractViolation2, 'v2_parent_mismatch'):
            replace(ch, rules=(changed_rule, *ch.rules[1:]))

    def test_per_chain_ordinals_preserve_source_rule_order(self):
        graph = self.f.normalize()
        ch = next(ch for table in graph.tables for ch in table.chains if ch.identity.name == 'prerouting')
        self.assertEqual([rule.identity.ordinal for rule in ch.rules], [0, 1, 2])
        self.assertEqual([rule.identity.handle for rule in ch.rules], [2, 3, 4])


class ValidationTests(_FixtureCase):
    def test_full_positive_is_only_structural_no_measurement_or_authority(self):
        value = self.f.validate()
        self.assertEqual((value.result, value.reason), ('recipe_matched', 'offline_structural_recipe_matched'))
        for name in ('physical_probe_permitted', 'ownership_proven', 'continuous_attestation',
                     'measurement_verified', 'topology_verified'):
            self.assertIs(getattr(value, name), False)
        self.assertEqual((value.installation_witness, value.byte_accounting), ('unverified_reference', 'unproven'))

    def test_missing_and_duplicate_rule(self):
        self.deny(lambda d: d['nftables'].remove(next(o for o in d['nftables'] if 'rule' in o)))
        self.deny(lambda d: d['nftables'].append(deepcopy(next(o for o in d['nftables'] if 'rule' in o))))

    def test_rule_reordering_is_not_sorted_by_handle(self):
        def change(d):
            indices = [i for i, obj in enumerate(d['nftables']) if 'rule' in obj]
            a, b = indices[:2]
            d['nftables'][a], d['nftables'][b] = d['nftables'][b], d['nftables'][a]
        self.deny(change, 'v2_expression_mismatch')

    def test_expression_reordering(self):
        def change(d):
            expr = self.rules(d)[0]['expr']
            expr[0], expr[1] = expr[1], expr[0]
        self.deny(change, 'v2_expression_mismatch')

    def test_counter_moved_before_match(self):
        def change(d):
            expr = self.rules(d)[0]['expr']
            expr.insert(0, expr.pop())
        self.deny(change, 'v2_expression_mismatch')

    def test_counter_after_verdict(self):
        def change(d):
            expr = self.rules(d)[2]['expr']
            expr.append(expr.pop(-2))
        self.deny(change, 'v2_counter_layout_invalid', stage='decode')

    def test_missing_or_duplicate_counter(self):
        self.deny(lambda d: self.rules(d)[0]['expr'].pop())
        self.deny(lambda d: self.rules(d)[0]['expr'].append(deepcopy(self.rules(d)[0]['expr'][-1])), stage='decode')

    def test_substituted_terminal_verdict(self):
        self.deny(lambda d: self.rules(d)[2]['expr'].__setitem__(-1, {'accept': None}), 'v2_expression_mismatch')

    def test_verdict_added_to_nonterminal_ingress(self):
        self.deny(lambda d: self.rules(d)[0]['expr'].append({'drop': None}), 'v2_expression_mismatch')

    def test_interface_ip_port_mutations(self):
        for index, value in ((1, 'vethForeign'), (4, '172.30.0.99'), (8, 9090)):
            self.deny(lambda d: self.rules(d)[0]['expr'][index]['match'].__setitem__('right', value), 'v2_expression_mismatch')

    def test_hook_priority_policy_mutations(self):
        for field, value in (('hook', 'input'), ('prio', -200), ('policy', 'accept')):
            self.deny(lambda d: self.chains(d)[0].__setitem__(field, value), 'v2_identity_mismatch')

    def test_table_chain_rule_handle_replacement(self):
        for kind in ('table', 'chain', 'rule'):
            self.deny(lambda d: next(o[kind] for o in d['nftables'] if kind in o).__setitem__('handle', 99), 'v2_identity_mismatch')

    def test_parent_replacement_to_existing_chain(self):
        self.deny(lambda d: self.rules(d)[0].__setitem__('chain', 'forward'))

    def test_epoch_generation_context_mismatch(self):
        for change in ({'install_epoch_uuid': uid(44)}, {'install_generation': 2}, {'context_uuid': uid(66)}):
            ctx = replace(self.f.context, installation=replace(self.f.context.installation, **change))
            decoded = r.decode_native2(json.dumps(self.f.document()).encode(), self.f.expected.profile, ctx)
            with self.assertRaisesRegex(c.ContractViolation2, 'v2_generation_changed'):
                r.validate_recipe2(r.normalize_rules2(decoded), self.f.expected, self.f.binding, self.f.expected.intent)

    def test_wrong_reader_namespace_session(self):
        ctx = replace(self.f.context, namespace=replace(self.f.context.namespace, reader_session_uuid=uid(22)))
        decoded = r.decode_native2(json.dumps(self.f.document()).encode(), self.f.expected.profile, ctx)
        with self.assertRaisesRegex(c.ContractViolation2, 'v2_generation_changed'):
            r.validate_recipe2(r.normalize_rules2(decoded), self.f.expected, self.f.binding, self.f.expected.intent)

    def test_foreign_same_name_or_handle_is_not_adopted(self):
        self.deny(lambda d: self.rules(d)[0].__setitem__('table', 'foreign'), stage='normalize')
        graph = self.f.normalize()
        binding = replace(self.f.binding, independent_readback_reference_digest=hd('foreign-unverified-reference'))
        result = r.validate_recipe2(graph, self.f.expected, binding, self.f.expected.intent)
        self.assertFalse(result.ownership_proven)  # Both references are unverified forever.

    def test_numeric_rows_do_not_change_static_policy_or_verify_deltas(self):
        doc = self.f.document()
        for rule in self.rules(doc):
            next(e['counter'] for e in rule['expr'] if 'counter' in e).update(packets=77, bytes=12345)
        result = self.f.validate(doc)
        self.assertEqual(result.result, 'recipe_matched')
        self.assertFalse(result.measurement_verified)
        graph = result.normalized
        self.assertTrue(all(rule.counter.packets == 77 for table in graph.tables for ch in table.chains for rule in ch.rules))

    def test_expected_static_digest_and_ast_both_checked(self):
        rule = self.f.expected.rules[0]
        nodes = list(rule.expressions)
        nodes[1] = replace(nodes[1], right='vethForeign')
        changed = replace(rule, expressions=tuple(nodes))
        with self.assertRaisesRegex(c.ContractViolation2, 'v2_rule_mismatch'):
            replace(self.f.expected, rules=(changed, *self.f.expected.rules[1:]))

    def test_recipe_digest_is_independently_recomputed(self):
        catalog = replace(self.f.expected.intent.catalog, canonical_recipe_digest=hd('fake-recipe'))
        digest = r.expected_recipe_digest2(catalog, self.f.expected.rules)
        self.assertNotEqual(digest, catalog.canonical_recipe_digest)

    def test_requires_typed_expected_and_pinned_binding(self):
        graph = self.f.normalize()
        for expected, binding in (({}, self.f.binding), (self.f.expected, {}), (self.f.expected, None)):
            with self.assertRaises(c.ContractViolation2):
                r.validate_recipe2(graph, expected, binding, self.f.expected.intent)

    def test_result_cannot_claim_physical_topology_measurement_or_witness(self):
        value = self.f.validate()
        for field, flag in (('physical_probe_permitted', True), ('ownership_proven', True),
                            ('measurement_verified', True), ('topology_verified', True),
                            ('installation_witness', 'committed'), ('byte_accounting', 'kernel_verified')):
            with self.assertRaises(c.ContractViolation2):
                replace(value, **{field: flag})
        with self.assertRaises(TypeError):
            replace(value, result='recipe_matched')

    def test_stage_dtos_are_immutable(self):
        for obj in (self.f.decode(), self.f.normalize(), self.f.validate()):
            with self.assertRaises(FrozenInstanceError):
                obj.version = 1


class SemanticsTests(unittest.TestCase):
    def test_ct_in_and_equality_remain_unproven_even_with_exact_ast(self):
        for op in ('in', '=='):
            f = ReadbackFixture2.create(ct=op)
            value = f.validate()
            self.assertEqual((value.result, value.reason), ('recipe_unproven', 'ct_semantics_unproven'))
            self.assertFalse(value.physical_probe_permitted)

    def test_ct_operator_mutation_is_not_an_alias(self):
        f = ReadbackFixture2.create(ct='==')
        document = f.document()
        node = next(expr['match'] for obj in document['nftables'] for expr in obj.get('rule', {}).get('expr', [])
                    if expr.get('match', {}).get('left') == {'ct': {'key': 'state'}})
        node['op'] = 'in'
        with self.assertRaisesRegex(c.ContractViolation2, 'v2_expression_mismatch'):
            f.validate(document)

    def test_ct_extended_set_mask_related_and_operator_fail_closed(self):
        f = ReadbackFixture2.create(ct='in')
        for field, value in (('right', ['established']), ('right', {'set': ['new', 'established']}),
                             ('right', 2), ('right', 'related'), ('op', '!=')):
            document = f.document()
            node = next(expr['match'] for obj in document['nftables'] for expr in obj.get('rule', {}).get('expr', [])
                        if expr.get('match', {}).get('left') == {'ct': {'key': 'state'}})
            node[field] = value
            with self.assertRaises(c.ContractViolation2):
                f.decode(document)

    def test_known_literal_raw_shape_is_only_unproven(self):
        f = ReadbackFixture2.create(raw=True)
        value = f.validate()
        self.assertEqual((value.result, value.reason), ('recipe_unproven', 'raw_payload_representation_unproven'))

    def test_unknown_raw_representation_fails_with_finite_reason(self):
        f = ReadbackFixture2.create(raw=True)
        for change in ({'base': 'nh'}, {'offset': '0'}, {'len': 0}, {'unknown': 1}):
            document = f.document()
            payload = next(e['match']['left']['payload'] for obj in document['nftables']
                for e in obj.get('rule', {}).get('expr', [])
                if 'base' in e.get('match', {}).get('left', {}).get('payload', {}))
            payload.update(change)
            with self.assertRaises(c.ContractViolation2) as caught:
                f.decode(document)
            self.assertIn(str(caught.exception), ('v2_raw_payload_representation_unproven', 'v2_integer_invalid'))

    def test_raw_hex_integer_and_width_are_not_normalized(self):
        f = ReadbackFixture2.create(raw=True)
        document = f.document()
        node = next(e['match'] for obj in document['nftables'] for e in obj.get('rule', {}).get('expr', [])
                    if 'base' in e.get('match', {}).get('left', {}).get('payload', {}))
        node['right'] = 1
        with self.assertRaisesRegex(c.ContractViolation2, 'v2_raw_payload_representation_unproven'):
            f.decode(document)
        node['right'] = '0x01'
        with self.assertRaisesRegex(c.ContractViolation2, 'v2_expression_mismatch'):
            f.validate(document)


class BoundedJsonTests(unittest.TestCase):
    def test_boundaries_and_unicode_escapes(self):
        self.assertEqual(j.bounded_json2(b'{"a":"\\uD834\\uDD1E","b":"\\n\\t\\/\\\\\\\""}'),
                         {'a': '\U0001D11E', 'b': '\n\t/\\"'})
        self.assertEqual(j.bounded_json2(b'"' + b'a'*256 + b'"'), 'a'*256)

    def test_malformed_json_and_invalid_escapes(self):
        for raw in (b'', b'{', b'[0,]', b'{"x":0,}', b'01', b'1 2', b'"\\uD800"',
                    b'"\\uDC00"', b'"\\uD800\\u0001"', b'"\\q"', b'"\n"', b'-'):
            with self.subTest(raw=raw), self.assertRaises(c.ContractViolation2):
                j.bounded_json2(raw)

    def test_utf8_bom_invalid_encoding_and_nonbytes(self):
        for raw in (b'\xef\xbb\xbf{}', b'"\xff"', '{}', bytearray(b'{}')):
            with self.assertRaises(c.ContractViolation2):
                j.bounded_json2(raw)

    def test_source_size_checked_before_tree(self):
        self.assertEqual(j.bounded_json2(b'{}' + b' '*(j.MAX_BYTES-2)), {})
        with self.assertRaisesRegex(c.ContractViolation2, 'v2_json_size_invalid'):
            j.bounded_json2(b'{}' + b' '*j.MAX_BYTES)

    def test_depth_bound_before_nested_container_allocation(self):
        self.assertEqual(j.bounded_json2(b'['*31 + b'0' + b']'*31), self._nested(31))
        with self.assertRaisesRegex(c.ContractViolation2, 'v2_json_depth_limit'):
            j.bounded_json2(b'['*32 + b'0' + b']'*32)

    @staticmethod
    def _nested(count):
        value = 0
        for _ in range(count):
            value = [value]
        return value

    def test_nodes_bounded_including_keys(self):
        with self.assertRaisesRegex(c.ContractViolation2, 'v2_json_nodes_limit'):
            j.bounded_json2(b'{"padding":[' + b'0,'*32767 + b'0]}')

    def test_strings_bounded_by_decoded_utf8_bytes(self):
        for raw in (b'"' + b'a'*257 + b'"', json.dumps('\U0001F600'*65).encode()):
            with self.assertRaisesRegex(c.ContractViolation2, 'v2_json_string_limit'):
                j.bounded_json2(raw)

    def test_object_array_and_expression_limits(self):
        for doc in ({'nftables': [{}]*129}, {'expr': [0]*65}):
            with self.assertRaisesRegex(c.ContractViolation2, 'v2_json_array_limit'):
                j.bounded_json2(json.dumps(doc).encode())

    def test_enormous_integer_tokens_are_not_converted(self):
        with self.assertRaisesRegex(c.ContractViolation2, 'v2_json_integer_invalid'):
            j.bounded_json2(b'9'*10000)


class NativeFixtureTests(unittest.TestCase):
    def setUp(self):
        self.f = ReadbackFixture2.create()
        self.root = Path(__file__).parent / 'fixtures/kernel_6_8_nft_1_0_9/native'
        self.raw = (self.root / 'nft_ruleset_final.json').read_bytes()
        self.decoded = r.decode_native2(self.raw, self.f.expected.profile, self.f.context)

    def test_original_bytes_metadata_grouping_and_ct_format(self):
        manifest = json.loads((self.root / 'provenance.json').read_text())
        self.assertEqual(hashlib.sha256(self.raw).hexdigest(), manifest['files']['nft_ruleset_final.json']['sha256'])
        self.assertEqual(self.decoded.metainfo, ('1.0.9', 'Old Doc Yak #3', 1))
        self.assertEqual(len(self.decoded.objects), 14)
        self.assertEqual([type(o).__name__ for o in self.decoded.objects[:3]],
                         ['NativeTable2', 'NativeChain2', 'NativeRule2'])
        nodes = [n for o in self.decoded.objects if type(o) is r.NativeRule2 for n in o.expressions
                 if type(n) is r.Match2 and type(n.left) is r.Ct2]
        self.assertEqual(len(nodes), 6)
        self.assertTrue(all(n.op == 'in' for n in nodes))
        self.assertEqual({n.right for n in nodes}, {'new', 'established'})

    def test_full_native_graph_scoped_handles_and_rule_order(self):
        graph = r.normalize_rules2(self.decoded)
        self.assertEqual([t.identity.name for t in graph.tables], ['tc_ct_lab', 'tc_strict_lab'])
        self.assertEqual([t.chains[0].identity.handle for t in graph.tables], [1, 1])
        self.assertEqual([r.identity.handle for r in graph.tables[1].chains[0].rules], list(range(2, 9)))
        self.assertEqual(graph.tables[1].identity.handle, graph.tables[1].chains[0].rules[-1].identity.handle)

    def test_actual_counters_nonterminal_observers_and_arp_without_counter(self):
        graph = r.normalize_rules2(self.decoded)
        ct, strict = [t.chains[0].rules for t in graph.tables]
        self.assertEqual([(x.counter.packets, x.counter.bytes) for x in ct], [(3, 180), (15, 1014), (12, 3530)])
        self.assertTrue(all(type(x.expressions[-1]) is r.AnonymousCounter2 for x in ct))
        self.assertTrue(all(x.counter is None for x in strict[:2]))
        self.assertEqual([(x.counter.packets, x.counter.bytes) for x in strict[2:]],
                         [(1, 60), (5, 338), (6, 1931), (6, 428), (3, 176)])

    def test_lab_policy_cannot_be_canonical_recipe_or_ownership(self):
        graph = r.normalize_rules2(self.decoded)
        with self.assertRaisesRegex(c.ContractViolation2, 'v2_recipe_mismatch'):
            r.validate_recipe2(graph, self.f.expected, self.f.binding, self.f.expected.intent)
        self.assertFalse(graph.ownership_proven)
        self.assertFalse(graph.physical_probe_permitted)


class IsolationTests(unittest.TestCase):
    def test_new_modules_have_no_os_io_legacy_writer_imports(self):
        for module in (j, r):
            tree = ast.parse(Path(module.__file__).read_text())
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    self.assertFalse({x.name.split('.')[0] for x in node.names} & {'os', 'socket', 'subprocess', 'docker', 'django'})
                if isinstance(node, ast.ImportFrom):
                    self.assertNotIn((node.module or '').split('.')[0], {'os', 'socket', 'subprocess', 'sandbox', 'django', 'trusted_checker_physical'})
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                    self.assertNotIn(node.func.id, ('open', 'eval', 'exec', '__import__'))

    def test_fresh_import_has_no_network_process_or_legacy_contracts(self):
        code = '''import socket, subprocess, os
def forbidden(*a, **k): raise AssertionError("physical operation")
socket.socket=forbidden
subprocess.Popen=forbidden
if hasattr(os,"setns"): os.setns=forbidden
import trusted_checker_network.native_v2_readback
import sys
assert not any(n in sys.modules for n in ("docker","django","trusted_checker_network.counter_contracts","trusted_checker_physical.collector"))
'''
        subprocess.run([sys.executable, '-c', code], check=True, capture_output=True, timeout=10)

    def test_physical_gate_does_not_accept_structural_result(self):
        from trusted_checker_physical.collector import PhysicalProbeGate
        from trusted_checker_runtime.profiles import Denied
        value = ReadbackFixture2.create().validate()
        with self.assertRaisesRegex(Denied, 'physical_network_boundary_not_accepted'):
            PhysicalProbeGate.permit(value)
