"""Offline topology registry, stages and joins; every full positive is synthetic."""
import ast
from copy import deepcopy
from dataclasses import FrozenInstanceError, replace
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

from trusted_checker_network import native_v2_contracts as c
from trusted_checker_network import native_v2_topology as t
from trusted_checker_network import native_v2_topology_schema as s
from trusted_checker_network import native_v2_topology_json as j
from .native_v2_support import uid, hd
from .native_v2_topology_support import TopologyFixture2, link


class _FixtureCase(unittest.TestCase):
    def setUp(self):
        self.f=TopologyFixture2.create()
        self.baseline=self.f.complete()
        self.assertEqual(self.baseline.stage,'topology_complete')

    def changed(self,change):
        rows=deepcopy(self.f.rows); change(rows); return rows

    def invalid(self,change,reason=None):
        with self.assertRaises(c.ContractViolation2) as caught:
            self.f.complete(self.changed(change))
        if reason: self.assertEqual(str(caught.exception),reason)

    def unproven(self,change,reason):
        e=self.f.complete(self.changed(change))
        self.assertEqual(e.stage,'topology_unproven')
        self.assertIn(reason,e.uncertainty_reasons)
        return e


class StageTests(_FixtureCase):
    def test_positive_complete_has_four_distinct_stages(self):
        docs,plan=self.f.bundle(); decoded=t.decode_topology_documents2(docs,self.f.profile,plan)
        n=t.normalize_topology2(decoded,plan); e=t.complete_topology2(n)
        self.assertEqual(decoded[0].stage,'source_decoded')
        self.assertEqual(n.stage,'topology_normalized'); self.assertEqual(e.stage,'topology_complete')
        self.assertEqual(len(e.joins),4)

    def test_all_records_immutable_and_no_permit(self):
        n=self.baseline.normalized.namespaces[0]
        for value in (self.baseline,n,*n.links,*n.addresses,*n.ports,*n.vlans,*n.fdb,*n.routes,*n.rules,*n.attachments):
            self.assertIs(value.physical_probe_permitted,False)
            self.assertIs(value.ownership_proven,False)
            with self.assertRaises(FrozenInstanceError): value.physical_probe_permitted=True
        with self.assertRaises(c.ContractViolation2): replace(self.baseline,physical_probe_permitted=True)
        with self.assertRaises(TypeError): replace(self.baseline,stage='topology_complete')

    def test_complete_is_never_isolation_or_policy_measurement(self):
        self.assertFalse(self.baseline.isolation_verified)
        self.assertFalse(self.baseline.management_policy_verified)
        self.assertFalse(self.baseline.measurement_verified)
        self.assertEqual(self.baseline.provenance_authentication,'unproven_offline_references')
        self.assertEqual(self.baseline.continuity,'snapshots_only_not_atomic')

    def test_unobserved_attachments_do_not_mean_no_attachments(self):
        for n in self.baseline.normalized.namespaces:
            self.assertEqual(len(n.attachments),7)
            self.assertTrue(all(a.status=='unobserved' for a in n.attachments))
            with self.assertRaises(c.ContractViolation2): replace(n.attachments[0],status='absent')

    def test_management_nic_and_provider_defaults_visible(self):
        n=self.baseline.normalized.namespaces[0]
        self.assertIn('mgmt0',[l.ifname for l in n.links])
        self.assertEqual([r.attributes.get('gateway') for r in n.routes],['192.0.2.1','fe80::1'])
        self.assertEqual([r.attributes.get('dst') for r in n.routes],['default','default'])

    def test_three_namespace_identities_have_local_index_reuse(self):
        ns=self.baseline.normalized.namespaces
        self.assertEqual(len({n.identity.key for n in ns}),3)
        self.assertEqual([n.links[0].reference.ifindex for n in ns],[1,1,1])

    def test_missing_document_is_not_empty_array(self):
        docs,plan=self.f.bundle(); sources=t.decode_topology_documents2(docs[:-1],self.f.profile,plan)
        e=t.complete_topology2(t.normalize_topology2(sources,plan))
        self.assertIn('source_coverage_missing',e.uncertainty_reasons)
        self.assertNotIn('rule6',[d.descriptor.source for d in e.normalized.namespaces[-1].sources])

    def test_explicit_empty_source_is_preserved(self):
        target=self.baseline.normalized.namespaces[-1]
        source=next(d for d in target.sources if d.descriptor.source=='bridge_link')
        self.assertEqual(source.rows,())
        self.assertEqual(source.raw_text,'[]')

    def test_missing_role_cannot_be_complete(self):
        docs,plan=self.f.bundle(); key=self.f.namespaces[-1].key
        plan=replace(plan,namespaces=plan.namespaces[:-1],captures=tuple(d for d in plan.captures if d.namespace!=key),
                     peer_witnesses=(),table_mappings=tuple(v for v in plan.table_mappings if v.namespace!=key))
        docs=tuple((raw,d) for raw,d in docs if d.namespace!=key)
        e=t.complete_topology2(t.normalize_topology2(t.decode_topology_documents2(docs,self.f.profile,plan),plan))
        self.assertIn('namespace_coverage_missing',e.uncertainty_reasons)

    def test_digest_deterministic_and_domain_bound(self):
        self.assertEqual(self.baseline.digest,self.f.complete().digest)
        self.assertEqual(self.f.profile.schema_registry_digest,s.REGISTRY_DIGEST)
        self.assertNotEqual(self.f.profile.digest,s.REGISTRY_DIGEST)

    def test_gate_stays_closed(self):
        from trusted_checker_physical.collector import PhysicalProbeGate
        from trusted_checker_runtime.profiles import Denied
        with self.assertRaisesRegex(Denied,'physical_network_boundary_not_accepted'):
            PhysicalProbeGate.permit(self.baseline)

    def test_resolved_references_pin_exact_namespace_link_and_table(self):
        refs=self.baseline.resolved_references
        self.assertTrue(any(r.relation=='address_link' for r in refs))
        self.assertTrue(any(r.relation=='vlan_link' for r in refs))
        self.assertTrue(any(r.relation=='fdb_dev' for r in refs))
        table=next(r for r in refs if r.relation=='route_table')
        self.assertEqual((table.target.native_token,table.target.number),('main',254))
        route=next(r for r in refs if r.relation=='route_dev')
        self.assertEqual(route.target,t.LinkReference2(self.f.namespaces[0].key,2))
        self.assertEqual(route.source_capture_digest,next(d.descriptor.digest for d in self.baseline.normalized.sources if d.descriptor.namespace==self.f.namespaces[0].key and d.descriptor.source=='route4'))

    def test_resolved_references_cannot_be_constructor_overrides(self):
        with self.assertRaises(TypeError): replace(self.baseline,resolved_references=())


