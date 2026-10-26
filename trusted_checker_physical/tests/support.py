from copy import deepcopy
from dataclasses import replace
import hashlib
import hmac
import json
from pathlib import Path
import struct
from trusted_checker_network.tests.support import NetworkLab,uuid
from trusted_checker_runtime.profiles import require
from trusted_checker_live.transport import DaemonWitness,ExplicitUnixEndpoint
from trusted_checker_live.egress import canonical_readback
from trusted_checker_physical.contracts import PhysicalApproval,Principal,Authenticator,Signed,TransactionTrace
from trusted_checker_physical.authorization import Activation,Deadline
from trusted_checker_physical.rules import recipes,rules_hash,name
from trusted_checker_physical.io import json_output
from trusted_checker_physical.preflight import HostPreflight,REQUIRED_CONFIG,OFFLOAD
from trusted_checker_physical.inventory import NamespaceInventory
from trusted_checker_physical.docker_readonly import ReadOnlyDocker
from trusted_checker_physical.installer import PhysicalNetworkInstaller,IndependentNftReadback
from trusted_checker_physical.journal import PhysicalJournal
from trusted_checker_physical.artifacts import source_digest
from trusted_checker_physical.collector import BoundedPhysicalCollector,physical_plan
from trusted_checker_network.packets import ipv4_frame


class FakeDocker:
    def __init__(self,lab):
        self.lab=lab;self.calls=[];self.timeout=3;self.extra=False;self.hook=None
        b=lab.binding
        self.attrs={n.container_id:{'Id':n.container_id,'RestartCount':0,'State':{'Pid':n.pid,'Running':True,'Status':'running',
            'StartedAt':n.docker_started_at,'Paused':False,'Restarting':False,'Dead':False},'NetworkSettings':{'Networks':{'approved':{
            'NetworkID':b.network_id,'EndpointID':n.endpoint_id,'IPAddress':n.ipv4,'MacAddress':n.mac}}}} for n in (b.target,b.runner)}
    def info(self):self.calls.append('info');return {'ID':self.lab.binding.daemon.daemon_id}
    def containers(self,all):
        self.calls.append('containers');return [{'Id':n} for n in self.attrs]+([{'Id':'0'*64}] if self.extra else [])
    def inspect_container(self,identifier):
        self.calls.append(identifier)
        if self.hook:self.hook(identifier)
        return deepcopy(self.attrs[identifier])
    def inspect_network(self,identifier):
        b=self.lab.binding
        return {'Id':identifier,'Driver':'bridge','Internal':True,'EnableIPv6':False,
                'Options':{'com.docker.network.bridge.name':b.bridge_name},'Containers':{n.container_id:{
                    'EndpointID':n.endpoint_id,'IPv4Address':n.ipv4+'/24'} for n in (b.target,b.runner)}}


class FakeLinuxIO:
    """No subclass/origin trick: offline Activation is mandatory."""
    def __init__(self,lab):
        require(lab.activation.offline,'test_only_io');self.lab=lab;self.activation=lab.activation;self.calls=[]
    def read(self,path,budget):
        self.activation.check('read');budget.remaining();value=self.lab.files[path]
        return value() if callable(value) else value
    def inode(self,path,budget):self.activation.check('read');budget.remaining();return self.lab.inodes[path]
    def run(self,operation,budget,*,payload=None,interface=None,namespace=None,recovery=False):
        self.activation.check('mutate' if operation=='nft_apply' else 'read',recovery=recovery)
        budget.remaining();self.calls.append(operation)
        l=self.lab
        if operation=='nft_apply':
            raw=self.activation.consume_batch(payload,budget);l.batches.append(json_output(raw))
            if l.apply_hook:l.apply_hook('before')
            commands=l.batches[-1]['nftables'];deletes=[c['delete']['table']['handle'] for c in commands if 'delete' in c]
            require(not l.rules['nftables'] if not deletes else deletes==list(l.handles),'test_kernel_foreign_handles')
            l.rules={'nftables':canonical_readback({'nftables':[{'add':c['create']} if 'create' in c else c
                        for c in commands if 'add' in c or 'create' in c]})}
            # canonical_readback intentionally doesn't support create commands;
            # the mock kernel turns them into normal table objects first.
            l.generation+=1;l.handles=(100*l.generation,100*l.generation+1)
            pos=0
            for item in l.rules['nftables']:
                if 'table' in item:item['table']['handle']=l.handles[pos];pos+=1
            if l.apply_hook:l.apply_hook('after')
            return b''
        if operation=='nft_read':
            if l.read_hook:l.read_hook()
            value=l.rules
        elif operation=='kernel':return l.kernel.encode()
        elif operation=='nft_version':return l.nft.encode()
        elif operation=='offload':return '\n'.join(key+': off' for key in OFFLOAD).encode() if not l.offload else b'generic-receive-offload: on'
        elif operation in ('tc_ingress','tc_egress'):value=[]
        elif operation=='links':value=l.namespace_links[namespace] if namespace else l.links
        elif operation=='addresses':value=l.addresses[namespace]
        else:raise AssertionError(operation)
        return json.dumps(value).encode()


