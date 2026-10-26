"""Offline V2-04 policy mutation tests. No OS/network operations."""
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
from trusted_checker_network import native_v2_topology as t
from trusted_checker_network import native_v2_topology_schema as s
from trusted_checker_network import native_v2_management as m
from .native_v2_support import hd, uid
from .native_v2_topology_support import link
from .native_v2_management_support import ManagementFixture2, address


class _FixtureCase(unittest.TestCase):
    def setUp(self):
        self.f=ManagementFixture2.create()
        self.topology=self.f.topology()
        self.baseline=m.validate_management_profile2(self.topology,self.f.policy,self.f.pinned_digest)
        self.assertEqual(self.topology.stage,'topology_complete')
        self.assertEqual(self.baseline.structural_result,'profile_structurally_matched')
        self.assertEqual(self.baseline.result,'profile_unproven')

    def mismatch(self,change,reason=None):
        result=self.f.validate(self.f.changed_rows(change))
        self.assertEqual(result.result,'profile_mismatch')
        self.assertEqual(result.structural_result,'profile_mismatch')
        self.assertFalse(result.management_policy_verified)
        self.assertFalse(result.isolation_verified)
        if reason: self.assertIn(reason,result.mismatch_reasons)
        return result

    def invalid(self,change):
        with self.assertRaises(c.ContractViolation2): self.f.validate(self.f.changed_rows(change))


class ResultTests(_FixtureCase):
    def test_positive_structural_match_and_unproven_are_separate(self):
        value=self.baseline
        self.assertEqual(value.structural_result,'profile_structurally_matched')
        self.assertEqual(value.result,'profile_unproven')
        self.assertEqual(value.isolation_result,'isolation_unproven')
        self.assertEqual(value.reason,'native_schema_provisional')
        self.assertFalse(value.mismatch_reasons)

    def test_no_authority_or_verification_constructor_overrides(self):
        for field,value in (('physical_probe_permitted',True),('ownership_proven',True),
                            ('continuous_attestation',True)):
            with self.assertRaises(c.ContractViolation2): replace(self.baseline,**{field:value})
        for field,value in (('management_policy_verified',True),('isolation_verified',True),
                            ('measurement_verified',True),('result','profile_structurally_matched'),
                            ('structural_result','profile_structurally_matched'),('evidence_statuses',())):
            with self.assertRaises(TypeError): replace(self.baseline,**{field:value})

    def test_result_profile_and_nested_records_frozen(self):
        for value in (self.baseline,self.f.policy,*self.f.policy.namespaces,*self.f.policy.requirements,
                      *self.baseline.evidence_statuses):
            self.assertFalse(value.physical_probe_permitted)
            self.assertFalse(value.ownership_proven)
            with self.assertRaises(FrozenInstanceError): value.physical_probe_permitted=True

    def test_profile_id_version_domain_exact(self):
        self.assertEqual(self.f.policy.profile_id,'dedicated-management-host-v2')
        for field,value in (('profile_id','dedicated-management-host-v1'),('policy_revision',True),
                            ('policy_revision',2),('acceptance','native_approved'),('origin','physical_linux'),
                            ('authentication','authenticated'),('version',1)):
            with self.assertRaises(c.ContractViolation2): replace(self.f.policy,**{field:value})

    def test_dedicated_boolean_not_an_input(self):
        with self.assertRaises(TypeError): replace(self.f.policy,dedicated_vm=True)

    def test_digest_reproducible_but_not_authentication(self):
        self.assertEqual(self.f.policy.digest,ManagementFixture2.create().policy.digest)
        self.assertEqual(self.baseline.digest,self.f.validate().digest)
        self.assertEqual(self.baseline.authentication,'not_authenticated')

    def test_exact_native_hook_requirements(self):
        self.assertEqual(len(self.f.policy.expected_host_hooks),7)
        self.assertIn(('bridge','forward',0,'drop'),self.f.policy.expected_host_hooks)
        self.assertIn(('inet','forward',-310,'accept'),self.f.policy.expected_host_hooks)
        with self.assertRaises(TypeError): replace(self.f.policy,expected_host_hooks=())

    def test_all_mandatory_evidence_surfaces_unobserved(self):
        surfaces={status.requirement.surface for status in self.baseline.evidence_statuses}
        self.assertEqual(surfaces,{name for name,expected in (*m.EXPECTATIONS,*m.LINK_EXPECTATIONS)})
        for value in self.baseline.evidence_statuses:
            self.assertEqual(value.status,'unobserved')
        self.assertTrue({'nft_hooks_priorities','tc_ingress','tc_egress','xdp','flowtables','offloads',
            'ipv4_forwarding','ipv6_forwarding','proxy_arp','proxy_nd','bridge_netfilter',
            'network_capabilities','external_inherited_fds','writer_authority'}<=surfaces)

    def test_evidence_status_cannot_claim_none_false_or_verified(self):
        status=self.baseline.evidence_statuses[0]
        for value in ('none','absent','verified',False,None):
            with self.assertRaises(c.ContractViolation2): replace(status,status=value)
        with self.assertRaises(TypeError): replace(self.f.policy,requirements=())

    def test_os_unknowns_block_even_complete_topology(self):
        self.assertIn('mandatory_os_evidence_unobserved',self.baseline.uncertainty_reasons)
        self.assertIn('writer_control_unproven',self.baseline.uncertainty_reasons)
        self.assertIn('capture_provenance_unauthenticated',self.baseline.uncertainty_reasons)
        self.assertIn('approved_native_host_profile_unproven',self.baseline.uncertainty_reasons)
        self.assertFalse(self.baseline.management_policy_verified)
        self.assertFalse(self.baseline.isolation_verified)

    def test_structural_match_cannot_open_physical_gate(self):
        from trusted_checker_physical.collector import PhysicalProbeGate
        from trusted_checker_runtime.profiles import Denied
        with self.assertRaisesRegex(Denied,'physical_network_boundary_not_accepted'):
            PhysicalProbeGate.permit(self.baseline)

    def test_mismatch_precedes_provisional_unknown(self):
        value=self.mismatch(lambda d:d['host']['route4'][0].__setitem__('gateway','192.0.2.99'))
        self.assertEqual(value.reason,'route4_policy_mismatch')
        self.assertIn('native_schema_provisional',value.uncertainty_reasons)