class ParserTests(_FixtureCase):
    def test_byte_cap_and_exact_input_type(self):
        for raw in (b'',b' '*1048577,'[]',bytearray(b'[]')):
            with self.assertRaises(c.ContractViolation2): j.bounded_topology_json2(raw)
        self.assertEqual(j.bounded_topology_json2(b'[]'+b' '*1048574),[])

    def test_duplicate_keys_and_escaped_alias(self):
        for raw in (b'{"a":1,"a":2}',b'{"a":1,"\\u0061":2}'):
            with self.assertRaisesRegex(c.ContractViolation2,'duplicate_key'): j.bounded_topology_json2(raw)

    def test_encoding_bom_and_bad_utf8(self):
        for raw in (b'\xef\xbb\xbf[]',b'\xff',b'"\x01"',b'"\\ud800"',b'"\\udc00"'):
            with self.assertRaises(c.ContractViolation2): j.bounded_topology_json2(raw)
        self.assertEqual(j.bounded_topology_json2(b'"\\ud83d\\ude00"'),'😀')

    def test_depth_boundary(self):
        self.assertIsNotNone(j.bounded_topology_json2(b'['*31+b'0'+b']'*31))
        with self.assertRaisesRegex(c.ContractViolation2,'depth_limit'): j.bounded_topology_json2(b'['*32+b'0'+b']'*32)

    def test_string_utf8_bound(self):
        self.assertEqual(len(j.bounded_topology_json2(('"'+'я'*256+'"').encode())),256)
        with self.assertRaisesRegex(c.ContractViolation2,'string_limit'): j.bounded_topology_json2(('"'+'я'*257+'"').encode())

    def test_row_and_nested_array_limits(self):
        for raw in (json.dumps([0]*1025).encode(),json.dumps({'a':[0]*1025}).encode()):
            with self.assertRaisesRegex(c.ContractViolation2,'array_limit'): j.bounded_topology_json2(raw)

    def test_node_limit_before_appending(self):
        raw=json.dumps([[0]*1024 for _ in range(64)]).encode()
        with self.assertRaisesRegex(c.ContractViolation2,'nodes_limit'): j.bounded_topology_json2(raw)

    def test_integer_range_bool_separation(self):
        self.assertEqual(j.bounded_topology_json2(b'[true,false,0]'),[True,False,0])
        for raw in (b'9223372036854775808',b'999999999999999999999',b'01'):
            with self.assertRaises(c.ContractViolation2): j.bounded_topology_json2(raw)
        for value in (True,False,1.0):
            self.invalid(lambda d:d['host']['link'][0].__setitem__('ifindex',value))

    def test_exact_decimal_token_and_scale_preserved(self):
        a,b=j.bounded_topology_json2(b'[178.16,0.00]')
        self.assertEqual((a.token,a.millionths),('178.16',178160000))
        self.assertEqual(b.token,'0.00'); self.assertEqual(b.millionths,0)
        self.assertNotEqual(b,j.ExactDecimal2('0.0'))

    def test_decimal_bounds_no_exponent_or_nonfinite(self):
        for raw in (b'1e2',b'1.0e2',b'NaN',b'Infinity',b'-1.0',b'0.0000001',b'12345678901.0'):
            with self.assertRaises(c.ContractViolation2): j.bounded_topology_json2(raw)

    def test_decimal_only_approved_timer_paths(self):
        self.invalid(lambda d:d['host']['link'][0].__setitem__('mtu',1.5))
        self.invalid(lambda d:d['host']['route4'][0].__setitem__('metric',1.5))
        rows=self.changed(lambda d:d['host']['link'][2]['linkinfo']['info_data'].__setitem__('gc_timer',178.16))
        timer=self.f.complete(rows).normalized.namespaces[0].links[2].attributes.get('linkinfo').get('info_data').get('gc_timer')
        self.assertIs(type(timer),j.ExactDecimal2)

    def test_malformed_trailing_null_root(self):
        for raw in (b'[',b'[]x',b'[1,]',b'{"a":}',b'null',b'{}'):
            if raw in (b'null',b'{}'):
                with self.assertRaises(c.ContractViolation2): s.validate_rows2('link',j.bounded_topology_json2(raw))
            else:
                with self.assertRaises(c.ContractViolation2): j.bounded_topology_json2(raw)

    def test_batch_document_count_and_aggregate_before_parsing(self):
        docs,plan=self.f.bundle()
        with self.assertRaisesRegex(c.ContractViolation2,'documents_limit'): t.decode_topology_documents2((docs[0],)*257,self.f.profile,plan)
        raw=b' '*1048576
        with patch.object(t,'decode_topology_source2',side_effect=AssertionError('parsing started')):
            with self.assertRaisesRegex(c.ContractViolation2,'aggregate_limit'): t.decode_topology_documents2(((raw,docs[0][1]),)*17,self.f.profile,plan)


