"""Local contract audit; native captures are read without kernel execution.

Observed numeric pairs come from the task summary. All surrounding canonical
readbacks, mutations, approvals, signatures and topology are synthetic fixtures.
"""
from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path
import unittest

from trusted_checker_network.counter_readback import parse_json, validate_readback
from trusted_checker_network.tests.counter_support import CounterLab
from trusted_checker_physical.collector import PhysicalProbeGate
from trusted_checker_runtime.profiles import Denied


FACTS_PATH = Path(__file__).parent / 'fixtures/kernel_6_8_nft_1_0_9/observations.json'


class KernelCompatibilityTests(unittest.TestCase):
    def setUp(self):
        self.lab = CounterLab()
        self.addCleanup(self.lab.close)
        self.facts = json.loads(FACTS_PATH.read_text())

    def unknown(self, change, reason):
        report = self.lab.run(change)
        self.assertEqual((report.result, report.reason), ('unknown', reason))
        self.assertTrue(self.lab.verifier.circuit)
        self.assertFalse(report.physical_probe_permitted)
        return report

    def rule_change(self, change, purpose='terminal_drop', reason='counter_readback_invalid'):
        spec = next(s for s in self.lab.recipe.counters if s.purpose == purpose)
        return self.unknown(
            lambda f: self.lab.change_read(f, 0, 'before',
                lambda raw: change(raw['nftables'][spec.object_index]['rule'], spec)), reason)

    def test_summary_preserves_actual_pairs_without_claiming_native_capture(self):
        self.assertEqual(
            [(r['label'], r['packets'], r['bytes']) for r in self.facts['counters']],
            [('Forward NEW accept', 1, 60), ('Forward ESTABLISHED accept', 5, 338),
             ('Reverse ESTABLISHED accept', 6, 1931), ('Forward drop', 6, 428),
             ('Reverse drop', 3, 176)])
        self.assertIs(self.facts['native_json_available'], True)
        self.assertIs(self.facts['before_snapshot_available'], False)
        self.assertEqual(self.facts['counter_basis'], 'cumulative_final_snapshot_not_probe_deltas')

    def test_observed_numbers_parse_in_explicitly_synthetic_canonical_counter(self):
        spec = self.lab.recipe.counters[0]
        for row in self.facts['counters']:
            with self.subTest(label=row['label']):
                observation = self.lab.readback(
                    {spec.identity: (row['packets'], row['bytes'])}, self.lab.clock())
                value = next(v for v in validate_readback(observation, self.lab.approval)
                             if v.identity == spec.identity)
                self.assertEqual((value.packets, value.bytes), (row['packets'], row['bytes']))

    def test_summary_is_not_a_native_readback_or_measurement(self):
        # Preserve the summary as-is: do not invent an nft object list for it.
        observation = self.lab.readback({}, self.lab.clock())
        with self.assertRaisesRegex(Denied, 'counter_readback_invalid'):
            validate_readback(replace(observation, json=FACTS_PATH.read_text()), self.lab.approval)
        self.unknown(lambda _: self.facts, 'counter_evidence_invalid')

    def test_single_snapshot_cannot_stand_in_for_signed_measurement(self):
        self.unknown(lambda f: f.samples[0].after, 'counter_evidence_invalid')

    def test_cumulative_baselines_can_be_nonzero_when_every_delta_is_proven(self):
        # Numeric offsets only. There is no asserted lab-rule/canonical-rule mapping.
        def offset(fixture):
            for index in range(len(fixture.samples)):
                for side in ('before', 'after'):
                    def add_baselines(raw):
                        for number, spec in enumerate(self.lab.recipe.counters):
                            row = self.facts['counters'][number % len(self.facts['counters'])]
                            counter = raw['nftables'][spec.object_index]['rule']['expr'][spec.expression_index]['counter']
                            counter['packets'] += row['packets']
                            counter['bytes'] += row['bytes']
                    fixture = self.lab.change_read(fixture, index, side, add_baselines)
            return fixture
        report = self.lab.run(offset)
        self.assertEqual(report.result, 'verified')
        self.assertEqual(report.samples[0].before[0].packets, 1)
        self.assertEqual(report.samples[0].before[0].bytes, 60)
        self.assertFalse(report.physical_probe_permitted)

    def test_cumulative_values_cannot_be_substituted_for_one_probe_delta(self):
        spec = next(s for s in self.lab.recipe.counters if s.purpose == 'ingress' and s.probe_index == 0)
        for row in self.facts['counters']:
            with self.subTest(label=row['label']):
                verifier = self.lab.new_verifier()
                verifier.set_enabled(True)
                verifier.begin(self.lab.clock() + 2)
                current = self.lab.fixture()
                def cumulative(raw):
                    raw['nftables'][spec.object_index]['rule']['expr'][spec.expression_index]['counter'] = {
                        'packets': row['packets'], 'bytes': row['bytes']}
                changed = self.lab.change_read(current, 0, 'after', cumulative)
                report = verifier.finish(changed)
                self.assertEqual((report.result, report.reason), ('unknown', 'counter_delta_unexplained'))
                self.assertFalse(report.physical_probe_permitted)

    def test_numeric_priority_decoding_does_not_authorize_other_priorities(self):
        observation = self.lab.readback({}, self.lab.clock())
        for priority in (-200, 10):
            with self.subTest(priority=priority):
                raw = json.loads(observation.json)
                raw['nftables'][1]['chain']['prio'] = priority
                encoded = json.dumps(raw)
                self.assertEqual(parse_json(encoded)['nftables'][1]['chain']['prio'], priority)
                with self.assertRaisesRegex(Denied, 'counter_readback_invalid'):
                    validate_readback(replace(observation, json=encoded), self.lab.approval)

    def test_canonical_integer_priorities_are_supported(self):
        observation = self.lab.readback({}, self.lab.clock())
        priorities = [item['chain']['prio'] for item in json.loads(observation.json)['nftables'] if 'chain' in item]
        self.assertEqual(priorities, [0, 0, 0, 0, -310, -310, -310])
        self.assertEqual(len(validate_readback(observation, self.lab.approval)), 49)

    def test_textual_nft_output_is_not_input(self):
        observation = self.lab.readback({}, self.lab.clock())
        with self.assertRaisesRegex(Denied, 'counter_readback_invalid'):
            validate_readback(replace(observation, json='table bridge tc_strict_lab { }'), self.lab.approval)

    def test_ct_state_in_decodes_but_is_not_silently_equated_to_canonical_match(self):
        observation = self.lab.readback({}, self.lab.clock())
        raw = json.loads(observation.json)
        matches = [expr['match'] for obj in raw['nftables'] for expr in obj.get('rule', {}).get('expr', [])
                   if expr.get('match', {}).get('left') == {'ct': {'key': 'state'}}]
        self.assertEqual(len(matches), 2)
        for match in matches:
            self.assertEqual((match['op'], match['right']), ('==', 'established'))
            match['op'] = 'in'
        encoded = json.dumps(raw)
        self.assertEqual(parse_json(encoded), raw)
        with self.assertRaisesRegex(Denied, 'counter_readback_invalid'):
            validate_readback(replace(observation, json=encoded), self.lab.approval)

    def test_no_verdict_ingress_and_separate_counter_verdict_elements(self):
        raw = json.loads(self.lab.readback({}, self.lab.clock()).json)
        for spec in self.lab.recipe.counters:
            expr = raw['nftables'][spec.object_index]['rule']['expr']
            self.assertEqual(set(expr[spec.expression_index]), {'counter'})
            tail = expr[spec.expression_index + 1:]
            self.assertEqual(tail, [] if spec.purpose == 'ingress' else
                             [{'accept': None}] if spec.purpose == 'allow' else [{'drop': None}])
        self.assertEqual(self.lab.run().result, 'verified')

    def test_removed_rule_is_unknown(self):
        spec = self.lab.recipe.counters[0]
        self.unknown(lambda f: self.lab.change_read(f, 0, 'before',
            lambda raw: raw['nftables'].pop(spec.object_index)), 'counter_readback_invalid')

    def test_reordered_matches_are_unknown_even_if_logically_similar(self):
        def reorder(rule, spec):
            rule['expr'][0], rule['expr'][1] = rule['expr'][1], rule['expr'][0]
        self.rule_change(reorder)

    def test_modified_expression_is_unknown(self):
        self.rule_change(lambda rule, spec: rule['expr'][0]['match'].__setitem__('right', 999))

    def test_changed_priority_is_terminal_unknown(self):
        self.unknown(lambda f: self.lab.change_read(f, 0, 'before',
            lambda raw: raw['nftables'][1]['chain'].__setitem__('prio', -200)), 'counter_readback_invalid')

    def test_lab_policy_accept_cannot_replace_bridge_default_drop(self):
        self.unknown(lambda f: self.lab.change_read(f, 0, 'before',
            lambda raw: raw['nftables'][1]['chain'].__setitem__('policy', self.facts['lab']['policy'])),
            'counter_readback_invalid')

    def test_changed_interface_is_unknown(self):
        def change(rule, spec):
            match = next(expr['match'] for expr in rule['expr']
                         if expr.get('match', {}).get('left') == {'meta': {'key': 'iifname'}})
            match['right'] = self.facts['lab']['bridge_ports'][0]
        self.rule_change(change, purpose='allow')

    def test_added_verdict_to_nonterminal_ingress_is_unknown(self):
        self.rule_change(lambda rule, spec: rule['expr'].append({'drop': None}), purpose='ingress')

    def test_metadata_is_not_ignored_by_counter_reader(self):
        # Synthetic metadata marker only, not an invented nft metainfo capture.
        self.unknown(lambda f: self.lab.change_read(f, 0, 'before',
            lambda raw: raw['nftables'].insert(0, {'metainfo': {}})), 'counter_readback_invalid')

    def test_regrouping_object_list_is_not_silently_normalized(self):
        def regroup(raw):
            raw['nftables'].sort(key=lambda item: next(iter(item.values()))['family'])
        self.unknown(lambda f: self.lab.change_read(f, 0, 'before', regroup), 'counter_readback_invalid')

    def test_decreased_packets_or_bytes_are_unknown(self):
        spec = next(s for s in self.lab.recipe.counters if s.purpose == 'ingress' and s.probe_index == 0)
        for field in ('packets', 'bytes'):
            with self.subTest(field=field):
                verifier = self.lab.new_verifier()
                verifier.set_enabled(True)
                verifier.begin(self.lab.clock() + 2)
                fixture = self.lab.fixture()
                def reset(raw):
                    raw['nftables'][spec.object_index]['rule']['expr'][spec.expression_index]['counter'][field] = 0
                changed = self.lab.change_read(fixture, 1, 'after', reset)
                self.assertEqual(verifier.finish(changed).reason, 'counter_reset_or_wrap')

    def test_unexpected_drop_delta_is_unknown(self):
        def extra(fixture):
            spec = next(s for s in self.lab.recipe.counters if s.purpose == 'terminal_drop' and s.probe_index == 1)
            def increment(raw):
                raw['nftables'][spec.object_index]['rule']['expr'][spec.expression_index]['counter']['packets'] += 1
            return self.lab.change_read(fixture, 1, 'after', increment)
        self.unknown(extra, 'counter_delta_unexplained')

    def test_background_arp_traffic_is_unknown(self):
        spec = next(s for s in self.lab.recipe.counters if s.purpose == 'allow' and
                    any(e.get('match', {}).get('left', {}).get('payload', {}).get('protocol') == 'arp'
                        for e in self.lab.commands[s.object_index]['add']['rule']['expr']))
        row = self.facts['counters'][3]
        def background(raw):
            raw['nftables'][spec.object_index]['rule']['expr'][spec.expression_index]['counter'] = {
                'packets': row['packets'], 'bytes': row['bytes']}
        self.unknown(lambda f: self.lab.change_read(f, 0, 'after', background), 'counter_delta_unexplained')

    def test_traffic_between_sample_windows_is_unknown(self):
        spec = next(s for s in self.lab.recipe.counters if s.purpose == 'fallback_drop')
        def gap(fixture):
            # Shift all later rows together: per-sample deltas stay correct,
            # but continuity from sample zero's final to sample one's baseline fails.
            for index in range(1, len(fixture.samples)):
                for side in ('before', 'after'):
                    def increment(raw):
                        counter = raw['nftables'][spec.object_index]['rule']['expr'][spec.expression_index]['counter']
                        counter['packets'] += 1
                        counter['bytes'] += self.facts['counters'][0]['bytes']
                    fixture = self.lab.change_read(fixture, index, side, increment)
            return fixture
        self.unknown(gap, 'counter_delta_unexplained')

    def test_lab_bridge_topology_cannot_replace_approved_binding(self):
        def topology(fixture):
            observation = fixture.topology_after.payload
            paths = list(observation.paths)
            interfaces = list(paths[0].interfaces)
            bridge = list(interfaces[1])
            bridge[0] = self.facts['lab']['bridge']
            interfaces[1] = tuple(bridge)
            paths[0] = replace(paths[0], interfaces=tuple(interfaces))
            return replace(fixture, topology_after=self.lab.sign(
                replace(observation, paths=tuple(paths)), 'topology'))
        self.unknown(topology, 'counter_topology_unproven')

    def test_offline_success_cannot_open_physical_gate(self):
        report = self.lab.run()
        self.assertEqual(report.result, 'verified')
        with self.assertRaisesRegex(Denied, 'physical_network_boundary_not_accepted'):
            PhysicalProbeGate.permit(report)


class LinkFormatBoundaryTests(unittest.TestCase):
    """Mock ip-port checks; native ip capture contains only the bridge."""

    def test_string_master_is_not_current_inventory_integer_contract(self):
        from trusted_checker_physical.tests.support import Lab
        lab = Lab()
        self.addCleanup(lab.close)
        lab.links = deepcopy(lab.links)
        for link in lab.links:
            if 'master' in link:
                link['master'] = lab.binding.bridge_name
        with self.assertRaisesRegex(Denied, 'physical_veth_identity_changed'):
            lab.inventory.observe(lab.budget())
        self.assertEqual(lab.batches, [])