class LinkPolicyTests(_FixtureCase):
    def test_management_nic_enslaved_even_structurally_complete(self):
        def change(d):
            d['host']['link'][1]['master']=5
            d['host']['bridge_link'].append({'ifindex':2,'ifname':'mgmt0','link':'if99',
                'flags':['UP'],'mtu':1500,'master':'tcsh0','state':'forwarding','priority':32,'cost':2})
        value=self.mismatch(change,'management_link_attachment_forbidden')
        self.assertEqual(value.topology.stage,'topology_complete')

    def test_management_name_alone_not_identity(self):
        self.mismatch(lambda d:d['host']['link'][1].__setitem__('ifindex',22),'link_inventory_mismatch')
        self.mismatch(lambda d:d['host']['link'][1].__setitem__('address','02:00:00:00:99:01'),'link_identity_mismatch')

    def test_management_name_change_not_auto_eth0_acceptance(self):
        self.mismatch(lambda d:d['host']['link'][1].__setitem__('ifname','eth0'),'link_policy_mismatch')

    def test_management_turned_into_veth(self):
        def change(d):
            d['host']['link'][1].update({'linkinfo':{'info_kind':'veth'},'link_index':2,'link_netnsid':10})
        self.mismatch(change,'management_link_attachment_forbidden')

    def test_management_replaced_with_bridge(self):
        self.mismatch(lambda d:d['host']['link'][1].__setitem__('linkinfo',{'info_kind':'bridge'}),
                      'management_link_attachment_forbidden')

    def test_unsupported_bond_vrf_tunnel_macvlan_fail_decoder(self):
        for kind in ('bond','vrf','tunnel','macvlan','vxlan'):
            self.invalid(lambda d:d['host']['link'][1].__setitem__('linkinfo',{'info_kind':kind}))

    def test_third_bridge_port(self):
        def change(d):
            d['host']['link'].append(link(11,'vethrogue','02:00:00:00:00:11','veth',5,3,10))
            d['host']['address'].append({'ifindex':11,'ifname':'vethrogue','addr_info':[]})
            d['host']['bridge_link'].append({'ifindex':11,'ifname':'vethrogue','link':'if3','flags':['UP'],
                'mtu':1500,'master':'tcsh0','state':'forwarding','priority':32,'cost':2})
        self.mismatch(change,'link_inventory_mismatch')

    def test_extra_unattached_veth(self):
        def change(d):
            d['host']['link'].append(link(11,'vethrogue','02:00:00:00:00:11','veth',peer=3,nsid=10))
            d['host']['address'].append({'ifindex':11,'ifname':'vethrogue','addr_info':[]})
        self.mismatch(change,'link_inventory_mismatch')

    def test_extra_bridge_or_management_nic(self):
        for kind in ('bridge',None):
            def change(d):
                d['host']['link'].append(link(11,'extra0','02:00:00:00:00:11',kind))
                d['host']['address'].append({'ifindex':11,'ifname':'extra0','addr_info':[]})
            self.mismatch(change,'link_inventory_mismatch')

    def test_peer_identity_ifindex_mac_mtu_flags(self):
        for key,value in (('ifindex',20),('address','02:00:00:00:99:02'),('mtu',1400),('flags',['UP','PROMISC'])):
            self.mismatch(lambda d:d['runner']['link'][1].__setitem__(key,value),'link_policy_mismatch')

    def test_host_veth_wrong_reciprocal_index(self):
        value=self.mismatch(lambda d:d['host']['link'][3].__setitem__('link_index',9),'link_policy_mismatch')
        self.assertEqual(value.topology.stage,'topology_unproven')

    def test_target_extra_interface(self):
        def change(d):
            d['target']['link'].append(link(4,'extra0','02:00:00:00:00:44'))
            d['target']['address'].append({'ifindex':4,'ifname':'extra0','addr_info':[]})
        value=self.mismatch(change,'link_inventory_mismatch')
        self.assertEqual(value.topology.stage,'topology_complete')

    def test_missing_management_interface_not_hidden(self):
        def change(d):
            d['host']['link'].pop(1); d['host']['address'].pop(1)
        self.mismatch(change,'link_inventory_mismatch')

    def test_wrong_bridge_options_or_mtu(self):
        self.mismatch(lambda d:d['host']['link'][2]['linkinfo']['info_data'].__setitem__('nf_call_iptables',1),'link_policy_mismatch')
        self.mismatch(lambda d:d['host']['link'][2].__setitem__('mtu',1400),'link_policy_mismatch')

    def test_bridge_timer_not_ignored(self):
        self.mismatch(lambda d:d['host']['link'][2]['linkinfo']['info_data'].__setitem__('gc_timer',179),'link_policy_mismatch')

    def test_port_master_or_state_drift(self):
        self.mismatch(lambda d:d['host']['bridge_link'][0].__setitem__('master','mgmt0'),'bridge_link_policy_mismatch')
        self.mismatch(lambda d:d['host']['bridge_link'][0].__setitem__('state','blocking'),'bridge_link_policy_mismatch')

    def test_unknown_vlan_and_pvid_untagged_drift(self):
        self.mismatch(lambda d:d['host']['vlan'][0]['vlans'][0].__setitem__('vlan',22),'vlan_policy_mismatch')
        self.mismatch(lambda d:d['host']['vlan'][0]['vlans'][0].__setitem__('flags',[]),'vlan_policy_mismatch')

    def test_fdb_foreign_mac_or_port(self):
        self.mismatch(lambda d:d['host']['fdb'][0].__setitem__('mac','02:aa:bb:cc:dd:ee'),'fdb_policy_mismatch')
        self.mismatch(lambda d:d['host']['fdb'][0].__setitem__('dev','mgmt0'),'fdb_policy_mismatch')

    def test_fdb_state_and_offload_flag_kept(self):
        self.mismatch(lambda d:d['host']['fdb'][0].__setitem__('state',['dynamic']),'fdb_policy_mismatch')
        self.mismatch(lambda d:d['host']['fdb'][0].__setitem__('flags',['master','offload']),'fdb_policy_mismatch')

    def test_management_moved_to_runner_namespace(self):
        def change(d):
            nic=d['host']['link'].pop(1); nic['ifindex']=3
            a=d['host']['address'].pop(1); a['ifindex']=3
            d['runner']['link'].append(nic); d['runner']['address'].append(a)
        self.mismatch(change,'link_inventory_mismatch')

    def test_management_slave_flag_requires_refusal(self):
        self.mismatch(lambda d:d['host']['link'][1].__setitem__('flags',['UP','SLAVE']),
                      'management_link_attachment_forbidden')
        with self.assertRaisesRegex(c.ContractViolation2,'manifest_unsafe'):
            self.f.policy_change('host','link',lambda rows:rows[1].__setitem__('flags',['UP','SLAVE']))