class SchemaTests(_FixtureCase):
    def test_all_nine_sources_separate_and_registry_fixed(self):
        for source in s.SOURCES:
            specs=[r for r in s.REGISTRY if r.source==source]
            self.assertTrue(specs)
            self.assertTrue(all(r.evidence_reference=='provisional_offline_specification_v1' for r in specs))
            self.assertTrue(all(r.disposition in ('identity','structural','ordered_policy','observed_volatile') for r in specs))
        with self.assertRaises(c.ContractViolation2): replace(self.f.profile,schema_registry_digest=hd('auto-widened'))
        with self.assertRaises(c.ContractViolation2): replace(self.f.profile,source_registry_digest=hd('different-caps-argv'))

    def test_unknown_field_each_source(self):
        for source in s.SOURCES:
            def mutate(d):
                if not d['host'][source]: d['host'][source]=[{}]
                d['host'][source][0]['unknown']=0
            with self.subTest(source=source): self.invalid(mutate,'v2_topology_unknown_field')

    def test_missing_mandatory_field(self):
        for source,key in (('link','ifindex'),('address','addr_info'),('bridge_link','master'),('vlan','vlans'),
                           ('fdb','mac'),('route4','table'),('route6','dst'),('rule4','src'),('rule6','priority')):
            with self.subTest(source=source): self.invalid(lambda d:d['host'][source][0].pop(key),'v2_topology_field_missing')

    def test_unknown_nested_fields(self):
        self.invalid(lambda d:d['host']['link'][2]['linkinfo']['info_data'].__setitem__('extra',0),'v2_topology_unknown_field')
        self.invalid(lambda d:d['host']['address'][0]['addr_info'][0].__setitem__('extra',0),'v2_topology_unknown_field')

    def test_ip_and_bridge_are_not_interchangeable(self):
        self.invalid(lambda d:d['host'].__setitem__('bridge_link',deepcopy(d['host']['link'])))
        self.invalid(lambda d:d['host'].__setitem__('link',deepcopy(d['host']['bridge_link'])))

    def test_master_integer_in_ip_name_in_bridge(self):
        self.invalid(lambda d:d['host']['link'][3].__setitem__('master','tcsh0'))
        self.invalid(lambda d:d['host']['bridge_link'][0].__setitem__('master',5))

    def test_unknown_link_kind_and_options(self):
        self.invalid(lambda d:d['host']['link'][3]['linkinfo'].__setitem__('info_kind','macvlan'))
        self.invalid(lambda d:d['host']['link'][3]['linkinfo'].__setitem__('info_data',{'nf_call_iptables':0}),'v2_topology_kind_unproven')

    def test_wrong_array_scalar_and_null(self):
        for value in (None,{},'UP',1): self.invalid(lambda d:d['host']['link'][0].__setitem__('flags',value))
        self.invalid(lambda d:d['host']['address'][0].__setitem__('addr_info',None))

    def test_negative_and_overflow_indices(self):
        for value in (0,-1,2**31,'1'): self.invalid(lambda d:d['host']['link'][0].__setitem__('ifindex',value))

    def test_ipv6_addresses_preserved_family_checked(self):
        a=self.baseline.normalized.namespaces[1].addresses[1]
        self.assertEqual(a.address.get('local'),'::1')
        self.invalid(lambda d:d['runner']['address'][0]['addr_info'][1].__setitem__('family','inet'),'v2_topology_family_mismatch')
        self.invalid(lambda d:d['runner']['address'][0]['addr_info'][0].__setitem__('prefixlen',33),'v2_topology_family_mismatch')

    def test_ipv6_route_family(self):
        self.invalid(lambda d:d['host']['route6'][0].__setitem__('gateway','192.0.2.1'),'v2_topology_family_mismatch')
        self.invalid(lambda d:d['host']['route4'][0].__setitem__('dst','2001:db8::/32'),'v2_topology_family_mismatch')

    def test_rpdb_selectors_all_preserved(self):
        rows=self.changed(lambda d:d['host']['rule4'][0].update({'dst':'192.0.2.0/24','iif':'mgmt0','oif':'lo','fwmark':'0x1','fwmask':'0xff','suppress_prefixlength':12,'l3mdev':False,'action':'lookup','protocol':'static'}))
        e=self.f.complete(rows); a=e.normalized.namespaces[0].rules[0].attributes
        self.assertEqual(a.get('fwmark'),'0x1'); self.assertIs(a.get('l3mdev'),False)
        self.assertEqual(a.get('dst'),'192.0.2.0/24')
        with self.assertRaisesRegex(c.ContractViolation2,'snapshot_changed'): t.compare_topology_snapshots2(e,self.baseline)

    def test_missing_mask_selector_is_not_defaulted(self):
        self.invalid(lambda d:d['host']['rule4'][0].__setitem__('fwmark','0x1'),'v2_topology_selector_incomplete')
        self.invalid(lambda d:d['host']['rule4'][0].__setitem__('fwmask','0xff'),'v2_topology_selector_incomplete')

    def test_unsupported_route_encap_multipath_expiry_fail(self):
        for key,value in (('encap',{}),('nexthops',[]),('expires',1)):
            self.invalid(lambda d:d['host']['route4'][0].__setitem__(key,value),'v2_topology_unknown_field')

    def test_timer_bounds_and_exact_transition(self):
        for value in (-1,86400.1,'178.16',True): self.invalid(lambda d:d['host']['link'][2]['linkinfo']['info_data'].__setitem__('gc_timer',value))
        e=self.f.complete(self.changed(lambda d:d['host']['link'][2]['linkinfo']['info_data'].__setitem__('gc_timer',179)))
        with self.assertRaisesRegex(c.ContractViolation2,'snapshot_changed'): t.compare_topology_snapshots2(e,self.baseline)
        self.assertTrue(all(r.transition=='exact_unchanged' for r in s.REGISTRY))

    def test_lifetime_not_erased(self):
        e=self.f.complete(self.changed(lambda d:d['host']['address'][0]['addr_info'][0].__setitem__('valid_life_time',300)))
        self.assertEqual(e.normalized.namespaces[0].addresses[0].address.get('valid_life_time'),300)
        with self.assertRaises(c.ContractViolation2): t.compare_topology_snapshots2(e,self.baseline)

    def test_optional_absence_distinct_from_null_or_empty(self):
        a=self.baseline.normalized.namespaces[0].routes[0].attributes
        self.assertFalse(a.has('flags'))
        e=self.f.complete(self.changed(lambda d:d['host']['route4'][0].__setitem__('flags',[])))
        self.assertTrue(e.normalized.namespaces[0].routes[0].attributes.has('flags'))
        with self.assertRaises(c.ContractViolation2): t.compare_topology_snapshots2(e,self.baseline)
        self.invalid(lambda d:d['host']['route4'][0].__setitem__('flags',None))

    def test_unknown_route_action_protocol_flag_refused(self):
        for key,value in (('type','blackhole'),('protocol','unknown-protocol'),('flags',['unknown-flag'])):
            self.invalid(lambda d:d['host']['route4'][0].__setitem__(key,value))
        self.invalid(lambda d:d['host']['rule4'][0].__setitem__('action','goto'))

    def test_unknown_flags_refused(self):
        self.invalid(lambda d:d['host']['link'][0].__setitem__('flags',['UNREVIEWED']))
        self.invalid(lambda d:d['host']['vlan'][0]['vlans'][0].__setitem__('flags',['unknown']))

    def test_key_order_and_whitespace_not_graph_changes(self):
        rows=deepcopy(self.f.rows)
        for role in rows:
            for source,values in rows[role].items():
                rows[role][source]=json.dumps(values,sort_keys=True,indent=1).encode()
        e=self.f.complete(rows)
        self.assertIs(t.compare_topology_snapshots2(e,self.baseline),e)

    def test_duplicate_frozen_object_fields_rejected(self):
        docs,plan=self.f.bundle(); source=t.decode_topology_documents2(docs,self.f.profile,plan)[0]
        duplicate=s.FrozenObject2(source.rows[0].fields+(source.rows[0].fields[0],))
        with self.assertRaises(c.ContractViolation2): replace(source,rows=(duplicate,)+source.rows[1:])

    def test_timer_field_does_not_accept_arbitrary_decimal_object(self):
        with self.assertRaises(c.ContractViolation2): j.ExactDecimal2('00.1')
        with self.assertRaises(c.ContractViolation2): j.ExactDecimal2('1.0000000')

    def test_complete_limitations_are_explicit(self):
        self.assertIn('capture_completeness_not_attested',self.baseline.limitations)
        self.assertIn('attachments_config_fds_unobserved',self.baseline.limitations)


