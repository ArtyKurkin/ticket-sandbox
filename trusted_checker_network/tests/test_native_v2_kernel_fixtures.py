"""Native originals prove shape observations, never installation/isolation."""
import ast
from copy import deepcopy
from dataclasses import FrozenInstanceError,replace
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tarfile
import unittest
from unittest.mock import patch

from trusted_checker_network import native_v2_contracts as c
from trusted_checker_network import native_v2_native61 as n
from trusted_checker_network import native_v2_native61_schema as s
from trusted_checker_network import native_v2_topology_schema as old
from trusted_checker_network import native_v2_topology as topology
from trusted_checker_network import native_v2_management as management
from trusted_checker_network.native_v2_topology_json import bounded_topology_json2,ExactDecimal2
from .native_v2_support import hd
from .native_v2_native61_support import (
    FIXTURES,ORIGINALS,SCOPES,FormatFixture61,make_reference,native_documents,native_bundle,addr,
)
from .native_v2_management_support import ManagementFixture2


# Original VDS captures are intentionally excluded from Git.
# Tests requiring original bytes must be explicitly skipped when absent.
ORIGINAL_EVIDENCE_AVAILABLE = (
    (ORIGINALS / "SHA256SUMS").is_file()
    and (ORIGINALS / "iproute2.txt").is_file()
    and (ORIGINALS / "kernel.txt").is_file()
    and (ORIGINALS / "host/address.json").is_file()
    and (FIXTURES / "tc-native-capture-20261021T082517Z.tar.gz").is_file()
)

ORIGINAL_EVIDENCE_REASON = (
    "Original private VDS capture is not present in this checkout"
)


class ProvenanceTests(unittest.TestCase):
    @unittest.skipUnless(ORIGINAL_EVIDENCE_AVAILABLE, ORIGINAL_EVIDENCE_REASON)
    def test_archive_bytes_hash_and_safe_original_paths(self):
        p=json.loads((FIXTURES/'provenance.json').read_text())
        raw=(FIXTURES/p['archive_name']).read_bytes()
        self.assertEqual((len(raw),hashlib.sha256(raw).hexdigest()),(p['archive_bytes'],s.ARCHIVE_SHA256))
        with tarfile.open(FIXTURES/p['archive_name']) as archive:
            members=archive.getmembers()
            self.assertEqual(len({m.name for m in members}),len(members))
            for member in members:
                self.assertTrue(member.isfile() or member.isdir())
                self.assertFalse(member.name.startswith('/'));self.assertNotIn('..',Path(member.name).parts)
                if member.isfile():self.assertEqual(archive.extractfile(member).read(),(FIXTURES/'native'/member.name).read_bytes())

    @unittest.skipUnless(ORIGINAL_EVIDENCE_AVAILABLE, ORIGINAL_EVIDENCE_REASON)
    def test_original_manifest_exact_107_entries(self):
        sums={}
        for line in (ORIGINALS/'SHA256SUMS').read_text().splitlines():
            expected,name=line.split('  ',1);self.assertTrue(name.startswith('./'));name=name[2:]
            self.assertNotIn(name,sums);sums[name]=expected
            self.assertEqual(hashlib.sha256((ORIGINALS/name).read_bytes()).hexdigest(),expected)
        self.assertEqual(len(sums),107)
        files={str(p.relative_to(ORIGINALS)) for p in ORIGINALS.rglob('*') if p.is_file()}
        self.assertEqual(files,set(sums)|{'SHA256SUMS'})

    @unittest.skipUnless(ORIGINAL_EVIDENCE_AVAILABLE, ORIGINAL_EVIDENCE_REASON)
    def test_all_originals_bound_in_provenance(self):
        p=json.loads((FIXTURES/'provenance.json').read_text())
        self.assertEqual(len(p['files']),108)
        for name,item in p['files'].items():
            raw=(ORIGINALS/name).read_bytes()
            self.assertEqual((len(raw),hashlib.sha256(raw).hexdigest()),(item['bytes'],item['sha256']))
        for flag in ('exact_argv_recorded','per_command_timestamps_recorded','os_principals_recorded',
                     'trusted_namespace_fd_witnesses_recorded','measurement_before_after_recorded','atomic_snapshot'):
            self.assertIs(p[flag],False)

    @unittest.skipUnless(ORIGINAL_EVIDENCE_AVAILABLE, ORIGINAL_EVIDENCE_REASON)
    def test_all_exit_stderr_records(self):
        exits=list(ORIGINALS.glob('*/*.exit'));errors=list(ORIGINALS.glob('*/*.err'))
        self.assertEqual(len(exits),34);self.assertEqual(len(errors),34)
        self.assertTrue(all(p.read_bytes()==b'0\n' for p in exits))
        self.assertTrue(all(p.read_bytes()==b'' for p in errors))

    @unittest.skipUnless(ORIGINAL_EVIDENCE_AVAILABLE, ORIGINAL_EVIDENCE_REASON)
    def test_all_34_json_documents_are_strictly_decodable(self):
        paths=list(ORIGINALS.glob('*/*.json'));self.assertEqual(len(paths),34)
        for path in paths:
            with self.subTest(path=str(path)):
                self.assertIsNotNone(bounded_topology_json2(path.read_bytes()))

    @unittest.skipUnless(ORIGINAL_EVIDENCE_AVAILABLE, ORIGINAL_EVIDENCE_REASON)
    def test_source_mapping_preserves_unknown_execution_argv(self):
        mapping=json.loads((FIXTURES/'source_mapping.json').read_text())
        self.assertFalse(mapping['actual_argv_recorded'])
        self.assertEqual(len(mapping['json_sources']),34)
        for item in mapping['json_sources']:
            self.assertIsNone(item['exact_argv']);self.assertIsNone(item['namespace_execution_wrapper'])
            self.assertIsNone(item['per_command_start_end'])
            raw=(ORIGINALS/item['artifact']).read_bytes()
            self.assertEqual(hashlib.sha256(raw).hexdigest(),item['stdout_sha256'])
            if item['source_id']!='nft':self.assertEqual(tuple(item['nominal_future_source_argv']),dict(s.NOMINAL_ARGV)[item['source_id']])

    @unittest.skipUnless(ORIGINAL_EVIDENCE_AVAILABLE, ORIGINAL_EVIDENCE_REASON)
    def test_declared_versions_not_binary_attestation(self):
        self.assertIn(b'6.8.0-147-generic',(ORIGINALS/'kernel.txt').read_bytes())
        self.assertIn(b'1.0.9',(ORIGINALS/'nft-version.txt').read_bytes())
        self.assertIn(b'iproute2-6.1.0',(ORIGINALS/'iproute2.txt').read_bytes())
        self.assertEqual((ORIGINALS/'bridge-version.txt').read_bytes(),b'bridge utility, 6.1.0\n')

    def test_observed_paths_exactly_match_200_static_registry_fields(self):
        matrix=json.loads((FIXTURES/'observed_matrix.json').read_text())
        paths={(source,tuple(path[2:].split('.'))) for source,rec in matrix.items() for path in rec['paths']
               if path.startswith('*.') and not path.endswith('.*')}
        self.assertEqual(paths,{(f.source,f.path) for f in s.REGISTRY61})
        self.assertEqual(len(s.REGISTRY61),200)
        specs={(f.source,f.path):f for f in s.REGISTRY61}
        for source,rec in matrix.items():
            for path,entry in rec['paths'].items():
                if 'parent_object_count' in entry:
                    self.assertEqual(entry['parent_object_count'],entry['present_count']+entry['absent_count'])
                    spec=specs[(source,tuple(path[2:].split('.')))]
                    self.assertEqual(entry['diagnostic_registry']['disposition'],spec.disposition)

    def test_matrix_records_native_cardinalities(self):
        matrix=json.loads((FIXTURES/'observed_matrix.json').read_text())
        self.assertEqual(matrix['bridge_fdb']['paths']['$']['cardinality'],{'min':23,'max':23})
        self.assertEqual(matrix['link']['paths']['$']['cardinality'],{'min':2,'max':5})
        self.assertEqual(matrix['route6']['paths']['*.metrics']['cardinality'],{'min':1,'max':1})