class AddressRouteTests(_FixtureCase):
    def test_management_ipv4_ipv6_addresses_exact(self):
        addresses=self.baseline.topology.normalized.namespaces[0].addresses
        self.assertTrue(any(a.address.get('local')=='2001:db8::2' for a in addresses))
        self.mismatch(lambda d:d['host']['address'][1]['addr_info'][0].__setitem__('local','192.0.2.99'),'address_policy_mismatch')
        self.mismatch(lambda d:d['host']['address'][1]['addr_info'][1].__setitem__('local','2001:db8::99'),'address_policy_mismatch')

    def test_extra_secondary_address_and_lifetime(self):
        self.mismatch(lambda d:d['runner']['address'][1]['addr_info'].append(address('inet','10.201.1.22',24)),'address_policy_mismatch')
        self.mismatch(lambda d:d['host']['address'][1]['addr_info'][0].__setitem__('valid_life_time',300),'address_policy_mismatch')

    def test_host_test_side_ipv6_address_forbidden(self):
        for index in (2,3,4):
            self.mismatch(lambda d:d['host']['address'][index]['addr_info'].append(address('inet6','fe80::1',64,'link')),
                          'test_side_ipv6_forbidden')

    def test_peer_ipv6_link_local_forbidden(self):
        for role in ('runner','target'):
            self.mismatch(lambda d:d[role]['address'][1]['addr_info'].append(address('inet6','fe80::2',64,'link')),
                          'test_side_ipv6_forbidden')

    def test_host_test_side_ipv6_route_forbidden(self):
        def change(d):
            d['host']['route6'].append({'dst':'fe80::/64','dev':'vethrun','table':'main','protocol':'kernel',
                                      'scope':'link','type':'unicast'})
        self.mismatch(change,'test_side_ipv6_route_forbidden')

    def test_loopback_ipv6_allowed_exactly(self):
        self.assertEqual(self.baseline.structural_result,'profile_structurally_matched')
        self.mismatch(lambda d:d['runner']['address'][0]['addr_info'][1].__setitem__('local','::2'),'address_policy_mismatch')

    def test_other_default_gateway_v4_v6(self):
        self.mismatch(lambda d:d['host']['route4'][0].__setitem__('gateway','192.0.2.100'),'route4_policy_mismatch')
        self.mismatch(lambda d:d['host']['route6'][0].__setitem__('gateway','fe80::100'),'route6_policy_mismatch')

    def test_default_route_on_test_port(self):
        self.mismatch(lambda d:d['host']['route4'][0].__setitem__('dev','vethrun'),'host_default_route_not_management')

    def test_extra_route_and_source_route_not_provider_wildcard(self):
        self.mismatch(lambda d:d['host']['route4'].append({'dst':'198.51.100.0/24','dev':'mgmt0',
             'table':'main','protocol':'static','scope':'global','type':'unicast','gateway':'192.0.2.1'}),'route4_policy_mismatch')
        self.mismatch(lambda d:d['host']['route4'][0].__setitem__('src','192.0.2.0/24'),'route4_policy_mismatch')

    def test_metric_protocol_source_scope_type_optional_presence(self):
        for key,value in (('metric',99),('protocol','dhcp'),('prefsrc','192.0.2.3'),('scope','link'),('type','local'),('flags',[])):
            self.mismatch(lambda d:d['host']['route4'][0].__setitem__(key,value),'route4_policy_mismatch')
        self.mismatch(lambda d:d['host']['route4'][0].pop('metric'),'route4_policy_mismatch')

    def test_runner_default_route(self):
        self.mismatch(lambda d:d['runner']['route4'][0].__setitem__('dst','default'),'peer_default_route_forbidden')

    def test_target_gateway_even_without_default(self):
        self.mismatch(lambda d:d['target']['route4'][0].__setitem__('gateway','10.201.1.1'),'peer_gateway_forbidden')

    def test_peer_route_must_be_connected_or_local(self):
        self.mismatch(lambda d:d['runner']['route4'][0].__setitem__('protocol','static'),'peer_route_not_connected_or_local')
        self.mismatch(lambda d:d['runner']['route4'][0].__setitem__('scope','global'),'peer_route_not_connected_or_local')

    def test_alternate_table_and_unknown_alias(self):
        self.mismatch(lambda d:d['runner']['route4'][0].__setitem__('table','foreign'),'peer_alternate_route_table_forbidden')
        self.mismatch(lambda d:d['host']['route4'][0].__setitem__('table',123),'route4_policy_mismatch')

    def test_host_rpdb_selectors_and_priorities(self):
        for key,value in (('priority',1),('dst','192.0.2.0/24'),('iif','mgmt0'),('l3mdev',False),('suppress_prefixlength',24)):
            self.mismatch(lambda d:d['host']['rule4'][0].__setitem__(key,value),'rule4_policy_mismatch')
        self.mismatch(lambda d:d['host']['rule4'][0].update({'fwmark':'0x1','fwmask':'0xff'}),'rule4_policy_mismatch')

    def test_peer_rpdb_policy_reroute_forbidden(self):
        self.mismatch(lambda d:d['runner']['rule4'][0].__setitem__('dst','10.201.1.0/24'),'peer_policy_routing_forbidden')
        self.mismatch(lambda d:d['target']['rule6'][0].__setitem__('priority',1),'peer_policy_routing_forbidden')

    def test_equal_priority_is_ambiguous(self):
        self.mismatch(lambda d:d['host']['rule4'][1].__setitem__('priority',0),'ambiguous_rpdb_priority')

    def test_rpdb_and_route_order_preserved(self):
        self.mismatch(lambda d:d['host']['rule4'].reverse(),'rule4_policy_mismatch')
        self.mismatch(lambda d:d['runner']['route4'].reverse(),'route4_policy_mismatch')

    def test_unsupported_selectors_and_expiry_fail_early(self):
        self.invalid(lambda d:d['host']['rule4'][0].__setitem__('goto',100))
        self.invalid(lambda d:d['host']['route6'][0].__setitem__('expires',30))

    def test_peer_source_selector_cannot_be_blessed_by_manifest(self):
        self.mismatch(lambda d:d['runner']['route4'][0].__setitem__('src','10.201.1.0/24'),
                      'peer_source_route_forbidden')
        with self.assertRaisesRegex(c.ContractViolation2,'manifest_unsafe'):
            self.f.policy_change('runner','route4',lambda rows:rows[0].__setitem__('src','10.201.1.0/24'))

    def test_removing_approved_host_selector_is_mismatch(self):
        policy=self.f.policy_change('host','rule4',lambda rows:rows[0].__setitem__('dst','192.0.2.0/24'))
        rows=self.f.changed_rows(lambda d:d['host']['rule4'][0].__setitem__('dst','192.0.2.0/24'))
        positive=m.validate_management_profile2(self.f.topology(rows),policy,policy.digest)
        self.assertEqual(positive.structural_result,'profile_structurally_matched')
        rows['host']['rule4'][0].pop('dst')
        value=m.validate_management_profile2(self.f.topology(rows),policy,policy.digest)
        self.assertIn('rule4_policy_mismatch',value.mismatch_reasons)