class JoinTests(_FixtureCase):
    def test_duplicate_ifindex(self):
        self.unproven(lambda d:d['host']['link'][1].__setitem__('ifindex',1),'link_identity_ambiguous')

    def test_duplicate_ifname_ambiguous_master(self):
        self.unproven(lambda d:d['host']['link'][1].__setitem__('ifname','tcsh0'),'link_identity_ambiguous')

    def test_address_wrong_index_and_name(self):
        self.unproven(lambda d:d['host']['address'][0].__setitem__('ifindex',123),'address_link_unproven')
        self.unproven(lambda d:d['host']['address'][0].__setitem__('ifname','other'),'address_link_unproven')

    def test_address_rows_missing_or_duplicate(self):
        self.unproven(lambda d:d['host']['address'].pop(),'address_coverage_missing')
        self.unproven(lambda d:d['host']['address'].append(deepcopy(d['host']['address'][0])),'address_coverage_missing')

    def test_address_duplicate_identity(self):
        self.unproven(lambda d:d['host']['address'][0]['addr_info'].append(deepcopy(d['host']['address'][0]['addr_info'][0])),'address_identity_ambiguous')

    def test_unknown_master_name(self):
        self.unproven(lambda d:d['host']['bridge_link'][0].__setitem__('master','absent'),'bridge_membership_unproven')

    def test_master_is_not_bridge(self):
        self.unproven(lambda d:d['host']['bridge_link'][0].__setitem__('master','mgmt0'),'bridge_membership_unproven')

    def test_ip_master_reference_missing(self):
        self.unproven(lambda d:d['host']['link'][3].__setitem__('master',123),'master_unproven')

    def test_ip_and_bridge_disagree(self):
        self.unproven(lambda d:d['host']['link'][3].pop('master'),'bridge_membership_unproven')
        self.unproven(lambda d:d['host']['bridge_link'][0].__setitem__('ifname','wrong'),'bridge_membership_unproven')

    def test_missing_or_duplicate_port(self):
        self.unproven(lambda d:d['host']['bridge_link'].pop(),'bridge_membership_unproven')
        self.unproven(lambda d:d['host']['bridge_link'].append(deepcopy(d['host']['bridge_link'][0])),'bridge_membership_unproven')

    def test_unexpected_port_not_found_in_ip(self):
        self.unproven(lambda d:d['host']['bridge_link'][0].__setitem__('ifindex',999),'bridge_membership_unproven')

    def test_peer_wrong_ifindex(self):
        self.unproven(lambda d:d['runner']['link'][1].__setitem__('link_index',9),'peer_identity_unproven')

    def test_peer_wrong_nsid(self):
        self.unproven(lambda d:d['runner']['link'][1].__setitem__('link_netnsid',21),'peer_identity_unproven')

    def test_peer_missing_index_or_nsid_not_inferred_from_if_string(self):
        for key in ('link_index','link_netnsid'):
            self.unproven(lambda d:d['runner']['link'][1].pop(key),'peer_identity_unproven')

    def test_peer_missing_independent_witness(self):
        n=self.f.normalized(plan_change=lambda p:replace(p,peer_witnesses=()))
        self.assertIn('peer_identity_unproven',t.complete_topology2(n).uncertainty_reasons)

    def test_peer_wrong_namespace_same_ifindex(self):
        other=replace(self.f.peers[0],second=t.LinkReference2(self.f.namespaces[2].key,2))
        # A coherent one-witness plan must still prove reciprocal peer index/NSID.
        n=self.f.normalized(plan_change=lambda p:replace(p,peer_witnesses=(other,)))
        self.assertIn('peer_identity_unproven',t.complete_topology2(n).uncertainty_reasons)

    def test_conflicting_nsid_namespace_mapping(self):
        w=replace(self.f.peers[1],first_observed_nsid=10)
        with self.assertRaisesRegex(c.ContractViolation2,'peer_invalid'):
            self.f.normalized(plan_change=lambda p:replace(p,peer_witnesses=(p.peer_witnesses[0],w)))

    def test_vlan_unknown_port(self):
        self.unproven(lambda d:d['host']['vlan'][0].__setitem__('ifname','unknown'),'vlan_link_unproven')

    def test_vlan_duplicate_range_and_reversed_range(self):
        self.unproven(lambda d:d['host']['vlan'][0]['vlans'].append({'vlan':1,'vlanEnd':2,'flags':[]}),'vlan_identity_ambiguous')
        self.invalid(lambda d:d['host']['vlan'][0]['vlans'][0].__setitem__('vlanEnd',0))

    def test_fdb_unknown_port_bridge_or_vlan(self):
        for key,value,reason in (('dev','unknown','fdb_link_unproven'),('master','mgmt0','fdb_link_unproven'),('vlan',20,'fdb_vlan_unproven')):
            self.unproven(lambda d:d['host']['fdb'][0].__setitem__(key,value),reason)

    def test_fdb_duplicate_and_native_state_retained(self):
        self.unproven(lambda d:d['host']['fdb'].append(deepcopy(d['host']['fdb'][0])),'fdb_identity_ambiguous')
        self.assertEqual(self.baseline.normalized.namespaces[0].fdb[0].attributes.get('state'),('permanent',))

    def test_routes_unknown_device_and_table(self):
        self.unproven(lambda d:d['host']['route4'][0].__setitem__('dev','unknown'),'route_link_unproven')
        self.unproven(lambda d:d['host']['route4'][0].__setitem__('table','unknown'),'table_reference_unproven')

    def test_rule_unknown_interface_and_table(self):
        self.unproven(lambda d:d['host']['rule4'][0].__setitem__('iif','unknown'),'route_link_unproven')
        self.unproven(lambda d:d['host']['rule4'][0].__setitem__('table',123),'table_reference_unproven')

    def test_route_gateway_change_visible_not_automatically_policy_accepted(self):
        e=self.f.complete(self.changed(lambda d:d['host']['route4'][0].__setitem__('gateway','192.0.2.254')))
        self.assertEqual(e.stage,'topology_complete')
        with self.assertRaisesRegex(c.ContractViolation2,'snapshot_changed'): t.compare_topology_snapshots2(e,self.baseline)

    def test_route_and_rpdb_order_preserved(self):
        e=self.f.complete(self.changed(lambda d:d['host']['rule4'].reverse()))
        self.assertEqual([r.attributes.get('priority') for r in e.normalized.namespaces[0].rules[:2]],[32766,0])
        with self.assertRaises(c.ContractViolation2): t.compare_topology_snapshots2(e,self.baseline)

    def test_extra_link_visible_and_changes_pinned_graph(self):
        def change(d):
            d['host']['link'].append(link(20,'extra0','02:00:00:00:00:20'))
            d['host']['address'].append({'ifindex':20,'ifname':'extra0','addr_info':[]})
        e=self.f.complete(self.changed(change))
        self.assertEqual(e.stage,'topology_complete')
        self.assertIn('extra0',[l.ifname for l in e.normalized.namespaces[0].links])
        with self.assertRaises(c.ContractViolation2): t.compare_topology_snapshots2(e,self.baseline)

    def test_extra_bridge_remains_visible(self):
        def change(d):
            d['host']['link'].append(link(20,'extra-br','02:00:00:00:00:20','bridge'))
            d['host']['address'].append({'ifindex':20,'ifname':'extra-br','addr_info':[]})
        e=self.f.complete(self.changed(change))
        self.assertEqual([l.ifname for l in e.normalized.namespaces[0].links if l.kind=='bridge'],['tcsh0','extra-br'])
        self.assertFalse(e.management_policy_verified)

    def test_empty_full_link_inventory_is_unproven_not_absence_proof(self):
        def change(d):
            d['runner']['link']=[]; d['runner']['address']=[]
        self.unproven(change,'loopback_identity_unproven')

    def test_removed_optional_selector_detected_against_pinned_snapshot(self):
        rows=self.changed(lambda d:d['host']['rule4'][0].__setitem__('dst','192.0.2.0/24'))
        pinned=self.f.complete(rows)
        self.assertEqual(pinned.stage,'topology_complete')
        rows['host']['rule4'][0].pop('dst')
        candidate=self.f.complete(rows)
        with self.assertRaisesRegex(c.ContractViolation2,'snapshot_changed'):
            t.compare_topology_snapshots2(candidate,pinned)