def nla(kind,raw):
    size=4+len(raw);return struct.pack('=HH',size,kind)+raw+b'\x00'*((-size)%4)


def trace_packet(lab,probe,trace_id,*,drop=False,foreign=False):
    a=lab.approval
    parts=[nla(1,(('foreign' if foreign else name(a.approval_uuid))+'\x00').encode()),nla(2,b'prerouting\x00'),
           nla(4,struct.pack('!I',1 if drop else 3)),nla(6,struct.pack('=I',trace_id)),nla(15,struct.pack('!I',7))]
    if drop:parts.append(nla(16,struct.pack('!I',0)))
    else:
        offset=18 if probe.frame[12:14]==b'\x81\x00' else 14
        header=40 if probe.frame[offset]>>4==6 else 20
        parts.extend((nla(7,probe.frame[:offset]),nla(8,probe.frame[offset:offset+header]),nla(9,probe.frame[offset+header:]),
                      nla(10,struct.pack('!I',lab.binding.runner.ifindex))))
    body=b'\x07\x00\x00\x00'+b''.join(parts)
    return struct.pack('=IHHII',16+len(body),0xa11,0,0,0)+body


class FakePackets:
    def __init__(self,lab):self.lab=lab;self.probe=None;self.sent=[];self.closed=False;self.modify=None;self.rst=True;self.loss=False
    def open(self,budget):return self
    def prime_peer(self,budget):pass
    def send(self,probe,budget):self.probe=probe;self.sent.append(probe.probe_id)
    def poll(self,budget,seconds):
        l,p=self.lab,self.probe;rows=[('host_runner',p.frame,('vethRunner',3,3,1,b''))]
        if p.response_required:
            reply=ipv4_frame(l.binding.target.mac,l.binding.runner.mac,l.binding.target.ipv4,l.binding.runner.ipv4,
                8080,p.sequence,reverse=True,flags=20 if self.rst else 18)
            rows.extend((('target',p.frame,('eth0',3,0,1,b'')),('target',reply,('eth0',3,4,1,b'')),
                         ('runner',reply,('eth0',3,0,1,b''))))
        else:
            rows.extend((('trace',trace_packet(l,p,len(self.sent)),(0,256)),
                         ('trace',trace_packet(l,p,len(self.sent),drop=True),(0,256))))
        l.clock.advance(seconds)
        return self.modify(rows) if self.modify else rows
    def finish(self):require(not self.loss,'physical_packet_capture_loss')
    def close(self):self.closed=True


