"""Authored native-format shapes plus byte-preserved corpus loading for tests only."""
from copy import deepcopy
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path

from trusted_checker_network import native_v2_native61 as n
from trusted_checker_network import native_v2_native61_schema as s
from .native_v2_support import hd

FIXTURES=Path(__file__).parent/'fixtures/native_capture_20261021'
ORIGINALS=FIXTURES/'native/tc-native-capture-20261021T082517Z'
SCOPES=('host','tc-br-runner','tc-br-target','tc-runner','tc-target')


def make_reference(raw,scope,source,archive_digest):
    return n.NativeSourceReference61(scope,source,scope+'/'+source+'.json',archive_digest,
                                     hashlib.sha256(raw).hexdigest(),len(raw))


def native_documents():
    # Version output hashes are artifact references, never binary/OS attestations.
    profile=s.NativeTopologyProfile61(hashlib.sha256((ORIGINALS/'iproute2.txt').read_bytes()).hexdigest(),
                                     hashlib.sha256((ORIGINALS/'bridge-version.txt').read_bytes()).hexdigest())
    documents=[]
    for path in sorted(ORIGINALS.glob('*/*.json')):
        if path.stem=='nft':continue
        raw=path.read_bytes()
        documents.append((raw,make_reference(raw,path.parent.name,path.stem,s.ARCHIVE_SHA256)))
    return profile,tuple(documents)


def native_bundle():
    profile,docs=native_documents()
    return n.NativeDiagnosticBundle61(profile,SCOPES,n.decode_native_documents61(docs,profile))


def bridge_options():
    # Authored values. Do not read the native artifact to construct this baseline.
    return dict(forward_delay=1500,hello_time=200,max_age=2000,ageing_time=30000,stp_state=0,
        priority=32768,vlan_filtering=0,root_port=0,root_path_cost=0,topology_change=0,
        topology_change_detected=0,vlan_default_pvid=1,vlan_stats_enabled=0,vlan_stats_per_port=0,
        mcast_snooping=1,no_linklocal_learn=0,mcast_vlan_snooping=0,mcast_router=1,
        mcast_query_use_ifaddr=0,mcast_querier=0,mcast_hash_elasticity=16,mcast_hash_max=4096,
        mcast_last_member_cnt=2,mcast_startup_query_cnt=2,mcast_last_member_intvl=100,
        mcast_membership_intvl=26000,mcast_querier_intvl=25500,mcast_query_intvl=12500,
        mcast_query_response_intvl=1000,mcast_startup_query_intvl=3125,mcast_stats_enabled=0,
        mcast_igmp_version=2,mcast_mld_version=1,nf_call_iptables=0,nf_call_ip6tables=0,
        nf_call_arptables=0,vlan_protocol='802.1Q',bridge_id='8000.02:00:00:00:00:05',
        root_id='8000.02:00:00:00:00:05',group_fwd_mask='0',group_addr='01:80:c2:00:00:00',
        hello_timer=0.0,tcn_timer=0.0,topology_change_timer=0.0,gc_timer=200.25)


def boolean_options():
    return dict(hairpin=False,guard=False,root_block=False,fastleave=False,learning=True,flood=True,
        mcast_flood=True,bcast_flood=True,mcast_to_unicast=False,neigh_suppress=False,
        vlan_tunnel=False,isolated=False,locked=False)


def link(index,name,kind=None,peer=None,nsid=None,master=None):
    lo=name=='lo'
    row=dict(ifindex=index,ifname=name,flags=['LOOPBACK','UP','LOWER_UP'] if lo else ['BROADCAST','MULTICAST','UP','LOWER_UP'],
        mtu=65536 if lo else 1500,qdisc='noqueue',operstate='UNKNOWN' if lo else 'UP',group='default',
        txqlen=1000,link_type='loopback' if lo else 'ether',address='00:00:00:00:00:00' if lo else '02:00:00:00:00:'+format(index,'02x'),
        broadcast='00:00:00:00:00:00' if lo else 'ff:ff:ff:ff:ff:ff',linkmode='DEFAULT',
        promiscuity=0,allmulti=0,min_mtu=0 if lo else 68,max_mtu=0 if lo else 65535,
        inet6_addr_gen_mode='eui64',num_tx_queues=1,num_rx_queues=1,gso_max_size=65536,
        gso_max_segs=65535,tso_max_size=524280,tso_max_segs=65535,gro_max_size=65536)
    if kind:row['linkinfo']={'info_kind':kind}
    if kind=='bridge':row['linkinfo']['info_data']=bridge_options()
    if peer is not None:row['link_index']=peer;row['link_netnsid']=nsid
    if master is not None:
        row['master']=master
        row['linkinfo']['info_slave_kind']='bridge'
        row['linkinfo']['info_slave_data']=dict(boolean_options(),state='forwarding',priority=32,cost=2,
            id='0x8001',no='0x1',designated_port=32769,designated_cost=0,
            bridge_id='8000.02:00:00:00:00:05',root_id='8000.02:00:00:00:00:05',
            topology_change_ack=0,config_pending=0,proxy_arp=False,proxy_arp_wifi=False,multicast_router=1,
            group_fwd_mask='0',group_fwd_mask_str='0x0',hold_timer=0.0,message_age_timer=0.0,forward_delay_timer=0.0)
    return row