class ProfileIntegrityTests(_FixtureCase):
    def test_spoofed_digest(self):
        value=m.validate_management_profile2(self.topology,self.f.policy,hd('spoofed-profile'))
        self.assertEqual(value.reason,'profile_digest_mismatch')
        self.assertEqual(value.result,'profile_mismatch')

    def test_replaced_manifest_even_if_snapshot_matches_new_manifest(self):
        changed=self.f.policy_change('host','route4',lambda rows:rows[0].__setitem__('gateway','192.0.2.99'))
        rows=self.f.changed_rows(lambda d:d['host']['route4'][0].__setitem__('gateway','192.0.2.99'))
        candidate=self.f.topology(rows)
        value=m.validate_management_profile2(candidate,changed,self.f.pinned_digest)
        self.assertIn('profile_digest_mismatch',value.mismatch_reasons)
        self.assertNotEqual(changed.digest,self.f.pinned_digest)

    def test_revision_review_writer_and_nft_references_are_in_digest(self):
        for field,value in (('review_reference_digest',hd('foreign-review')),
                            ('canonical_nft_recipe_reference_digest',hd('foreign-recipe')),
                            ('writers',replace(self.f.policy.writers,review_reference_digest=hd('foreign-writer-review')))):
            changed=replace(self.f.policy,**{field:value})
            self.assertNotEqual(changed.digest,self.f.pinned_digest)
            self.assertIn('profile_digest_mismatch',m.validate_management_profile2(self.topology,changed,self.f.pinned_digest).mismatch_reasons)

    def test_digest_type_format_invalid(self):
        for value in (None,True,'sha256',b'0'*64):
            with self.assertRaises(c.ContractViolation2): m.validate_management_profile2(self.topology,self.f.policy,value)

    def test_unsafe_manifest_runner_default_or_gateway_rejected(self):
        for key,value in (('dst','default'),('gateway','10.201.1.1')):
            with self.assertRaisesRegex(c.ContractViolation2,'manifest_unsafe'):
                self.f.policy_change('runner','route4',lambda rows:rows[0].__setitem__(key,value))

    def test_unsafe_manifest_host_test_ipv6_rejected(self):
        with self.assertRaisesRegex(c.ContractViolation2,'manifest_unsafe'):
            self.f.policy_change('host','address',lambda rows:rows[2]['addr_info'].append(address('inet6','fe80::1',64,'link')))

    def test_unsafe_manifest_peer_policy_route_rejected(self):
        with self.assertRaisesRegex(c.ContractViolation2,'manifest_unsafe'):
            self.f.policy_change('runner','rule4',lambda rows:rows[0].__setitem__('iif','eth0'))

    def test_invalid_profile_coverage_and_derived_requirements(self):
        host=self.f.policy.namespaces[0]
        with self.assertRaises(c.ContractViolation2): replace(host,sources=host.sources[:-1])
        with self.assertRaises(c.ContractViolation2): replace(host,sources=host.sources[:-1]+(host.sources[0],))
        with self.assertRaises(c.ContractViolation2): replace(self.f.policy,namespaces=self.f.policy.namespaces[:-1])
        with self.assertRaises(c.ContractViolation2): replace(host,links=host.links[:-1])

    def test_exact_creation_references_not_ownership_claim(self):
        linkpolicy=self.f.policy.namespaces[0].links[2]
        self.assertFalse(linkpolicy.ownership_proven)
        with self.assertRaises(c.ContractViolation2): replace(linkpolicy,creation_record_reference_digest=None)
        with self.assertRaises(c.ContractViolation2): replace(linkpolicy,ownership_proven=True)
        changed=replace(linkpolicy,creation_record_reference_digest=hd('other-creation-ref'))
        self.assertNotEqual(changed.digest,linkpolicy.digest)

    def test_unknown_profile_extra_inputs_rejected(self):
        with self.assertRaises(TypeError): replace(self.f.policy,allow_any_provider_routes=True)
        with self.assertRaises(TypeError): replace(self.f.policy,os_surfaces_verified=True)
        with self.assertRaises(TypeError): replace(self.f.policy,native_approved=True)

    def test_unsafe_management_role_and_expected_mac(self):
        host=self.f.policy.namespaces[0]
        with self.assertRaises(c.ContractViolation2): replace(host,links=(host.links[1],)+host.links[1:])
        bad=replace(host.links[1],mac='02:00:00:00:99:ff')
        with self.assertRaises(c.ContractViolation2): replace(host,links=(host.links[0],bad)+host.links[2:])

    def test_wrong_expected_peer_witness(self):
        witness=replace(self.f.policy.peer_witnesses[0],first_observed_nsid=999)
        with self.assertRaisesRegex(c.ContractViolation2,'manifest_unsafe'):
            replace(self.f.policy,peer_witnesses=(witness,self.f.policy.peer_witnesses[1]))

    def test_writer_principals_required_exact_unique(self):
        writers=self.f.policy.writers
        for values in ((),[hd('writer')],(hd('writer'),hd('writer'))):
            with self.assertRaises(c.ContractViolation2): replace(writers,principal_reference_digests=values)
        with self.assertRaises(c.ContractViolation2): replace(writers,mode='any_root_writer')

    def test_key_order_and_whitespace_not_policy_changes(self):
        rows=self.f.changed_rows(lambda d:None)
        for ns in rows:
            for source in rows[ns]: rows[ns][source]=json.dumps(rows[ns][source],sort_keys=True,indent=2).encode()
        self.assertEqual(self.f.validate(rows).structural_result,'profile_structurally_matched')

    def test_no_snapshot_to_profile_factory(self):
        self.assertFalse(hasattr(m,'profile_from_topology2'))
        self.assertFalse(hasattr(m,'approve_profile2'))
        with self.assertRaises(c.ContractViolation2): m.validate_management_profile2(self.topology,self.topology,self.f.pinned_digest)

    def test_nsid_mapping_cannot_name_two_namespaces(self):
        witness=replace(self.f.policy.peer_witnesses[1],first_observed_nsid=10)
        with self.assertRaisesRegex(c.ContractViolation2,'peer_nsid_conflict'):
            replace(self.f.policy,peer_witnesses=(self.f.policy.peer_witnesses[0],witness))

    def test_requirement_scope_covers_every_registered_link(self):
        links={link.reference for policy in self.f.policy.namespaces for link in policy.links}
        for surface,expectation in m.LINK_EXPECTATIONS:
            self.assertEqual({req.link for req in self.f.policy.requirements if req.surface==surface and req.link is not None},links)