class ProvenanceTests(_FixtureCase):
    def test_source_raw_hash_and_size(self):
        docs,plan=self.f.bundle(); raw,d=docs[0]
        for bad in (raw+b' ',raw.replace(b'lo',b'xx',1)):
            with self.assertRaisesRegex(c.ContractViolation2,'capture_mismatch'): t.decode_topology_source2(bad,self.f.profile,d)
        result=t.decode_topology_source2(raw,self.f.profile,d)
        self.assertEqual(result.descriptor.raw_sha256,hashlib.sha256(raw).hexdigest())

    def test_source_reference_substitution(self):
        docs,plan=self.f.bundle(); raw,d=docs[0]
        altered=replace(d,provenance_reference_digest=hd('foreign-reference'))
        with self.assertRaisesRegex(c.ContractViolation2,'source_reference_mismatch'):
            t.decode_topology_documents2(((raw,altered),),self.f.profile,plan)

    def test_duplicate_capture_uuid_or_source(self):
        docs,plan=self.f.bundle(); decoded=t.decode_topology_documents2(docs,self.f.profile,plan)
        with self.assertRaises(c.ContractViolation2): t.normalize_topology2(decoded+(decoded[0],),plan)
        with self.assertRaises(c.ContractViolation2): replace(plan,captures=plan.captures+(plan.captures[0],))

    def test_namespace_wrong_boot_session_or_duplicate_inode(self):
        for key,value in (('host_boot_uuid',uid(999)),('reader_session_uuid',uid(999)),('netns_inode',100)):
            docs,plan=self.f.bundle()
            role=replace(plan.namespaces[1],key=replace(plan.namespaces[1].key,**{key:value}))
            with self.assertRaises(c.ContractViolation2): replace(plan,namespaces=(plan.namespaces[0],role,plan.namespaces[2]))

    def test_wrong_namespace_descriptor_not_in_plan(self):
        docs,plan=self.f.bundle(); raw,d=docs[0]
        d=replace(d,namespace=self.f.namespaces[1].key)
        with self.assertRaises(c.ContractViolation2): t.decode_topology_documents2(((raw,d),),self.f.profile,plan)

    def test_wrong_binary_profile_or_exit(self):
        docs,plan=self.f.bundle(); raw,d=docs[0]
        for name,value in (('binary_digest',hd('wrong-binary')),('profile_digest',hd('wrong-profile')),('exit_status',1)):
            with self.assertRaises(c.ContractViolation2): t.decode_topology_source2(raw,self.f.profile,replace(d,**{name:value}))

    def test_changed_approval_context_epoch_not_inherited(self):
        docs,plan=self.f.bundle()
        for name,value in (('approval_digest',hd('new-approval')),('context_uuid',uid(888)),('writer_epoch_uuid',uid(888))):
            with self.assertRaisesRegex(c.ContractViolation2,'provenance_mismatch'): replace(plan,**{name:value})

    def test_direct_decoded_constructor_cannot_replace_rows(self):
        docs,plan=self.f.bundle(); decoded=t.decode_topology_documents2(docs,self.f.profile,plan)[0]
        row=s.FrozenObject2(tuple((k,99 if k=='ifindex' else v) for k,v in decoded.rows[0].fields))
        with self.assertRaisesRegex(c.ContractViolation2,'capture_mismatch'): replace(decoded,rows=(row,)+decoded.rows[1:])

    def test_direct_normalized_constructor_cannot_hide_namespace(self):
        n=self.baseline.normalized
        with self.assertRaises(TypeError): replace(n,namespaces=())
        with self.assertRaises(TypeError): replace(n.namespaces[0],links=())

    def test_exact_repeated_snapshot_succeeds_without_new_authority(self):
        self.assertIs(t.compare_topology_snapshots2(self.baseline,self.f.complete()),self.baseline)
        self.assertFalse(self.baseline.physical_probe_permitted)


class NativeFixtureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.path=Path(__file__).parent/'fixtures/kernel_6_8_nft_1_0_9/native'
        cls.fixture=TopologyFixture2.create()

    def decode(self,name,source):
        raw=(self.path/name).read_bytes(); f=self.fixture
        d=t.CaptureDescriptor2(f.namespaces[0].key,source,f.profile.digest,
            f.profile.ip_binary_digest if source=='link_single' else f.profile.bridge_binary_digest,
            uid(700 if source=='link_single' else 701),uid(3),hd('original-artifact-offline-reference'),uid(4),hashlib.sha256(raw).hexdigest(),len(raw),hd('provenance.json:'+name))
        return t.decode_topology_source2(raw,f.profile,d)

    def test_original_hashes_and_exact_terminal_lines(self):
        manifest=json.loads((self.path/'provenance.json').read_text())
        terminal=(self.path/'raw_terminal_capture.md').read_bytes()
        for name in ('bridge_tc_br0_final.json','bridge_links_final.json'):
            raw=(self.path/name).read_bytes()
            # Manifest shape is intentionally inspected, not reconstructed.
            item=next(item for item in manifest['files'] if item['name']==name) if isinstance(manifest['files'],list) else manifest['files'][name]
            self.assertEqual(hashlib.sha256(raw).hexdigest(),item['sha256'])
            self.assertIn(raw.strip(),terminal)

    def test_bridge_ports_actual_master_indices_link_strings(self):
        d=self.decode('bridge_links_final.json','bridge_link_basic')
        self.assertEqual([r.get('master') for r in d.rows],['tc-br0','tc-br0'])
        self.assertEqual([r.get('ifindex') for r in d.rows],[7,9])
        self.assertEqual([r.get('link') for r in d.rows],['if6','if8'])
        self.assertEqual(d.descriptor.argv,('bridge','-j','link','show'))
        self.assertEqual(d.descriptor.extent,'basic_ports')

    def test_bridge_only_options_and_exact_decimal(self):
        d=self.decode('bridge_tc_br0_final.json','link_single'); row=d.rows[0]
        self.assertEqual(row.get('ifindex'),5); self.assertEqual(row.get('ifname'),'tc-br0')
        options=row.get('linkinfo').get('info_data')
        self.assertEqual(options.get('nf_call_iptables'),0)
        self.assertEqual(options.get('nf_call_ip6tables'),0)
        self.assertEqual(options.get('vlan_protocol'),'802.1Q')
        self.assertEqual(options.get('gc_timer').token,'178.16')
        self.assertEqual(options.get('hello_timer').token,'0.00')
        self.assertEqual(d.descriptor.argv,('ip','-j','-d','link','show','tc-br0'))

    def test_original_partial_artifacts_cannot_be_complete(self):
        f=self.fixture; sources=(self.decode('bridge_tc_br0_final.json','link_single'),self.decode('bridge_links_final.json','bridge_link_basic'))
        plan=t.TopologyCapturePlan2(f.profile,uid(3),hd('original-artifact-offline-reference'),uid(4),f.namespaces,
            tuple(d.descriptor for d in sources),(),())
        e=t.complete_topology2(t.normalize_topology2(sources,plan))
        self.assertEqual(e.stage,'topology_unproven')
        self.assertIn('source_coverage_missing',e.uncertainty_reasons)
        self.assertIn('partial_capture',e.uncertainty_reasons)
        self.assertIn('bridge_membership_unproven',e.uncertainty_reasons)

    def test_original_partial_cannot_replace_pinned_full_source(self):
        f=self.fixture; docs,plan=f.bundle(); d=self.decode('bridge_tc_br0_final.json','link_single')
        with self.assertRaisesRegex(c.ContractViolation2,'source_reference_mismatch'):
            t.normalize_topology2((d,),plan)

    def test_native_profiles_have_exact_fragment_provenance_only(self):
        for source,name in (('link_single','bridge_tc_br0_final.json'),('bridge_link_basic','bridge_links_final.json')):
            self.assertTrue(any(r.evidence_reference=='native/'+name for r in s.REGISTRY if r.source==source))
            self.assertTrue(any(r.evidence_reference=='provisional_offline_specification_v1' for r in s.REGISTRY if r.source==source))
        self.assertEqual(self.fixture.profile.acceptance,'provisional_offline_only')