def address_row(row,addresses):
    keys=('ifindex','ifname','flags','mtu','qdisc','operstate','group','txqlen','link_type','address','broadcast',
          'altnames','link_index','link_netnsid','master')
    return dict({k:deepcopy(row[k]) for k in keys if k in row},addr_info=addresses)


def addr(family,local,prefix,scope):
    return dict(family=family,local=local,prefixlen=prefix,scope=scope,
                valid_life_time=4294967295,preferred_life_time=4294967295)


@dataclass
class FormatFixture61:
    profile: s.NativeTopologyProfile61
    rows: dict

    @classmethod
    def create(cls):
        rows={scope:{source:[] for source in s.SOURCES} for scope in ('host','runner','target')}
        host=[link(1,'lo'),link(2,'mgmt0'),link(5,'tcsh0','bridge'),
              link(7,'vethrun','veth',6,2,'tcsh0'),link(9,'vethtarget','veth',8,3,'tcsh0')]
        host[1].update(parentbus='virtio',parentdev='virtio0',altnames=['ens3'])
        rows['host']['link']=host
        rows['runner']['link']=[link(1,'lo'),link(6,'eth0','veth',7,0)]
        rows['target']['link']=[link(1,'lo'),link(8,'eth0','veth',9,0)]
        for scope,docs in rows.items():
            for row in docs['link']:
                addresses=[addr('inet','127.0.0.1',8,'host'),addr('inet6','::1',128,'host')] if row['ifname']=='lo' else []
                docs['address'].append(address_row(row,addresses))
            for source in ('rule4','rule6'):
                docs[source]=[dict(priority=0,src='all',table='local'),dict(priority=32766,src='all',table='main')]
        rows['host']['address'][1]['addr_info']=[dict(addr('inet','192.0.2.2',24,'global'),dynamic=True,metric=100,label='mgmt0',broadcast='192.0.2.255')]
        rows['host']['address'][0]['addr_info'][1]['noprefixroute']=True
        rows['host']['route4']=[dict(dst='default',dev='mgmt0',protocol='dhcp',prefsrc='192.0.2.2',gateway='192.0.2.1',metric=100,flags=[]),
            dict(type='local',dst='127.0.0.1',dev='lo',table='local',protocol='kernel',scope='host',prefsrc='127.0.0.1',flags=[])]
        rows['host']['route6']=[dict(dst='default',dev='mgmt0',protocol='ra',metric=100,flags=[],pref='medium',gateway='fe80::1',expires=1700,metrics=[dict(hoplimit=64)]),
            dict(type='local',dst='::1',dev='lo',table='local',protocol='kernel',metric=0,flags=[],pref='medium')]
        rows['host']['bridge_link']=[dict(boolean_options(),ifindex=row['ifindex'],link='if'+str(row['link_index']),
            ifname=row['ifname'],flags=row['flags'],mtu=1500,master='tcsh0',state='forwarding',priority=32,cost=2,mcast_router=1)
            for row in host if 'master' in row]
        rows['host']['bridge_vlan']=[dict(ifname=name,vlans=[dict(vlan=1,flags=['PVID','Egress Untagged'])]) for name in ('tcsh0','vethrun','vethtarget')]
        rows['host']['bridge_fdb']=[dict(mac='33:33:00:00:00:01',ifname='mgmt0',flags=['self'],state='permanent'),
            dict(mac='02:00:00:00:00:07',ifname='vethrun',flags=[],state='permanent',master='tcsh0',vlan=1)]
        return cls(s.NativeTopologyProfile61(hd('authored-ip-version-reference'),hd('authored-bridge-version-reference')),rows)

    def documents(self,rows=None):
        rows=deepcopy(self.rows if rows is None else rows)
        return tuple((raw,make_reference(raw,scope,source,hd('authored-synthetic-not-native-archive')))
            for scope,docs in rows.items() for source,value in docs.items()
            for raw in (json.dumps(value,separators=(',',':')).encode(),))

    def decode(self,scope,source,value=None):
        raw=json.dumps(self.rows[scope][source] if value is None else value,separators=(',',':')).encode()
        return n.decode_native_source61(raw,self.profile,make_reference(raw,scope,source,hd('authored-synthetic-not-native-archive')))

    def bundle(self,rows=None):
        docs=self.documents(rows)
        return n.NativeDiagnosticBundle61(self.profile,('host','runner','target'),n.decode_native_documents61(docs,self.profile))