@unittest.skipUnless(ORIGINAL_EVIDENCE_AVAILABLE, ORIGINAL_EVIDENCE_REASON)
class NativeFormatTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.profile,cls.documents=native_documents()
        cls.sources=n.decode_native_documents61(cls.documents,cls.profile)
        cls.bundle=n.NativeDiagnosticBundle61(cls.profile,SCOPES,cls.sources)

    def doc(self,scope,source):
        return next(d for d in self.sources if (d.reference.scope_label,d.reference.source)==(scope,source))

    def test_all_33_native_topology_jsons_decode_without_field_loss(self):
        self.assertEqual(len(self.sources),33)
        for d in self.sources:
            self.assertEqual(d.rows,s.decode_native61_rows(d.raw_text.encode(),d.reference.source))
            self.assertEqual(d.stage,'native_format_decoded_diagnostic_only')
            self.assertFalse(d.physical_probe_permitted)

    def test_old_provisional_schema_acceptance_exact_matrix(self):
        accepted=0;refused=0;mapping={'bridge_vlan':'vlan','bridge_fdb':'fdb'}
        for raw,ref in self.documents:
            try:old.validate_rows2(mapping.get(ref.source,ref.source),bounded_topology_json2(raw));accepted+=1
            except c.ContractViolation2:refused+=1
        self.assertEqual((accepted,refused),(14,19))
        self.assertEqual(old.REGISTRY_DIGEST,'eb52342f871ea66a59cdf0790dbd9f90da7f5f05feedf198a18df44556d3bcbd')

    def test_legacy_fdb_and_bridge_boolean_incompatibilities(self):
        for source,target in (('bridge_fdb','fdb'),('bridge_link','bridge_link'),('bridge_vlan','vlan')):
            with self.assertRaises(c.ContractViolation2): old.validate_rows2(target,bounded_topology_json2(self.doc('host',source).raw_text.encode()))

    def test_string_ip_master_retained_not_guessed_integer(self):
        host=self.doc('host','link')
        self.assertEqual([r.get('master') for r in host.rows if r.has('master')],['tc-br0','tc-br0'])
        self.assertEqual([r.get('ifindex') for r in host.rows],[1,2,5,7,9])

    def test_parent_bus_altnames_and_slave_data_retained(self):
        rows=self.doc('host','link').rows
        self.assertEqual(rows[1].get('altnames'),('enp0s3','ens3'))
        self.assertEqual((rows[1].get('parentbus'),rows[1].get('parentdev')),('virtio','virtio0'))
        data=rows[3].get('linkinfo').get('info_slave_data')
        self.assertEqual(data.get('id'),'0x8001');self.assertEqual(data.get('designated_port'),32769)
        self.assertIs(data.get('learning'),True);self.assertIs(data.get('proxy_arp'),False)

    def test_exact_seven_bridge_and_slave_decimal_paths(self):
        bridge=self.doc('host','link').rows[2].get('linkinfo').get('info_data')
        self.assertEqual(bridge.get('gc_timer').token,'293.28')
        self.assertEqual(bridge.get('hello_timer').token,'0.00')
        self.assertEqual(len([f for f in s.REGISTRY61 if f.kind=='decimal']),7)
        self.assertEqual(self.doc('host','link').rows[3].get('linkinfo').get('info_slave_data').get('hold_timer').token,'0.00')

    def test_route_absences_not_filled_with_kernel_defaults(self):
        r4=self.doc('host','route4').rows[0];r6=self.doc('host','route6').rows[0]
        for key in ('table','type','scope'):
            self.assertFalse(r4.has(key));self.assertFalse(r6.has(key))
        local=self.doc('host','route4').rows[6]
        self.assertEqual(local.get('table'),'local');self.assertEqual(local.get('type'),'local')
        self.assertEqual(local.get('dst'),'89.169.0.131')
        self.assertNotEqual(local.get('dst'),'89.169.0.131/32')

    def test_ra_expiry_and_nested_metrics_never_erased(self):
        ra=next(r for r in self.doc('host','route6').rows if r.has('expires'))
        self.assertEqual(ra.get('expires'),1726)
        self.assertEqual(ra.get('metrics')[0].get('hoplimit'),64)
        self.assertEqual(ra.get('protocol'),'ra')

    def test_native_address_envelope_and_per_address_booleans(self):
        rows=self.doc('host','address').rows
        self.assertIs(rows[0].get('addr_info')[1].get('noprefixroute'),True)
        a=rows[1].get('addr_info')[0]
        self.assertIs(a.get('dynamic'),True);self.assertEqual(a.get('metric'),100)
        self.assertEqual(a.get('valid_life_time'),52658)

    def test_fdb_all_management_entries_retained_separately(self):
        rows=self.doc('host','bridge_fdb').rows
        self.assertEqual(len(rows),23)
        self.assertEqual(len([r for r in rows if r.get('ifname')=='eth0']),6)
        self.assertEqual(len([r for r in rows if r.has('master')]),6)
        self.assertEqual(len([r for r in rows if r.has('vlan')]),3)
        self.assertEqual(len([category for scope,ordinal,category in self.bundle.fdb_classifications if category=='non_bridge_interface_self_entry']),6)

    def test_fdb_state_scalar_and_exact_native_vlan_literal(self):
        self.assertTrue(all(r.get('state')=='permanent' for r in self.doc('host','bridge_fdb').rows))
        self.assertEqual(self.doc('host','bridge_vlan').rows[0].get('vlans')[0].get('flags'),('PVID','Egress Untagged'))

    def test_bridge_flags_are_actual_bool_not_string_or_integer(self):
        row=self.doc('host','bridge_link').rows[0]
        self.assertIs(row.get('learning'),True);self.assertIs(row.get('guard'),False)
        self.assertIs(type(row.get('mcast_router')),int)
        self.assertEqual(row.get('link'),'if6')

    def test_local_observational_joins_are_not_namespace_attestation(self):
        self.assertEqual(len(self.bundle.joins),112)
        self.assertTrue(all(j.namespace_binding=='unproven_capture_scope_only' for j in self.bundle.joins))
        self.assertTrue(any(j.relation=='bridge_member' and j.target_ifindex==5 for j in self.bundle.joins))
        self.assertNotIn('bridge_join_unproven',self.bundle.uncertainty_reasons)

    def test_three_peer_index_candidates_never_fd_witnesses(self):
        pairs=self.bundle.peer_index_candidates
        self.assertEqual(len(pairs),3)
        self.assertEqual({frozenset((p.first_ifindex,p.second_ifindex)) for p in pairs},
                         {frozenset((6,7)),frozenset((8,9)),frozenset((3,4))})
        self.assertTrue(all(p.status=='unproven_no_namespace_fd_nsid_witness' for p in pairs))
        self.assertFalse(hasattr(pairs[0],'namespace_key'))

    def test_twelve_missing_bridge_sources_not_empty_results(self):
        expected={(scope,source) for scope in SCOPES if scope!='host' for source in ('bridge_link','bridge_vlan','bridge_fdb')}
        self.assertEqual(set(self.bundle.missing_sources),expected)
        self.assertEqual(self.bundle.stage,'topology_unproven')
        self.assertIn('os_attachments_permissions_fds_unobserved',self.bundle.uncertainty_reasons)

    def test_four_named_namespaces_preserved_as_labels_only(self):
        self.assertEqual(len(self.bundle.declared_scope_labels),5)
        self.assertIn('tc-runner',self.bundle.declared_scope_labels)
        self.assertIn('tc-target',self.bundle.declared_scope_labels)
        labels=(ORIGINALS/'namespaces.txt').read_text()
        self.assertEqual(len(labels.splitlines()),4)
        self.assertTrue(all(d.reference.namespace_identity=='unobserved' for d in self.sources))

    def test_real_lab_negative_against_independent_synthetic_policy(self):
        f=ManagementFixture2.create()
        review=n.review_native_policy61(self.bundle,f.policy,f.pinned_digest)
        self.assertEqual(review.result,'profile_mismatch')
        for reason in ('additional_named_capture_scopes','canonical_bridge_name_mismatch',
                       'host_link_inventory_mismatch','test_side_ipv6_forbidden','test_side_ipv6_route_forbidden'):
            self.assertIn(reason,review.findings)
        self.assertEqual(review.isolation_result,'isolation_unproven')
        self.assertFalse(review.management_policy_verified);self.assertFalse(review.isolation_verified)

    def test_nft_format_stays_laboratory_not_canonical(self):
        from trusted_checker_network import native_v2_readback as r
        from .native_v2_readback_support import ReadbackFixture2
        raw=(ORIGINALS/'host/nft.json').read_bytes()
        # EXPLICIT SYNTHETIC context only to exercise the existing pure schema;
        # these context values do not describe the saved VDS or a namespace FD.
        fixture=ReadbackFixture2.create()
        decoded=r.decode_native2(raw,fixture.expected.profile,fixture.context)
        normalized=r.normalize_rules2(decoded)
        self.assertEqual({table.identity.name for table in normalized.tables},{'tc_ct_lab','tc_strict_lab'})
        with self.assertRaises(c.ContractViolation2):
            r.validate_recipe2(normalized,fixture.expected,fixture.binding,fixture.expected.intent)