class CoverageIdentityTests(_FixtureCase):
    def test_missing_document_not_synthetic_empty(self):
        f=self.f.topology_fixture; docs,plan=f.bundle()
        missing=tuple(item for item in docs if not (item[1].namespace==f.namespaces[-1].key and item[1].source=='fdb'))
        sources=t.decode_topology_documents2(missing,f.profile,plan)
        topology=t.complete_topology2(t.normalize_topology2(sources,plan))
        value=m.validate_management_profile2(topology,self.f.policy,self.f.pinned_digest)
        self.assertEqual(value.structural_result,'profile_unproven')
        self.assertEqual(value.result,'profile_unproven')
        self.assertIn('source_coverage_incomplete',value.uncertainty_reasons)
        self.assertNotIn('fdb',[s.descriptor.source for s in topology.normalized.namespaces[-1].sources])

    def test_missing_nonempty_source_not_structural_match(self):
        f=self.f.topology_fixture; docs,plan=f.bundle()
        sources=t.decode_topology_documents2(tuple(item for item in docs if item[1].source!='route4'),f.profile,plan)
        value=m.validate_management_profile2(t.complete_topology2(t.normalize_topology2(sources,plan)),self.f.policy,self.f.pinned_digest)
        self.assertEqual(value.structural_result,'profile_unproven')

    def test_empty_nonempty_source_is_actual_mismatch(self):
        self.mismatch(lambda d:d['host'].__setitem__('route4',[]),'route4_policy_mismatch')

    def test_missing_source_cannot_be_overridden_by_derived_records(self):
        with self.assertRaises(TypeError): replace(self.topology.normalized.namespaces[-1],fdb=())
        with self.assertRaises(TypeError): replace(self.topology,stage='topology_complete')

    def test_changed_namespace_coherent_graph_rejected(self):
        f=deepcopy(self.f.topology_fixture)
        old=f.namespaces[1].key; key=replace(old,netns_inode=999,namespace_binding_generation=2)
        f.namespaces=(f.namespaces[0],replace(f.namespaces[1],key=key),f.namespaces[2])
        def ref(value): return replace(value,namespace=key) if value.namespace==old else value
        f.peers=tuple(replace(w,first=ref(w.first),second=ref(w.second)) for w in f.peers)
        f.tables=tuple(replace(row,namespace=key) if row.namespace==old else row for row in f.tables)
        candidate=f.complete()
        self.assertEqual(candidate.stage,'topology_complete')
        value=m.validate_management_profile2(candidate,self.f.policy,self.f.pinned_digest)
        self.assertIn('namespace_identity_mismatch',value.mismatch_reasons)

    def test_namespace_reference_digest_changed(self):
        f=deepcopy(self.f.topology_fixture)
        f.namespaces=(replace(f.namespaces[0],namespace_reference_digest=hd('other-namespace-ref')),)+f.namespaces[1:]
        value=m.validate_management_profile2(f.complete(),self.f.policy,self.f.pinned_digest)
        self.assertIn('namespace_identity_mismatch',value.mismatch_reasons)

    def test_reader_session_change_coherent_graph_rejected(self):
        f=deepcopy(self.f.topology_fixture)
        mapping={n.key:replace(n.key,reader_session_uuid=uid(900)) for n in f.namespaces}
        f.namespaces=tuple(replace(n,key=mapping[n.key]) for n in f.namespaces)
        f.peers=tuple(replace(w,first=replace(w.first,namespace=mapping[w.first.namespace]),
                              second=replace(w.second,namespace=mapping[w.second.namespace])) for w in f.peers)
        f.tables=tuple(replace(row,namespace=mapping[row.namespace]) for row in f.tables)
        value=m.validate_management_profile2(f.complete(),self.f.policy,self.f.pinned_digest)
        self.assertIn('namespace_identity_mismatch',value.mismatch_reasons)

    def test_peer_witness_missing_unproven(self):
        f=self.f.topology_fixture; docs,plan=f.bundle(); plan=replace(plan,peer_witnesses=())
        sources=t.decode_topology_documents2(docs,f.profile,plan)
        value=m.validate_management_profile2(t.complete_topology2(t.normalize_topology2(sources,plan)),self.f.policy,self.f.pinned_digest)
        self.assertEqual(value.structural_result,'profile_unproven')
        self.assertIn('peer_witness_missing',value.uncertainty_reasons)

    def test_changed_approval_context_or_writer_epoch(self):
        f=self.f.topology_fixture; docs,plan=f.bundle()
        for key,value in (('context_uuid',uid(909)),('approval_digest',hd('other-approval')),('writer_epoch_uuid',uid(909))):
            changed=tuple((raw,replace(d,**{key:value})) for raw,d in docs)
            changed_plan=replace(plan,captures=tuple(d for raw,d in changed),**{key:value})
            sources=t.decode_topology_documents2(changed,f.profile,changed_plan)
            result=m.validate_management_profile2(t.complete_topology2(t.normalize_topology2(sources,changed_plan)),self.f.policy,self.f.pinned_digest)
            self.assertIn('capture_context_mismatch',result.mismatch_reasons)

    def test_changed_table_mapping_reference(self):
        f=self.f.topology_fixture; docs,plan=f.bundle()
        plan=replace(plan,table_mappings=(replace(plan.table_mappings[0],reference_digest=hd('different-table-reference')),)+plan.table_mappings[1:])
        sources=t.decode_topology_documents2(docs,f.profile,plan)
        result=m.validate_management_profile2(t.complete_topology2(t.normalize_topology2(sources,plan)),self.f.policy,self.f.pinned_digest)
        self.assertIn('table_mapping_mismatch',result.mismatch_reasons)

    def test_wrong_topology_type_rejected_before_any_policy_result(self):
        for value in (None,{},self.topology.normalized,self.baseline):
            with self.assertRaises(c.ContractViolation2): m.validate_management_profile2(value,self.f.policy,self.f.pinned_digest)

    def test_wrong_remaining_witness_not_hidden_by_missing_witness(self):
        f=self.f.topology_fixture; docs,plan=f.bundle()
        wrong=replace(plan.peer_witnesses[0],reference_digest=hd('other-peer-witness'))
        plan=replace(plan,peer_witnesses=(wrong,))
        sources=t.decode_topology_documents2(docs,f.profile,plan)
        value=m.validate_management_profile2(t.complete_topology2(t.normalize_topology2(sources,plan)),self.f.policy,self.f.pinned_digest)
        self.assertIn('peer_witness_mismatch',value.mismatch_reasons)
        self.assertIn('peer_witness_missing',value.uncertainty_reasons)
        self.assertEqual(value.result,'profile_mismatch')


