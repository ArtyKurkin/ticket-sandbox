"""Explicit synthetic complete topology. No reconstruction of VDS captures."""
from copy import deepcopy
from dataclasses import dataclass, replace
import hashlib
import json
from trusted_checker_network import native_v2_contracts as c
from trusted_checker_network import native_v2_topology as t
from trusted_checker_network import native_v2_topology_schema as s
from .native_v2_support import uid, hd


def link(index,name,mac,kind=None,master=None,peer=None,nsid=None):
    row={'ifindex':index,'ifname':name,'flags':['UP'],'mtu':1500,'link_type':'ether','address':mac}
    if name=='lo':
        row['flags']=['LOOPBACK','UP']; row['link_type']='loopback'
    if kind: row['linkinfo']={'info_kind':kind}
    if master is not None: row['master']=master
    if peer is not None: row['link_index']=peer
    if nsid is not None: row['link_netnsid']=nsid
    return row


@dataclass
class TopologyFixture2:
    profile: s.TopologyProfile2
    namespaces: tuple
    rows: dict
    peers: tuple
    tables: tuple

    @classmethod
    def create(cls):
        profile=s.TopologyProfile2(hd('synthetic-ip-build'),hd('synthetic-bridge-build'))
        namespaces=tuple(t.NamespaceRole2(role,c.NamespaceKey2(uid(1),100+i,uid(2),1),hd('synthetic-ns-'+role))
                         for i,role in enumerate(('host','runner','target')))
        host,runner,target=(n.key for n in namespaces)
        macs=('02:00:00:00:00:01','02:00:00:00:00:02','02:00:00:00:00:03','02:00:00:00:00:04','02:00:00:00:00:05')
        rows={role:{source:[] for source in s.SOURCES} for role in ('host','runner','target')}
        rows['host']['link']=[link(1,'lo','00:00:00:00:00:00'),link(2,'mgmt0',macs[0]),
            link(5,'tcsh0',macs[1],'bridge'),link(7,'vethrun',macs[2],'veth',5,2,10),link(9,'vethtarget',macs[3],'veth',5,2,11)]
        rows['host']['link'][2]['linkinfo']['info_data']={'gc_timer':178,'nf_call_iptables':0}
        rows['runner']['link']=[link(1,'lo','00:00:00:00:00:00'),link(2,'eth0',macs[4],'veth',peer=7,nsid=20)]
        rows['target']['link']=[link(1,'lo','00:00:00:00:00:00'),link(2,'eth0','02:00:00:00:00:06','veth',peer=9,nsid=20)]
        for role in rows:
            for l in rows[role]['link']:
                info=[]
                if l['ifname']=='lo':
                    info=[{'family':'inet','local':'127.0.0.1','prefixlen':8,'scope':'host','valid_life_time':'forever','preferred_life_time':'forever'},
                          {'family':'inet6','local':'::1','prefixlen':128,'scope':'host','valid_life_time':'forever','preferred_life_time':'forever'}]
                rows[role]['address'].append({'ifindex':l['ifindex'],'ifname':l['ifname'],'addr_info':info})
            for family in (4,6):
                rows[role]['rule'+str(family)]=[{'priority':0,'src':'all','table':'local'},
                    {'priority':32766,'src':'all','table':'main'}]
        rows['host']['bridge_link']=[{'ifindex':idx,'ifname':name,'link':peer,'flags':['UP'],'mtu':1500,
            'master':'tcsh0','state':'forwarding','priority':32,'cost':2} for idx,name,peer in
            ((7,'vethrun','if2'),(9,'vethtarget','if2'))]
        rows['host']['vlan']=[{'ifname':name,'vlans':[{'vlan':1,'flags':['PVID','Egress_Untagged']}]} for name in ('tcsh0','vethrun','vethtarget')]
        rows['host']['fdb']=[{'mac':macs[4],'dev':'vethrun','master':'tcsh0','vlan':1,'flags':['master'],'state':['permanent']}]
        rows['host']['route4']=[{'dst':'default','dev':'mgmt0','table':'main','protocol':'static','scope':'global','type':'unicast','gateway':'192.0.2.1','prefsrc':'192.0.2.2','metric':10}]
        rows['host']['route6']=[{'dst':'default','dev':'mgmt0','table':'main','protocol':'static','scope':'global','type':'unicast','gateway':'fe80::1','metric':100}]
        peers=(t.PeerWitness2(t.LinkReference2(host,7),t.LinkReference2(runner,2),10,20,hd('synthetic-peer-runner')),
               t.PeerWitness2(t.LinkReference2(host,9),t.LinkReference2(target,2),11,20,hd('synthetic-peer-target')))
        tables=tuple(t.TableMapping2(n.key,token,number,hd('synthetic-table-map-'+n.role)) for n in namespaces for token,number in (('local',255),('main',254)))
        return cls(profile,namespaces,rows,peers,tables)

    def bundle(self,rows=None):
        rows=deepcopy(self.rows if rows is None else rows); captures=[]; documents=[]
        for n in self.namespaces:
            for source,values in rows[n.role].items():
                raw=values if type(values) is bytes else json.dumps(values,separators=(',',':')).encode()
                binary=self.profile.bridge_binary_digest if dict(s.COMMANDS)[source][0]=='bridge' else self.profile.ip_binary_digest
                d=t.CaptureDescriptor2(n.key,source,self.profile.digest,binary,uid(1000+len(captures)),uid(3),hd('synthetic-approval'),uid(4),
                    hashlib.sha256(raw).hexdigest(),len(raw),hd('synthetic-capture-'+n.role+'-'+source))
                captures.append(d); documents.append((raw,d))
        plan=t.TopologyCapturePlan2(self.profile,uid(3),hd('synthetic-approval'),uid(4),self.namespaces,tuple(captures),self.peers,self.tables)
        return tuple(documents),plan

    def normalized(self,rows=None,plan_change=None):
        docs,plan=self.bundle(rows)
        if plan_change: plan=plan_change(plan)
        sources=t.decode_topology_documents2(docs,self.profile,plan)
        return t.normalize_topology2(sources,plan)

    def complete(self,rows=None): return t.complete_topology2(self.normalized(rows))