class _SyntheticCase(unittest.TestCase):
    def setUp(self):
        self.f=FormatFixture61.create()
        self.baseline=self.f.bundle()
        self.assertEqual(len(self.baseline.sources),27)
        self.assertEqual(self.baseline.missing_sources,())

    def invalid(self,source,change):
        data=deepcopy(self.f.rows['host'][source]);change(data)
        with self.assertRaises(c.ContractViolation2):self.f.decode('host',source,data)

    def bundle_change(self,change):
        rows=deepcopy(self.f.rows);change(rows)
        return self.f.bundle(rows)


class SyntheticSchemaTests(_SyntheticCase):
    def test_authored_positive_format_complete_but_topology_unproven(self):
        self.assertEqual(self.baseline.stage,'topology_unproven')
        self.assertIn('namespace_fd_nsid_witness_unobserved',self.baseline.uncertainty_reasons)
        self.assertFalse(self.baseline.management_policy_verified)
        self.assertFalse(self.baseline.isolation_verified)
        self.assertFalse(self.baseline.physical_probe_permitted)

    @staticmethod
    def target(rows,path):
        def find(value,remaining):
            if len(remaining)==1 and type(value) is dict and remaining[0] in value:
                return value,remaining[0]
            if not remaining:return None
            key=remaining[0]
            if key=='*' and type(value) is list:
                for row in value:
                    result=find(row,remaining[1:])
                    if result:return result
            elif type(value) is dict and key in value:return find(value[key],remaining[1:])
            return None
        for row in rows:
            result=find(row,path)
            if result:return result
        raise AssertionError('authored fixture missing registered path '+str(path))

    def test_all_200_fields_have_independent_positive_and_wrong_type_mutations(self):
        for spec in s.REGISTRY61:
            with self.subTest(source=spec.source,path=spec.path):
                rows=deepcopy(self.f.rows['host'][spec.source])
                parent,key=self.target(rows,spec.path)
                self.f.decode('host',spec.source,rows)
                parent[key]=0 if spec.kind in ('bool','decimal') else True if spec.kind in ('index','uint32','uint8','vlan','prefix') else None
                with self.assertRaises(c.ContractViolation2):self.f.decode('host',spec.source,rows)

    def test_required_field_removal_for_every_registered_required_path(self):
        for spec in s.REGISTRY61:
            if not spec.required:continue
            with self.subTest(source=spec.source,path=spec.path):
                rows=deepcopy(self.f.rows['host'][spec.source])
                parent,key=self.target(rows,spec.path);parent.pop(key)
                with self.assertRaises(c.ContractViolation2):self.f.decode('host',spec.source,rows)

    def test_unknown_field_each_source(self):
        for source in s.SOURCES:
            self.invalid(source,lambda rows:rows[0].__setitem__('unreviewed_field',0))

    def test_unknown_nested_metrics_slave_bridge_address_paths(self):
        cases=(('link',lambda rows:rows[2]['linkinfo']['info_data'].__setitem__('unknown',0)),
               ('link',lambda rows:rows[3]['linkinfo']['info_slave_data'].__setitem__('unknown',0)),
               ('address',lambda rows:rows[0]['addr_info'][0].__setitem__('unknown',0)),
               ('route6',lambda rows:rows[0]['metrics'][0].__setitem__('unknown',0)))
        for source,change in cases:self.invalid(source,change)

    def test_malformed_duplicate_key_bom_and_bad_utf8(self):
        for raw in (b'[',b'[] trailing',b'\xef\xbb\xbf[]',b'\xff',b'[{"a":1,"a":2}]',b'null'):
            with self.assertRaises(c.ContractViolation2):s.decode_native61_rows(raw,'link')

    def test_route_optional_presence_preserved_and_never_defaulted(self):
        rows=deepcopy(self.f.rows['host']['route4'])
        absent=self.f.decode('host','route4',rows).rows[0]
        self.assertFalse(absent.has('table'));self.assertFalse(absent.has('type'));self.assertFalse(absent.has('scope'))
        rows[0]['table']='local'
        present=self.f.decode('host','route4',rows).rows[0]
        self.assertTrue(present.has('table'));self.assertFalse(present.has('type'))
        self.assertNotEqual(absent,present)
        rows[0]['type']='local';rows[0]['scope']='host'
        self.assertTrue(self.f.decode('host','route4',rows).rows[0].has('scope'))

    def test_route_unknown_guessed_unicast_main_and_scope6_not_aliases(self):
        self.invalid('route4',lambda rows:rows[0].__setitem__('type','unicast'))
        self.invalid('route4',lambda rows:rows[0].__setitem__('table','main'))
        self.invalid('route6',lambda rows:rows[0].__setitem__('scope','global'))
        self.invalid('route6',lambda rows:rows[0].__setitem__('table',254))

    def test_ra_metrics_must_be_single_object_array(self):
        for value in (None,{},[],[{},{}],[{'hoplimit':64},{'hoplimit':64}]):
            self.invalid('route6',lambda rows:rows[0].__setitem__('metrics',value))
        self.invalid('route6',lambda rows:rows[0]['metrics'][0].__setitem__('hoplimit',True))
        self.invalid('route6',lambda rows:rows[0]['metrics'][0].__setitem__('hoplimit',256))

    def test_expires_integer_not_bool_decimal_or_null(self):
        for value in (True,None,1.5,-1,'1726'):
            self.invalid('route6',lambda rows:rows[0].__setitem__('expires',value))

    def test_missing_expires_and_metrics_remain_observed_absence(self):
        rows=deepcopy(self.f.rows['host']['route6']);rows[0].pop('expires');rows[0].pop('metrics')
        a=self.f.decode('host','route6',rows).rows[0]
        self.assertFalse(a.has('expires'));self.assertFalse(a.has('metrics'))
        self.assertTrue(a.has('gateway'))

    def test_bridge_boolean_no_on_off_or_int_coercion(self):
        for key in ('hairpin','guard','learning','flood','locked','mcast_to_unicast'):
            for value in ('on','off',0,1,None):
                self.invalid('bridge_link',lambda rows:rows[0].__setitem__(key,value))
        rows=deepcopy(self.f.rows['host']['bridge_link']);rows[0]['hairpin']=True
        doc=self.f.decode('host','bridge_link',rows)
        self.assertIs(doc.rows[0].get('hairpin'),True)
        self.assertFalse(doc.management_policy_verified)

    def test_fdb_self_master_vlan_combinations(self):
        rows=deepcopy(self.f.rows['host']['bridge_fdb'])
        doc=self.f.decode('host','bridge_fdb',rows)
        self.assertFalse(doc.rows[0].has('master'));self.assertEqual(doc.rows[1].get('vlan'),1)
        self.invalid('bridge_fdb',lambda rows:rows[0].__setitem__('master','tcsh0'))
        self.invalid('bridge_fdb',lambda rows:rows[0].__setitem__('vlan',1))
        self.invalid('bridge_fdb',lambda rows:rows[1].pop('master'))

    def test_fdb_ifname_not_dev_state_scalar_not_list(self):
        self.invalid('bridge_fdb',lambda rows:rows[0].__setitem__('dev','mgmt0'))
        self.invalid('bridge_fdb',lambda rows:rows[0].__setitem__('state',['permanent']))
        self.invalid('bridge_fdb',lambda rows:rows[0].__setitem__('state','dynamic'))

    def test_native_vlan_string_not_silent_underscore_alias(self):
        self.invalid('bridge_vlan',lambda rows:rows[0]['vlans'][0].__setitem__('flags',['PVID','Egress_Untagged']))
        self.invalid('bridge_vlan',lambda rows:rows[0]['vlans'][0].__setitem__('vlan',True))

    def test_master_string_not_old_integer_form(self):
        self.invalid('link',lambda rows:rows[3].__setitem__('master',5))
        self.invalid('address',lambda rows:rows[3].__setitem__('master',5))
        self.invalid('bridge_link',lambda rows:rows[0].__setitem__('master',5))

    def test_unknown_link_kind_and_parent_pair(self):
        self.invalid('link',lambda rows:rows[1].__setitem__('linkinfo',{'info_kind':'macvlan'}))
        self.invalid('link',lambda rows:rows[1].pop('parentbus'))

    def test_altnames_and_fields_type_bounds(self):
        for value in (None,'ens3',['ens3','ens3'],['a'*16],[False]):
            self.invalid('link',lambda rows:rows[1].__setitem__('altnames',value))
        self.invalid('link',lambda rows:rows[0].__setitem__('ifindex',0))
        self.invalid('link',lambda rows:rows[0].__setitem__('min_mtu',-1))
        self.invalid('address',lambda rows:rows[0]['addr_info'][0].__setitem__('valid_life_time',2**32))

    def test_address_boolean_lifetime_and_family(self):
        self.invalid('address',lambda rows:rows[0]['addr_info'][1].__setitem__('noprefixroute',1))
        self.invalid('address',lambda rows:rows[1]['addr_info'][0].__setitem__('dynamic','true'))
        self.invalid('address',lambda rows:rows[0]['addr_info'][0].__setitem__('family','inet6'))
        self.invalid('address',lambda rows:rows[1]['addr_info'][0].__setitem__('valid_life_time','forever'))

    def test_timer_exact_decimal_only_at_seven_paths(self):
        doc=self.f.decode('host','link')
        timer=doc.rows[2].get('linkinfo').get('info_data').get('gc_timer')
        self.assertIs(type(timer),ExactDecimal2);self.assertEqual(timer.token,'200.25')
        for value in (0,True,'200.25',None):
            self.invalid('link',lambda rows:rows[2]['linkinfo']['info_data'].__setitem__('gc_timer',value))
        self.invalid('link',lambda rows:rows[2]['linkinfo']['info_data'].__setitem__('nf_call_iptables',0.5))

    def test_rule_order_and_raw_tokens_retained(self):
        rows=deepcopy(self.f.rows['host']['rule4']);rows.reverse()
        doc=self.f.decode('host','rule4',rows)
        self.assertEqual([r.get('priority') for r in doc.rows],[32766,0])
        self.invalid('rule4',lambda rows:rows[0].__setitem__('table',255))
        self.invalid('rule6',lambda rows:rows[0].__setitem__('src','::/0'))
        self.invalid('rule4',lambda rows:rows[0].__setitem__('fwmark','0x1'))

    def test_route_literal_and_family_without_prefix_invention(self):
        a=self.f.decode('host','route4').rows[1]
        self.assertEqual(a.get('dst'),'127.0.0.1')
        self.invalid('route4',lambda rows:rows[0].__setitem__('gateway','fe80::1'))
        self.invalid('route6',lambda rows:rows[0].__setitem__('dst','192.0.2.0/24'))

    def test_bounds_apply_before_batch_parse(self):
        doc=self.f.documents()[0]
        with self.assertRaisesRegex(c.ContractViolation2,'documents_limit'):n.decode_native_documents61((doc,)*257,self.f.profile)
        with patch.object(n,'decode_native_source61',side_effect=AssertionError('parser reached')):
            with self.assertRaisesRegex(c.ContractViolation2,'aggregate_limit'):
                n.decode_native_documents61(((b' '*1048576,doc[1]),)*17,self.f.profile)

    def test_byte_cap_depth_array_duplicate_and_decimal_exponents(self):
        for raw in (b' '*1048577,b'['*33+b'0'+b']'*33,json.dumps([0]*1025).encode(),b'[1e2]',b'[NaN]'):
            with self.assertRaises(c.ContractViolation2):s.decode_native61_rows(raw,'link')