class NativePartialTests(_FixtureCase):
    def native(self):
        path=Path(__file__).parent/'fixtures/kernel_6_8_nft_1_0_9/native'
        manifest=json.loads((path/'provenance.json').read_text())
        f=self.f.topology_fixture; docs=[]
        terminal=(path/'raw_terminal_capture.md').read_bytes()
        for i,(source,name) in enumerate((('link_single','bridge_tc_br0_final.json'),('bridge_link_basic','bridge_links_final.json'))):
            raw=(path/name).read_bytes()
            self.assertEqual(hashlib.sha256(raw).hexdigest(),manifest['files'][name]['sha256'])
            self.assertIn(raw.strip(),terminal)
            descriptor=t.CaptureDescriptor2(f.namespaces[0].key,source,f.profile.digest,
                f.profile.ip_binary_digest if source=='link_single' else f.profile.bridge_binary_digest,
                uid(920+i),uid(3),hd('synthetic-approval'),uid(4),hashlib.sha256(raw).hexdigest(),len(raw),hd('original:'+name))
            docs.append((raw,descriptor))
        plan=t.TopologyCapturePlan2(f.profile,uid(3),hd('synthetic-approval'),uid(4),f.namespaces,
                                    tuple(d for raw,d in docs),(),f.tables)
        return t.complete_topology2(t.normalize_topology2(t.decode_topology_documents2(tuple(docs),f.profile,plan),plan))

    def test_original_partial_topology_never_full_profile_acceptance(self):
        topology=self.native()
        result=m.validate_management_profile2(topology,self.f.policy,self.f.pinned_digest)
        self.assertEqual(topology.stage,'topology_unproven')
        self.assertEqual(result.result,'profile_unproven')
        self.assertEqual(result.structural_result,'profile_unproven')
        self.assertFalse(result.management_policy_verified)
        self.assertFalse(result.isolation_verified)
        self.assertFalse(result.physical_probe_permitted)

    def test_native_fields_and_extent_remain_visible(self):
        topology=self.native()
        host=topology.normalized.namespaces[0]
        self.assertEqual(host.links[0].attributes.get('ifname'),'tc-br0')
        self.assertEqual(host.links[0].attributes.get('linkinfo').get('info_data').get('gc_timer').token,'178.16')
        self.assertEqual([p.attributes.get('link') for p in host.ports],['if6','if8'])
        self.assertTrue(all(source.descriptor.extent!='namespace_source' for source in host.sources))

    def test_partial_sources_cannot_be_expected_manifest(self):
        with self.assertRaises(c.ContractViolation2):
            m.ExpectedTopologySource2('link_single',self.native().normalized.namespaces[0].sources[0].rows)