class Lab:
    def __init__(self):
        self.base=NetworkLab();self.clock=self.base.clock;self.tmp=self.base.tmp
        b=self.base.binding
        self.witness=DaemonWitness(b.host_boot_uuid,123,0,12345,1,456)
        self.endpoint=ExplicitUnixEndpoint('endpoint:unit','/run/tc-shadow/docker.sock',self.witness)
        daemon=replace(b.daemon,endpoint_config_digest=self.endpoint.digest)
        self.runtime=replace(self.base.runtime_approval,daemon=daemon)
        self.binding=replace(b,daemon=daemon,runtime_approval_digest=self.runtime.digest,
            host_identity_digest=hashlib.sha256(b'test-machine').hexdigest())
        identifier=uuid()
        boot,active=(recipes(identifier,self.runtime,self.binding,active=flag) for flag in (False,True))
        self.approval=PhysicalApproval(identifier,'operator:physical',self.binding,rules_hash(boot),rules_hash(active),
            source_digest(),self.clock(),self.clock()+3600,True,'install_and_collect')
        self.principals=tuple(Principal(role+':physical',role,self.binding.scope,bytes([i])*32) for i,role in
                              enumerate(('operator','observer','validator','collector'),31))
        self.auth=Authenticator(self.principals);self.activation=Activation(self.auth,enabled=True,offline=True,clock=self.clock,monotonic=self.clock)
        self.rules={'nftables':[]};self.handles=();self.generation=0;self.batches=[]
        self.apply_hook=self.read_hook=None;self.kernel='6.8.0-test';self.nft='nftables v1.0.9 (Old Doc Yak)';self.offload=False
        b=self.binding
        self.files={'/boot/config-'+self.kernel:'\n'.join(key+'=y' for key in REQUIRED_CONFIG),'/proc/modules':'',
                    '/proc/sys/kernel/random/boot_id':b.host_boot_uuid,'/etc/machine-id':'test-machine',
                    '/proc/self/status':'CapEff: '+format(sum(1<<bit for bit in (12,13,21)),'x')+'\nSeccomp: 0',
                    '/proc/sys/net/core/rmem_max':'262144','/proc/sys/net/core/rmem_default':'262144'}
        self.inodes={'/proc/self/ns/net':b.host_netns_inode}
        for key in ('iptables','ip6tables','arptables'):self.files['/proc/sys/net/bridge/bridge-nf-call-'+key]='0'
        self.links=[{'ifindex':10,'ifname':'tcsh0','address':b.bridge_mac,'linkinfo':{'info_kind':'bridge'}}]
        self.namespace_links={};self.addresses={}
        for n in (b.target,b.runner):
            self.inodes['/proc/'+str(n.pid)+'/ns/net']=n.netns_inode
            self.files['/proc/'+str(n.pid)+'/stat']=str(n.pid)+' (test (proc)) '+' '.join(['S']+['0']*18+[str(n.process_start_ticks)])
            self.links.append({'ifindex':n.ifindex,'ifname':n.interface,'address':'02:00:00:00:00:aa','master':10,
                               'link_index':n.peer_ifindex,'linkinfo':{'info_kind':'veth'}})
            self.namespace_links[n.pid]=[{'ifindex':1,'ifname':'lo'}, {'ifindex':n.peer_ifindex,'ifname':'eth0',
                'link_index':n.ifindex,'address':n.mac,'linkinfo':{'info_kind':'veth'}}]
            self.addresses[n.pid]=[{'ifindex':n.peer_ifindex,'addr_info':[{'family':'inet','local':n.ipv4}]}]
        self.api=FakeDocker(self)
        self.io=FakeLinuxIO(self);self.read_io=FakeLinuxIO(self)
        self.docker=ReadOnlyDocker(self.activation,self.endpoint,offline_api=self.api,offline_witness=self.witness)
        self.preflight=HostPreflight(self.activation,self.read_io,self.docker)
        self.inventory=NamespaceInventory(self.activation,self.read_io,self.docker)
        self.reader=IndependentNftReadback(self.activation,self.read_io)
        self.journal=PhysicalJournal(Path(self.tmp.name)/'test.physical.sqlite3',self.activation.origin)
        self.installer=PhysicalNetworkInstaller(self.activation,self.io,self.reader,self.journal,self.preflight,self.inventory,self.runtime)
        self.installer.register(self.sign(self.approval,'approval'))
        self.packets=FakePackets(self)
        self.collector=BoundedPhysicalCollector(self.activation,self.inventory,self.reader,self.journal,offline_sockets=self.packets)
    def close(self):self.base.close()
    def budget(self,seconds=30):return Deadline(self.clock()+seconds,self.clock,self.clock)
    def sign(self,payload,kind):
        role={'approval':'operator','transaction':'observer','capture':'collector'}[kind]
        p=next(p for p in self.principals if p.role==role)
        return Signed(kind,p.name,payload,hmac.new(p.key,Authenticator.raw(kind,p.name,payload),hashlib.sha256).hexdigest())
    def install(self,op,key=None,budget=None):return self.installer.install(op,key or uuid(),budget or self.budget())
    def active(self):self.install('bootstrap');self.install('active')
    def trace(self,key,origin='offline_simulation'):
        with self.journal.transaction() as db:intent=self.journal.get(db,'intent',key)
        return self.sign(TransactionTrace(key,self.approval.digest,intent['transaction'],intent['rules'],self.binding.host_boot_uuid,
            self.binding.digest,intent['generation'],self.handles,self.clock(),'independent_committed_netlink_transaction',origin,
            self.approval.scope),'transaction')