class SyntheticJoinPolicyTests(_SyntheticCase):
    def test_duplicate_local_link_identity_not_joined(self):
        bundle=self.bundle_change(lambda rows:rows['host']['link'][1].__setitem__('ifindex',1))
        self.assertIn('local_link_identity_ambiguous',bundle.uncertainty_reasons)

    def test_bridge_name_join_wrong_master(self):
        bundle=self.bundle_change(lambda rows:rows['host']['bridge_link'][0].__setitem__('master','mgmt0'))
        self.assertIn('bridge_join_unproven',bundle.uncertainty_reasons)

    def test_missing_port_not_ignored(self):
        bundle=self.bundle_change(lambda rows:rows['host']['bridge_link'].pop())
        self.assertIn('bridge_membership_incomplete',bundle.uncertainty_reasons)

    def test_address_identity_and_shared_header_consistency(self):
        a=self.bundle_change(lambda rows:rows['host']['address'][1].__setitem__('ifname','wrong'))
        self.assertIn('address_join_unproven',a.uncertainty_reasons)
        b=self.bundle_change(lambda rows:rows['host']['address'][1].__setitem__('mtu',1400))
        self.assertIn('address_link_fields_conflict',b.uncertainty_reasons)

    def test_vlan_and_fdb_wrong_links_or_vlan(self):
        for source,change,reason in (
            ('bridge_vlan',lambda rows:rows[0].__setitem__('ifname','unknown'),'vlan_join_unproven'),
            ('bridge_fdb',lambda rows:rows[0].__setitem__('ifname','unknown'),'fdb_interface_unproven'),
            ('bridge_fdb',lambda rows:rows[1].__setitem__('master','mgmt0'),'fdb_bridge_unproven'),
            ('bridge_fdb',lambda rows:rows[1].__setitem__('vlan',2),'fdb_vlan_unproven')):
            rows=deepcopy(self.f.rows);change(rows['host'][source])
            self.assertIn(reason,self.f.bundle(rows).uncertainty_reasons)

    def test_unknown_route_device_and_rpdb_ambiguity(self):
        a=self.bundle_change(lambda rows:rows['host']['route6'][0].__setitem__('dev','unknown'))
        self.assertIn('route_device_unproven',a.uncertainty_reasons)
        b=self.bundle_change(lambda rows:rows['host']['rule4'][1].__setitem__('priority',0))
        self.assertIn('rpdb_priority_ambiguous',b.uncertainty_reasons)

    def test_numeric_peer_indices_ambiguous_across_scope_labels(self):
        rows=deepcopy(self.f.rows);rows['another']=deepcopy(rows['runner'])
        docs=self.f.documents(rows)
        bundle=n.NativeDiagnosticBundle61(self.f.profile,('host','runner','target','another'),n.decode_native_documents61(docs,self.f.profile))
        self.assertIn('peer_index_candidates_ambiguous',bundle.uncertainty_reasons)
        self.assertTrue(all(p.status=='unproven_no_namespace_fd_nsid_witness' for p in bundle.peer_index_candidates))

    def test_nsid_integer_not_namespace_identity_even_when_unique(self):
        self.assertEqual(len(self.baseline.peer_index_candidates),2)
        self.assertIn('namespace_fd_nsid_witness_unobserved',self.baseline.uncertainty_reasons)
        with self.assertRaises(c.ContractViolation2):
            replace(self.baseline.peer_index_candidates[0],status='verified')

    def test_missing_source_not_equal_empty_capture(self):
        docs=self.f.documents();docs=tuple((raw,r) for raw,r in docs if not (r.scope_label=='target' and r.source=='bridge_fdb'))
        bundle=n.NativeDiagnosticBundle61(self.f.profile,('host','runner','target'),n.decode_native_documents61(docs,self.f.profile))
        self.assertEqual(bundle.missing_sources,(('target','bridge_fdb'),))
        explicit=next(d for d in self.baseline.sources if (d.reference.scope_label,d.reference.source)==('target','bridge_fdb'))
        self.assertEqual(explicit.rows,())

    def test_extra_capture_scope_not_hidden(self):
        f=ManagementFixture2.create();rows=deepcopy(self.f.rows);rows['old-ns']=deepcopy(rows['runner'])
        bundle=n.NativeDiagnosticBundle61(self.f.profile,('host','runner','target','old-ns'),n.decode_native_documents61(self.f.documents(rows),self.f.profile))
        review=n.review_native_policy61(bundle,f.policy,f.pinned_digest)
        self.assertIn('additional_named_capture_scopes',review.findings)
        self.assertEqual(review.result,'profile_mismatch')

    def test_no_findings_still_no_acceptance_or_authority(self):
        f=ManagementFixture2.create();review=n.review_native_policy61(self.baseline,f.policy,f.pinned_digest)
        self.assertEqual(review.findings,())
        self.assertEqual(review.result,'profile_unproven')
        self.assertFalse(review.management_policy_verified);self.assertFalse(review.isolation_verified)
        self.assertFalse(review.physical_probe_permitted)

    def test_host_peer_ipv6_records_are_negative_policy_facts(self):
        f=ManagementFixture2.create()
        for scope,index in (('host',2),('host',3),('runner',1),('target',1)):
            rows=deepcopy(self.f.rows);rows[scope]['address'][index]['addr_info'].append(addr('inet6','fe80::2',64,'link'))
            review=n.review_native_policy61(self.f.bundle(rows),f.policy,f.pinned_digest)
            self.assertIn('test_side_ipv6_forbidden',review.findings)
            self.assertEqual(review.result,'profile_mismatch')

    def test_test_side_ipv6_route_not_removed(self):
        f=ManagementFixture2.create();rows=deepcopy(self.f.rows)
        rows['host']['route6'].append(dict(dst='fe80::/64',dev='vethrun',protocol='kernel',metric=256,flags=[],pref='medium'))
        review=n.review_native_policy61(self.f.bundle(rows),f.policy,f.pinned_digest)
        self.assertIn('test_side_ipv6_route_forbidden',review.findings)

    def test_canonical_bridge_name_not_fitted_to_lab(self):
        f=ManagementFixture2.create();rows=deepcopy(self.f.rows)
        rows['host']['link'][2]['ifname']='tc-br0'
        review=n.review_native_policy61(self.f.bundle(rows),f.policy,f.pinned_digest)
        self.assertIn('canonical_bridge_name_mismatch',review.findings)

    def test_external_policy_pin_not_chosen_from_capture(self):
        f=ManagementFixture2.create()
        review=n.review_native_policy61(self.baseline,f.policy,hd('foreign-pin'))
        self.assertIn('profile_digest_mismatch',review.findings)

    def test_false_flags_constructor_immutable(self):
        for value in (self.baseline,self.baseline.sources[0],self.baseline.joins[0]):
            with self.assertRaises(FrozenInstanceError):value.physical_probe_permitted=True
            with self.assertRaises(c.ContractViolation2):replace(value,physical_probe_permitted=True)
        with self.assertRaises(TypeError):replace(self.baseline,management_policy_verified=True)
        with self.assertRaises(TypeError):replace(self.baseline,joins=())

    def test_old_v2_03_and_v2_04_types_cannot_adopt_diagnostic_bundle(self):
        f=ManagementFixture2.create()
        with self.assertRaises(c.ContractViolation2):management.validate_management_profile2(self.baseline,f.policy,f.pinned_digest)
        with self.assertRaises(c.ContractViolation2):topology.complete_topology2(self.baseline)

    def test_existing_physical_gate_rejects_diagnostic_and_policy_review(self):
        from trusted_checker_physical.collector import PhysicalProbeGate
        from trusted_checker_runtime.profiles import Denied
        f=ManagementFixture2.create()
        for value in (self.baseline,n.review_native_policy61(self.baseline,f.policy,f.pinned_digest)):
            with self.assertRaisesRegex(Denied,'physical_network_boundary_not_accepted'):PhysicalProbeGate.permit(value)