class IsolationTests(unittest.TestCase):
    def test_production_imports_no_io_discovery_or_old_boundary(self):
        tree=ast.parse((Path(__file__).parents[1]/'native_v2_management.py').read_text())
        allowed={'dataclasses','native_v2_contracts','native_v2_topology','native_v2_topology_schema'}
        for node in ast.walk(tree):
            if isinstance(node,ast.Import): self.assertTrue(all(v.name in allowed for v in node.names))
            if isinstance(node,ast.ImportFrom):
                self.assertTrue(node.module in allowed or node.module is None)
                if node.module is None: self.assertTrue(all(v.name in allowed for v in node.names))
            if isinstance(node,ast.Call) and isinstance(node.func,ast.Name):
                self.assertNotIn(node.func.id,('open','eval','exec','compile','__import__'))

    def test_fresh_import_no_socket_process_or_os_operations(self):
        script='''
import os,socket,subprocess,sys
from contextlib import ExitStack
from unittest.mock import patch
def no_io(*a,**k): raise AssertionError('forbidden I/O')
with ExitStack() as stack:
 for owner,name in ((socket,'socket'),(subprocess,'Popen'),(os,'system'),(os,'setns')):
  stack.enter_context(patch.object(owner,name,no_io,create=True))
 import trusted_checker_network.native_v2_management
 assert 'docker' not in sys.modules and 'django' not in sys.modules
'''
        result=subprocess.run([sys.executable,'-W','error::ResourceWarning','-c',script],capture_output=True,check=False)
        self.assertEqual(result.returncode,0,result.stderr.decode())