class IsolationTests(unittest.TestCase):
    def test_production_ast_has_no_io_or_legacy_imports(self):
        allowed={'dataclasses','hashlib','ipaddress','re','native_v2_contracts','native_v2_topology_schema','native_v2_topology_json'}
        for name in ('native_v2_topology','native_v2_topology_schema','native_v2_topology_json'):
            tree=ast.parse((Path(__file__).parents[1]/(name+'.py')).read_text())
            for node in ast.walk(tree):
                if isinstance(node,ast.Import): self.assertTrue(all(alias.name in allowed for alias in node.names))
                if isinstance(node,ast.ImportFrom):
                    self.assertTrue(node.module in allowed or node.module is None)
                    if node.module is None: self.assertTrue(all(alias.name in allowed for alias in node.names))

    def test_fresh_import_has_no_network_process_or_django_side_effects(self):
        script='''
import socket,subprocess,os,sys
from unittest.mock import patch
def forbidden(*a,**k): raise AssertionError('forbidden I/O')
with patch.object(socket,'socket',forbidden), patch.object(subprocess,'Popen',forbidden), patch.object(os,'system',forbidden):
 import trusted_checker_network.native_v2_topology
 assert 'docker' not in sys.modules and 'django' not in sys.modules
'''
        result=subprocess.run([sys.executable,'-W','error::ResourceWarning','-c',script],capture_output=True,check=False)
        self.assertEqual(result.returncode,0,result.stderr.decode())