class IntegrityIsolationTests(_SyntheticCase):
    def test_profile_and_registry_separate_from_provisional(self):
        self.assertNotEqual(self.f.profile.profile_id,'iproute2-native-topology-v2-provisional-offline-1')
        self.assertNotEqual(s.REGISTRY_DIGEST61,old.REGISTRY_DIGEST)
        for key,value in (('profile_id','permissive'),('schema_revision',True),('schema_revision',1),
                          ('iproute2_version','6.2.0'),('field_registry_digest',hd('wrong')),
                          ('acceptance','native_approved')):
            with self.assertRaises(c.ContractViolation2):replace(self.f.profile,**{key:value})

    def test_registry_and_literal_pools_immutable_and_hash_bound(self):
        self.assertIs(type(s.REGISTRY61),tuple)
        self.assertIs(type(s.LITERAL_VALUES61),tuple);self.assertIs(type(s.FLAG_VALUES61),tuple)
        with self.assertRaises(FrozenInstanceError):s.REGISTRY61[0].required=False
        expected=c._hash('native61_registry_revision2',(
            tuple(tuple(getattr(f,k) for k in f.__dataclass_fields__) for f in s.REGISTRY61),
            s.LITERAL_VALUES61,s.FLAG_VALUES61,s.INTEGER_BOUNDS61,'decimal_exact_10_6_no_unit_claim'))
        self.assertEqual(self.f.profile.field_registry_digest,expected)
        for spec in s.REGISTRY61:
            if spec.source.startswith(('route','rule')):
                self.assertEqual(spec.disposition,'observed_volatile' if spec.path==('expires',) else 'ordered_policy')

    def test_raw_hash_size_source_reference_consistency(self):
        raw,ref=self.f.documents()[0]
        for changed in (raw+b' ',raw.replace(b'lo',b'xx',1)):
            with self.assertRaises(c.ContractViolation2):n.decode_native_source61(changed,self.f.profile,ref)
        with self.assertRaises(c.ContractViolation2):replace(ref,artifact_path='../host/link.json')
        with self.assertRaises(c.ContractViolation2):replace(ref,source='address')

    def test_missing_argv_timing_principal_never_reconstructed(self):
        ref=self.f.documents()[0][1]
        for key,value in (('exact_argv','ip -j -d link show'),('timestamps','2026-10-21'),
                          ('namespace_identity','inode:123'),('os_principal','root')):
            with self.assertRaises(c.ContractViolation2):replace(ref,**{key:value})
        self.assertEqual(ref.exact_argv,'unrecorded')
        self.assertIs(type(ref.nominal_argv),tuple)

    def test_duplicate_source_or_scope_and_undeclared_scope_rejected(self):
        docs=self.f.documents()
        with self.assertRaises(c.ContractViolation2):n.decode_native_documents61((docs[0],docs[0]),self.f.profile)
        with self.assertRaises(c.ContractViolation2):replace(self.baseline,declared_scope_labels=('host','host'))
        with self.assertRaises(c.ContractViolation2):replace(self.baseline,declared_scope_labels=('host','runner'))

    def test_direct_constructor_cannot_swap_equal_bool_integer_rows(self):
        doc=self.f.decode('host','link')
        row=old.FrozenObject2(tuple((key,True if key=='ifindex' else value) for key,value in doc.rows[0].fields))
        with self.assertRaises(c.ContractViolation2):replace(doc,rows=(row,)+doc.rows[1:])
        different=old.FrozenObject2(tuple((key,99 if key=='ifindex' else value) for key,value in doc.rows[0].fields))
        with self.assertRaises(c.ContractViolation2):replace(doc,rows=(different,)+doc.rows[1:])

    def test_deterministic_digest_no_verification_override(self):
        self.assertEqual(self.baseline.digest,self.f.bundle().digest)
        f=ManagementFixture2.create();review=n.review_native_policy61(self.baseline,f.policy,f.pinned_digest)
        self.assertEqual(review.digest,n.review_native_policy61(self.baseline,f.policy,f.pinned_digest).digest)
        for key,value in (('result','verified'),('findings',()),('isolation_verified',True),('management_policy_verified',True)):
            with self.assertRaises(TypeError):replace(review,**{key:value})

    def test_import_ast_has_no_physical_io_or_registry_file_loading(self):
        allowed={'dataclasses','hashlib','ipaddress','re','native_v2_contracts','native_v2_topology_schema',
                 'native_v2_topology_json','native_v2_native61_schema','native_v2_management'}
        for name in ('native_v2_native61','native_v2_native61_schema'):
            tree=ast.parse((Path(__file__).parents[1]/(name+'.py')).read_text())
            for node in ast.walk(tree):
                if isinstance(node,ast.Import):self.assertTrue(all(alias.name in allowed for alias in node.names))
                if isinstance(node,ast.ImportFrom):
                    self.assertTrue(node.module is None or node.module in allowed)
                    if node.module is None:self.assertTrue(all(alias.name in allowed for alias in node.names))
                if isinstance(node,ast.Call) and isinstance(node.func,ast.Name):
                    self.assertNotIn(node.func.id,('open','exec','eval','__import__'))

    def test_fresh_import_forbids_socket_process_and_setns(self):
        script='''
import os,socket,subprocess,sys
from contextlib import ExitStack
from unittest.mock import patch
def no_io(*a,**k): raise AssertionError('forbidden I/O')
with ExitStack() as stack:
 for owner,name in ((socket,'socket'),(subprocess,'Popen'),(os,'system'),(os,'setns')):
  stack.enter_context(patch.object(owner,name,no_io,create=True))
 import trusted_checker_network.native_v2_native61
 assert 'docker' not in sys.modules and 'django' not in sys.modules
'''
        result=subprocess.run([sys.executable,'-W','error::ResourceWarning','-c',script],capture_output=True,check=False)
        self.assertEqual(result.returncode,0,result.stderr.decode())
