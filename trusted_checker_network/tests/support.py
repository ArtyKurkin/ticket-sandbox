from dataclasses import replace
from pathlib import Path
from uuid import uuid4
from trusted_checker_runtime.tests.support import Lab
from trusted_checker_runtime.live_contract import LIVE_POLICY,LIVE_TARGET,LIVE_RUNNER
from trusted_checker_network.auth import Principal,NetworkSigner,NetworkVerifier
from trusted_checker_network.contracts import NetworkApproval,NetworkBinding,NamespaceIdentity,HostSnapshot
from trusted_checker_network.host import MockNetworkHost,IndependentReadback
from trusted_checker_network.rules import approved_rules,rules_hash
from trusted_checker_network.store import NetworkStore
from trusted_checker_network.installer import TrustedRulesInstaller
from trusted_checker_network.collector import Capture,PacketEvent,IndependentCollector
from trusted_checker_network.packets import ipv4_frame


def uuid():return str(uuid4())


class NetworkLab:
    def __init__(self, runtime=None, run_id=None):
        self.base = runtime or Lab()
        self.clock,self.tmp = self.base.clock,self.base.tmp
        if runtime is None:
            self.runtime_approval = replace(self.base.approval,policy_id=LIVE_POLICY.policy_id,policy_version=2,
                policy_digest=LIVE_POLICY.digest,schema_version=2,authority_mode='live_runtime_v2',
                target_profile_digest=LIVE_TARGET.digest,runner_profile_digest=LIVE_RUNNER.digest)
            target_id,runner_id,binding,generation,started = 'd'*64,'e'*64,uuid(),uuid(),self.clock.docker()
        else:
            self.runtime_approval = runtime.approval
            report = runtime.authority.report(run_id)
            target_id,runner_id,binding,generation,started = (runtime.target_id,report['owned_container_id'],
                report['runtime_binding_uuid'],report['generation_uuid'],report['target_snapshot']['started_at'])
        approval = self.runtime_approval
        self.scope = approval.scope
        self.principals = tuple(Principal(role+':network',role,self.scope,bytes([i])*32) for i,role in
                    enumerate(('operator','installer','capture','validator','host'),11))
        self.signers = {p.role:NetworkSigner(p) for p in self.principals}
        self.verifier = NetworkVerifier(self.principals)
        self.binding = NetworkBinding(uuid(),'1'*64,4026531000,approval.daemon,self.scope,approval.digest,binding,generation,
            approval.network.network_id,'tcsh0',10,'02:42:ac:1e:00:01',
            NamespaceIdentity(target_id,111,10001,4026531101,started,0,'f'*64,'vethTarget',11,2,'02:42:ac:1e:00:02','172.30.0.2'),
            NamespaceIdentity(runner_id,112,10002,4026531102,started,0,'9'*64,'vethRunner',12,2,'02:42:ac:1e:00:03','172.30.0.3'),
            '172.30.0.1','172.30.0.4','172.30.0.5','172.30.0.6','172.30.0.7')
        identifier = uuid()
        self.bootstrap_rules = approved_rules(identifier,approval,self.binding,active=False)
        self.active_rules = approved_rules(identifier,approval,self.binding,active=True)
        self.approval = NetworkApproval(identifier,'operator:network',self.binding,rules_hash(self.bootstrap_rules),
            rules_hash(self.active_rules),self.clock(),self.clock()+3600)
        self.snapshot = HostSnapshot(self.binding,('tcsh0',),('vethTarget','vethRunner'),(2,),(2,),10,10,0,self.clock())
        self.store = NetworkStore(Path(self.tmp.name)/('network-'+identifier+'.network.sqlite3'))
        self.host = MockNetworkHost(self.snapshot,self.clock,self.signers['host'])
        self.reader = IndependentReadback(self.host,self.signers['validator'],self.verifier,self.clock)
        self.installer = self.new_installer()
        self.installer.register(self.signers['operator'].sign('approval',self.approval),
                                self.bootstrap_rules,self.active_rules,self.runtime_approval)
        self.collector = IndependentCollector(self.store,self.host,self.installer,self.signers['validator'],self.verifier,self.clock)
        self.response_flags = 20
        self.modify_capture = None
        self.host.capture_factory = self.capture

    def close(self):self.base.close()

    def new_installer(self):
        return TrustedRulesInstaller(self.store,self.host,self.reader,self.signers['installer'],self.verifier,
                                     'operator:network',self.clock)

    def install(self, operation, request=None, deadline=None):
        return self.installer.install(self.approval,operation,request or uuid(),deadline or self.clock()+8)

    def active(self):self.install('bootstrap');self.install('active')

    def capture(self, approval, request):
        start = self.clock();before = self.host.snapshot();events = []
        for index,probe in enumerate(request['probes']):
            stages = ('send','ingress','target_ingress','response','runner_receive') if probe.response_required else ('send','ingress','drop')
            for stage in stages:
                frame = probe.frame
                interface = self.binding.runner.interface
                if stage in ('target_ingress','response'):interface = self.binding.target.interface
                if stage in ('response','runner_receive'):
                    frame = ipv4_frame(self.binding.target.mac,self.binding.runner.mac,self.binding.target.ipv4,
                        self.binding.runner.ipv4,8080,probe.sequence,flags=self.response_flags,reverse=True)
                events.append(PacketEvent(len(events)+1,probe.probe_id,stage,interface,frame,start+index*0.1,
                                          request['rules_digest'],request['generation']))
        self.clock.advance(1.5)
        capture = Capture(request['context_uuid'],approval.scope,approval.binding.digest,request['generation'],request['rules_digest'],
            before,self.host.snapshot(),start,self.clock(),len(events),0,0,False,True,'none',tuple(events))
        if self.modify_capture:capture = self.modify_capture(capture)
        return self.signers['capture'].sign('capture',capture)

    def measure(self, context=None, deadline=None):
        return self.collector.measure(self.approval,context or uuid(),deadline or self.clock()+8)
