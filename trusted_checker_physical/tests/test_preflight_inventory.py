from copy import deepcopy
from dataclasses import replace
import unittest
from trusted_checker_runtime.profiles import Denied
from .support import Lab


class PreflightTests(unittest.TestCase):
    def setUp(self):self.l=Lab();self.addCleanup(self.l.close)
    def test_readonly_facts_never_claim_isolation(self):
        l=self.l;r=l.preflight.check(l.budget())
        self.assertEqual(r.origin,'offline_simulation');self.assertFalse(r.isolation_proven);self.assertFalse(r.capture_continuity_proven)
        self.assertEqual(l.batches,[])
    def test_unsupported_kernel(self):
        self.l.kernel='5.15.0-test'
        with self.assertRaisesRegex(Denied,'kernel_unsupported'):self.l.preflight.check(self.l.budget())
    def test_unsupported_nft(self):
        self.l.nft='nftables v0.9.0'
        with self.assertRaisesRegex(Denied,'nft_unsupported'):self.l.preflight.check(self.l.budget())
    def test_module_or_bridge_feature_missing(self):
        l=self.l;l.files['/boot/config-'+l.kernel]=l.files['/boot/config-'+l.kernel].replace('CONFIG_NF_CONNTRACK_BRIDGE=y','CONFIG_NF_CONNTRACK_BRIDGE=m')
        with self.assertRaisesRegex(Denied,'kernel_feature_unproven'):l.preflight.check(l.budget())
        l.files['/proc/modules']='nf_conntrack_bridge 100 0 - Live 0x0'
        self.assertFalse(l.preflight.check(l.budget()).isolation_proven)
    def test_bridge_family_absent(self):
        l=self.l;l.files['/boot/config-'+l.kernel]=l.files['/boot/config-'+l.kernel].replace('CONFIG_NF_TABLES_BRIDGE=y','CONFIG_NF_TABLES_BRIDGE=n')
        with self.assertRaises(Denied):l.preflight.check(l.budget())
    def test_foreign_hook_or_table(self):
        l=self.l
        for obj in ({'table':{'family':'bridge','name':'foreign'}},{'chain':{'family':'bridge','table':'foreign','name':'x','hook':'prerouting'}}):
            with self.subTest(obj=obj):
                l.rules={'nftables':[obj]}
                with self.assertRaises(Denied):l.preflight.check(l.budget())
    def test_br_netfilter_active(self):
        l=self.l;l.files['/proc/sys/net/bridge/bridge-nf-call-iptables']='1'
        with self.assertRaises(Denied):l.preflight.check(l.budget())
    def test_extra_bridge(self):
        l=self.l;l.links.append({'ifindex':90,'ifname':'docker0','address':'02:00:00:00:00:01','linkinfo':{'info_kind':'bridge'}})
        with self.assertRaises(Denied):l.preflight.check(l.budget())
    def test_foreign_workload(self):
        self.l.api.extra=True
        with self.assertRaisesRegex(Denied,'foreign_workload'):self.l.preflight.check(self.l.budget())
    def test_offload_not_disabled(self):
        self.l.offload=True
        with self.assertRaisesRegex(Denied,'offload_unproven'):self.l.preflight.check(self.l.budget())
    def test_capture_buffer_small(self):
        self.l.files['/proc/sys/net/core/rmem_max']='8192'
        with self.assertRaisesRegex(Denied,'capture_buffer'):self.l.preflight.check(self.l.budget())
    def test_missing_capability_and_seccomp_restriction(self):
        l=self.l;l.files['/proc/self/status']='CapEff: 0\nSeccomp: 0'
        with self.assertRaisesRegex(Denied,'capabilities_unproven'):l.preflight.check(l.budget())
    def test_xdp_bypass_unapproved(self):
        l=self.l;l.links[-1]['xdp']={'attached':'drv'}
        with self.assertRaisesRegex(Denied,'xdp_or_vlan'):l.preflight.check(l.budget())
    def test_foreign_host_identity(self):
        self.l.files['/etc/machine-id']='foreign'
        with self.assertRaisesRegex(Denied,'host_identity'):self.l.preflight.check(self.l.budget())
    def test_endpoint_and_daemon_session(self):
        l=self.l;l.docker._witness=replace(l.witness,process_start_ticks=999)
        with self.assertRaisesRegex(Denied,'session_changed'):l.preflight.check(l.budget())
    def test_readonly_docker_rejects_exec_and_foreign_id(self):
        l=self.l
        for op,identifier in (('exec_create',None),('inspect_container','0'*64),('inspect_network','0'*64)):
            with self.subTest(op=op),self.assertRaises(Denied):l.docker.call(op,l.budget(),identifier)
        self.assertEqual(l.api.calls,[])


