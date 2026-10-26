"""Original native final snapshots: format tests only, never per-probe evidence."""
from collections import Counter
from copy import deepcopy
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import unittest

from trusted_checker_network.counter_inventory import check_topology
from trusted_checker_network.counter_readback import parse_json, validate_readback
from trusted_checker_network.tests.counter_support import CounterLab
from trusted_checker_physical.io import json_output
from trusted_checker_runtime.profiles import Denied


ROOT = Path(__file__).parent / 'fixtures/kernel_6_8_nft_1_0_9'
NATIVE = ROOT / 'native'


class NativeFormatTests(unittest.TestCase):
    def setUp(self):
        self.raw_nft = (NATIVE / 'nft_ruleset_final.json').read_text()
        self.nft = parse_json(self.raw_nft)

    def rules(self, table):
        return [item['rule'] for item in self.nft['nftables']
                if 'rule' in item and item['rule']['table'] == table]

    def test_original_bytes_and_exact_extraction_from_terminal_log(self):
        provenance = json.loads((NATIVE / 'provenance.json').read_text())
        self.assertEqual(provenance['archive_sha256'],
                         '2437f0c35a0864885a975b77ce34e3bc072cf37cb41b4ef9d22271ba6aa45a7b')
        self.assertIs(provenance['before_after_json_available'], False)
        lines = (NATIVE / 'raw_terminal_capture.md').read_bytes().splitlines()
        for name, facts in provenance['files'].items():
            with self.subTest(name=name):
                raw = (NATIVE / name).read_bytes()
                self.assertEqual(len(raw), facts['bytes'])
                self.assertEqual(hashlib.sha256(raw).hexdigest(), facts['sha256'])
                if name.endswith('.json'):
                    self.assertIn(raw.rstrip(b'\n'), lines)

    def test_complete_native_nft_json_decodes_with_original_metadata(self):
        self.assertEqual(len(self.nft['nftables']), 15)
        self.assertEqual(self.nft['nftables'][0], {'metainfo': {
            'version': '1.0.9', 'release_name': 'Old Doc Yak #3', 'json_schema_version': 1}})
        self.assertEqual(json_output(self.raw_nft.encode()), self.nft)

    def test_actual_signed_integer_priorities(self):
        chains = {item['chain']['table']: item['chain'] for item in self.nft['nftables'] if 'chain' in item}
        self.assertEqual({name: chain['prio'] for name, chain in chains.items()},
                         {'tc_ct_lab': -200, 'tc_strict_lab': 10})
        self.assertTrue(all(type(chain['prio']) is int and chain['policy'] == 'accept'
                            for chain in chains.values()))

    def test_actual_ct_state_in_uses_scalar_new_and_established(self):
        matches = [expr['match'] for table in ('tc_ct_lab', 'tc_strict_lab') for rule in self.rules(table)
                   for expr in rule['expr'] if expr.get('match', {}).get('left') == {'ct': {'key': 'state'}}]
        self.assertEqual(Counter((m['op'], m['right']) for m in matches),
                         Counter({('in', 'new'): 2, ('in', 'established'): 4}))

    def test_actual_strict_counters_equal_task_values_with_scoped_handles(self):
        rules = self.rules('tc_strict_lab')
        rows = [(rule['handle'], expr['counter']['packets'], expr['counter']['bytes'])
                for rule in rules for expr in rule['expr'] if 'counter' in expr]
        self.assertEqual(rows, [(4, 1, 60), (5, 5, 338), (6, 6, 1931), (7, 6, 428), (8, 3, 176)])
        summary = json.loads((ROOT / 'observations.json').read_text())
        self.assertEqual([(p, b) for _, p, b in rows],
                         [(row['packets'], row['bytes']) for row in summary['counters']])

    def test_actual_ct_observer_counters_and_nonterminal_rules(self):
        rules = self.rules('tc_ct_lab')
        self.assertEqual([(rule['handle'], rule['expr'][-1]['counter']) for rule in rules],
                         [(2, {'packets': 3, 'bytes': 180}), (3, {'packets': 15, 'bytes': 1014}),
                          (4, {'packets': 12, 'bytes': 3530})])
        self.assertFalse(any('accept' in expr or 'drop' in expr for rule in rules for expr in rule['expr']))

    def test_actual_counter_before_separate_verdict_and_uncounted_arp(self):
        rules = self.rules('tc_strict_lab')
        self.assertEqual([rule['expr'][-1] for rule in rules],
                         [{'accept': None}] * 5 + [{'drop': None}] * 2)
        self.assertTrue(all('counter' not in expr for rule in rules[:2] for expr in rule['expr']))
        self.assertTrue(all(set(rule['expr'][-2]) == {'counter'} for rule in rules[2:]))

    def test_native_handles_repeat_across_tables_and_object_kinds(self):
        objects = [(kind, obj['family'], obj.get('table', obj.get('name')), obj['handle'])
                   for item in self.nft['nftables'] for kind, obj in item.items() if kind != 'metainfo']
        handles = [row[-1] for row in objects]
        self.assertLess(len(set(handles)), len(handles))
        self.assertEqual(len(set(objects)), len(objects))
        self.assertIn(('table', 'bridge', 'tc_strict_lab', 8), objects)
        self.assertIn(('rule', 'bridge', 'tc_strict_lab', 8), objects)
        self.assertIn(('chain', 'bridge', 'tc_ct_lab', 1), objects)
        self.assertIn(('chain', 'bridge', 'tc_strict_lab', 1), objects)

    def test_actual_bridge_ports_use_name_master_and_link_string(self):
        links = json_output((NATIVE / 'bridge_links_final.json').read_bytes())
        self.assertEqual([(p['ifindex'], p['ifname'], p['master'], p['link']) for p in links],
                         [(7, 'tc-br-r-host', 'tc-br0', 'if6'), (9, 'tc-br-t-host', 'tc-br0', 'if8')])
        self.assertTrue(all(p['state'] == 'forwarding' and 'link_index' not in p for p in links))

    def test_actual_ip_dump_is_bridge_only_and_contains_float_timers(self):
        links = json_output((NATIVE / 'bridge_tc_br0_final.json').read_bytes())
        self.assertEqual(len(links), 1)
        bridge = links[0]
        self.assertEqual((bridge['ifindex'], bridge['ifname'], bridge['address']),
                         (5, 'tc-br0', 'da:86:66:ca:86:59'))
        self.assertEqual(bridge['linkinfo']['info_kind'], 'bridge')
        info = bridge['linkinfo']['info_data']
        self.assertEqual(info['gc_timer'], 178.16)
        self.assertIs(type(info['gc_timer']), float)
        self.assertEqual([info[key] for key in ('vlan_filtering', 'nf_call_iptables',
                                               'nf_call_ip6tables', 'nf_call_arptables')], [0, 0, 0, 0])

    def test_terminal_log_records_extra_namespaces_and_host_default_routes(self):
        log = (NATIVE / 'raw_terminal_capture.md').read_text()
        for fact in ('tc-br-target (id: 3)', 'tc-br-runner (id: 2)',
                     'tc-target (id: 1)', 'tc-runner (id: 0)'):
            self.assertIn(fact, log)
        self.assertRegex(log, r'default via [0-9.]+ dev eth0')
        self.assertRegex(log, r'default via fe80::[0-9a-f:]+ dev eth0')


class NativeContractBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.lab = CounterLab()
        self.addCleanup(self.lab.close)
        self.nft = parse_json((NATIVE / 'nft_ruleset_final.json').read_text())

    def test_final_lab_dump_cannot_be_a_canonical_readback_or_measurement(self):
        observation = self.lab.readback({}, self.lab.clock())
        with self.assertRaisesRegex(Denied, 'counter_readback_invalid'):
            validate_readback(replace(observation, json=(NATIVE / 'nft_ruleset_final.json').read_text()),
                              self.lab.approval)
        report = self.lab.run(lambda _: self.nft)
        self.assertEqual((report.result, report.reason), ('unknown', 'counter_evidence_invalid'))
        self.assertFalse(report.physical_probe_permitted)

    def test_actual_metadata_is_not_silently_stripped_from_canonical_dump(self):
        observation = self.lab.readback({}, self.lab.clock())
        raw = json.loads(observation.json)
        raw['nftables'].insert(0, deepcopy(self.nft['nftables'][0]))
        with self.assertRaisesRegex(Denied, 'counter_readback_invalid'):
            validate_readback(replace(observation, json=json.dumps(raw)), self.lab.approval)

    def test_actual_established_expression_is_not_accepted_as_canonical_equality(self):
        native_match = next(expr for obj in self.nft['nftables'] for expr in obj.get('rule', {}).get('expr', [])
                            if expr.get('match', {}).get('left') == {'ct': {'key': 'state'}}
                            and expr['match']['right'] == 'established')
        observation = self.lab.readback({}, self.lab.clock())
        raw = json.loads(observation.json)
        for obj in raw['nftables']:
            for index, expr in enumerate(obj.get('rule', {}).get('expr', [])):
                if expr.get('match', {}).get('left') == {'ct': {'key': 'state'}}:
                    obj['rule']['expr'][index] = deepcopy(native_match)
        with self.assertRaisesRegex(Denied, 'counter_readback_invalid'):
            validate_readback(replace(observation, json=json.dumps(raw)), self.lab.approval)

    def test_global_handle_uniqueness_assumption_rejects_native_scoped_reuse(self):
        # Test the assumption only: never import laboratory handles as ownership.
        handles = list(self.lab.approval.object_handles)
        table_handle = next(item['table']['handle'] for item in self.nft['nftables']
                            if item.get('table', {}).get('name') == 'tc_strict_lab')
        rule_handle = next(item['rule']['handle'] for item in self.nft['nftables']
                           if item.get('rule', {}).get('table') == 'tc_strict_lab'
                           and item['rule']['handle'] == table_handle)
        handles[:2] = [table_handle, rule_handle]
        with self.assertRaisesRegex(Denied, 'counter_handle_binding_invalid'):
            replace(self.lab.approval, object_handles=tuple(handles))

    def test_raw_link_dumps_cannot_substitute_for_complete_typed_topology(self):
        for name in ('bridge_links_final.json', 'bridge_tc_br0_final.json'):
            with self.subTest(name=name), self.assertRaisesRegex(Denied, 'counter_topology_required'):
                check_topology(json_output((NATIVE / name).read_bytes()), self.lab.approval)