class InventoryTests(unittest.TestCase):
    def setUp(self):self.l=Lab();self.addCleanup(self.l.close)
    def test_exact_inventory_not_continuous_attestation(self):
        r=self.l.inventory.observe(self.l.budget());self.assertEqual(len(r.namespace_peers),2);self.assertFalse(r.continuity_proven)
    def test_pid_and_start_ticks_reuse(self):
        l=self.l;n=l.binding.runner
        l.files['/proc/'+str(n.pid)+'/stat']=str(n.pid)+' (same name) '+' '.join(['S']+['0']*18+['999'])
        with self.assertRaisesRegex(Denied,'pid_namespace_reuse'):l.inventory.observe(l.budget())
    def test_netns_inode_reuse(self):
        l=self.l;l.inodes['/proc/'+str(l.binding.runner.pid)+'/ns/net']=999
        with self.assertRaisesRegex(Denied,'pid_namespace_reuse'):l.inventory.observe(l.budget())
    def test_veth_identity_and_reciprocal_link(self):
        l=self.l;original=deepcopy(l.links)
        for field,value in (('ifname','vethForeign'),('ifindex',90),('link_index',99),('master',90)):
            with self.subTest(field=field):
                l.links=deepcopy(original);l.links[-1][field]=value
                with self.assertRaises(Denied):l.inventory.observe(l.budget())
    def test_source_mac_and_ip_changed(self):
        l=self.l;n=l.binding.runner;peer=l.namespace_links[n.pid][1];original=peer['address']
        peer['address']='02:00:00:00:00:99'
        with self.assertRaises(Denied):l.inventory.observe(l.budget())
        peer['address']=original;l.addresses[n.pid][0]['addr_info'][0]['local']='172.30.0.99'
        with self.assertRaises(Denied):l.inventory.observe(l.budget())
    def test_extra_namespace_attachment(self):
        l=self.l;l.namespace_links[l.binding.runner.pid].append({'ifindex':3,'ifname':'eth1'})
        with self.assertRaisesRegex(Denied,'extra_namespace_interface'):l.inventory.observe(l.budget())
    def test_extra_docker_network(self):
        l=self.l;l.api.attrs[l.binding.runner.container_id]['NetworkSettings']['Networks']['foreign']={}
        with self.assertRaisesRegex(Denied,'extra_docker_network'):l.inventory.observe(l.budget())
    def test_endpoint_start_and_restart_drift(self):
        l=self.l;attrs=l.api.attrs[l.binding.runner.container_id];original=deepcopy(attrs)
        for path,key,value in (('State','StartedAt','2026-10-19T11:00:00Z'),('State','Pid',999),('State','Running',False)):
            with self.subTest(key=key):
                attrs.clear();attrs.update(deepcopy(original));attrs[path][key]=value
                with self.assertRaises(Denied):l.inventory.observe(l.budget())
        attrs.clear();attrs.update(original);attrs['RestartCount']=1
        with self.assertRaises(Denied):l.inventory.observe(l.budget())
    def test_identity_changed_between_reads(self):
        l=self.l;target=l.binding.target.container_id;count=[0]
        def change(identifier):
            if identifier==target:
                count[0]+=1
                if count[0]==2:l.api.attrs[identifier]['State']['Pid']=999
        l.api.hook=change
        with self.assertRaisesRegex(Denied,'changed_during_observation'):l.inventory.observe(l.budget())
    def test_stale_endpoint_id(self):
        l=self.l;ep=next(iter(l.api.attrs[l.binding.runner.container_id]['NetworkSettings']['Networks'].values()))
        ep['EndpointID']='0'*64
        with self.assertRaisesRegex(Denied,'endpoint_changed'):l.inventory.observe(l.budget())
