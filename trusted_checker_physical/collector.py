"""Finite physical probes + packet/trace correlation. Never fabricates success.

Native NFTRACE lacks end-to-end loss/continuity accounting. This implementation
reports bounded observations, but its complete-matrix result remains unknown.
"""
from dataclasses import dataclass,replace,asdict
from copy import deepcopy
import selectors
import struct
import hashlib
import hmac
from trusted_checker_network.packets import plan,unpad,classify_reply,checksum
from trusted_checker_runtime.profiles import require,Denied
from trusted_checker_runtime.contracts import uid
from .contracts import PROFILE
from .packet_io import NamespaceSocketBroker,KernelTraceSocket,packet_read,packet_statistics,peer_arp_request,approved_peer_arp
from .trace import decode_kernel
from .rules import name


def physical_plan(binding,context):
    result=[]
    for probe in plan(binding,context):
        raw=probe.frame;offset=18 if raw[12:14]==b'\x81\x00' else 14
        if probe.case=='deny_spoofing' and offset==18:
            known={n.mac.replace(':','') for n in (binding.runner,binding.target)}|{binding.bridge_mac.replace(':','')}
            spoof=next(bytes.fromhex('0200000000'+format(i,'02x')) for i in range(240,256)
                       if '0200000000'+format(i,'02x') not in known)
            raw=raw[:6]+spoof+raw[12:]
        if raw[offset]>>4==4 and raw[offset+9]==17:
            # Full 96-bit per-matrix correlation token within nft's bounded
            # transport dump (8 UDP +12 payload bytes), no arbitrary payload.
            ip=bytearray(raw[offset:offset+20]);udp=bytearray(raw[offset+20:]);udp.extend(bytes.fromhex(probe.probe_id[:24]))
            udp[4:6]=struct.pack('!H',len(udp));udp[6:8]=b'\x00\x00'
            udp[6:8]=struct.pack('!H',checksum(bytes(ip[12:20])+struct.pack('!BBH',0,17,len(udp))+bytes(udp)) or 65535)
            ip[2:4]=struct.pack('!H',20+len(udp));ip[10:12]=b'\x00\x00';ip[10:12]=struct.pack('!H',checksum(bytes(ip)))
            raw=raw[:offset]+bytes(ip)+bytes(udp)
        probe=replace(probe,frame=raw)
        result.append(probe)
    return tuple(result)


class PhysicalSockets:
    def __init__(self,activation,inventory):self.activation,self.inventory=activation,inventory;self.packets={};self.trace=None
    def open(self,budget):
        started=budget.monotonic()
        require(not self.activation.offline,'physical_sockets_cannot_be_mock')
        broker=NamespaceSocketBroker(self.activation,self.inventory)
        try:
            for role in ('runner','target','host_runner'):self.packets[role]=broker.open(role,budget)
            self.trace=KernelTraceSocket(self.activation).open(budget)
            for sock in self.packets.values():
                require(packet_statistics(sock)==0,'physical_capture_not_empty')
            self.read_counts={k:0 for k in self.packets}
            self.total_events=0;budget.record('socket_setup',started)
            return self
        except BaseException:self.close();raise
    def send(self,probe,budget):
        started=budget.monotonic()
        self.activation.check('mutate');self.packets['runner'].settimeout(budget.remaining(.1))
        require(self.packets['runner'].send(probe.frame)==len(probe.frame),'physical_packet_send_incomplete')
        self.packets['runner'].setblocking(False)
        budget.record('packet_injection',started)
    def prime_peer(self,budget):
        raw=peer_arp_request(self.activation.approval.binding)
        self.packets['runner'].settimeout(budget.remaining(.1))
        require(self.packets['runner'].send(raw)==len(raw),'physical_arp_send_incomplete')
        self.packets['runner'].setblocking(False)
        for role,frame,address in self.poll(budget,.1):
            if role=='trace':decode_kernel(frame,address)
            else:require(approved_peer_arp(frame,self.activation.approval.binding),'physical_arp_window_not_quiet')
    def poll(self,budget,seconds):
        output=[]
        with selectors.DefaultSelector() as selector:
            for role,sock in self.packets.items():selector.register(sock,selectors.EVENT_READ,role)
            selector.register(self.trace.socket,selectors.EVENT_READ,'trace')
            end=budget.monotonic()+seconds
            while budget.monotonic()<end:
                for key,_ in selector.select(min(end-budget.monotonic(),budget.remaining())):
                    if key.data=='trace':
                        raw,peer=self.trace.recv();output.append(('trace',raw,peer))
                    else:
                        raw,address=packet_read(key.fileobj);self.read_counts[key.data]+=1
                        output.append((key.data,raw,address))
                    require(len(output)<=PROFILE.packet_limit,'physical_capture_event_limit')
                    self.total_events+=1;require(self.total_events<=PROFILE.packet_limit,'physical_capture_event_limit')
        return output
    def finish(self):
        for role,sock in self.packets.items():
            require(packet_statistics(sock)==self.read_counts[role],'physical_capture_unread_packets')
    def close(self):
        for sock in self.packets.values():sock.close()
        if self.trace is not None:self.trace.close()


@dataclass(frozen=True)
class CollectionReport:
    context_uuid: str
    binding_digest: str
    origin: str
    reason: str
    observations: tuple
    timings: dict
    scope: str
    result: str = 'unknown'
    matrix_complete: bool = False
    probe_permitted: bool = False
    def __post_init__(self):
        require(self.result=='unknown' and self.matrix_complete is False and self.probe_permitted is False,
                'physical_capture_cannot_prove_continuity')


class BoundedPhysicalCollector:
    def __init__(self,activation,inventory,reader,journal,*,offline_sockets=None):
        require(activation.offline or offline_sockets is None,'physical_mock_capture_forbidden')
        require(journal.origin==activation.origin,'physical_capture_store_origin_mismatch')
        if not activation.offline:
            from .inventory import NamespaceInventory
            from .installer import IndependentNftReadback
            from .io import LinuxIO
            require(type(inventory) is NamespaceInventory and type(reader) is IndependentNftReadback and
                    type(inventory.io) is LinuxIO and type(reader.io) is LinuxIO,'physical_mock_inventory_forbidden')
        self.activation,self.inventory,self.reader,self.journal=activation,inventory,reader,journal
        self.offline_sockets=offline_sockets
    def _guard(self,budget):
        a=self.activation.check('mutate');budget.remaining()
        from .artifacts import source_digest
        require(source_digest()==a.source_digest,'physical_capture_artifact_changed')
        require(not self.journal.stopped(),'physical_capture_killed')
        with self.journal.transaction() as db:
            state=db.execute('SELECT * FROM control').fetchone()
            require(state['stage']=='active' and not state['blocked'],'physical_active_rules_unproven')
            expected=self.journal.get(db,'recipe','active')
            import json
            handles=tuple(json.loads(state['handles']))
        self.reader.read(budget,a,expected,handles)
        self.inventory.observe(budget)
        return a
    def measure(self,context,budget):
        uid(context);a=self.activation.check('mutate')
        with self.journal.transaction() as db:
            existing=db.execute("SELECT 1 FROM docs WHERE kind='capture_unknown' AND id=?",(context,)).fetchone()
            if existing:
                saved=self.journal.get(db,'capture_unknown',context);saved['observations']=tuple(saved['observations'])
                return CollectionReport(**saved)
        observations=[];sockets=None;started=budget.monotonic()
        reason='physical_collector_unknown'
        try:
            a=self._guard(budget)
            with self.journal.transaction() as db:
                exists=db.execute("SELECT 1 FROM docs WHERE kind='capture_dispatch' AND id=?",(context,)).fetchone()
                require(exists is None,'physical_capture_replay')
                self.journal.put(db,'capture_dispatch',context,{'binding':a.binding.digest,'deadline':budget.absolute})
            probes=physical_plan(a.binding,context)
            sockets=self.offline_sockets if self.activation.offline else PhysicalSockets(self.activation,self.inventory)
            require(sockets is not None,'physical_capture_backend_missing')
            sockets.open(budget);end=budget.monotonic()+min(PROFILE.capture_seconds,budget.remaining(PROFILE.capture_seconds))
            sockets.prime_peer(budget)
            cache={};event_count=0
            for probe in probes:
                self.activation.check('mutate');require(not self.journal.stopped(),'physical_capture_killed')
                require(budget.monotonic()<end,'physical_capture_deadline')
                sockets.send(probe,budget)
                chain=['send'];reply=None
                for role,raw,address in sockets.poll(budget,.1):
                    event_count+=1;require(event_count<=PROFILE.packet_limit,'physical_capture_event_limit')
                    if role=='trace':
                        for event in decode_kernel(raw,address):
                            require(event.table==name(a.approval_uuid) and event.chain=='prerouting','physical_foreign_kernel_hook')
                            if event.frame is not None:
                                # Only this currently issued probe can join a trace
                                # cache. Earlier/foreign sequence cannot be adopted.
                                require(unpad(event.frame)==probe.frame,'physical_foreign_kernel_packet')
                                require(event.iif==a.binding.runner.ifindex,'physical_kernel_ingress_changed')
                                old=cache.get(event.trace_id)
                                require(old is None or old==probe.probe_id,'physical_trace_id_collision')
                                cache[event.trace_id]=probe.probe_id
                            if event.verdict==0:
                                require(cache.get(event.trace_id)==probe.probe_id and event.event_type==1,
                                        'physical_drop_trace_unbound')
                                chain.append('drop')
                    else:
                        require(role in ('host_runner','target','runner') and type(address) is tuple and len(address)>=3,
                                'physical_packet_source_invalid')
                        if approved_peer_arp(raw,a.binding):continue
                        packet=unpad(raw)
                        if packet==probe.frame:
                            if role=='host_runner' and address[2] in (0,3):chain.append('ingress')
                            elif role=='target' and address[2] in (0,3):chain.append('target_delivery')
                        elif probe.response_required and role in ('target','runner'):
                            reply=classify_reply(probe,a.binding,packet)
                            if role=='target' and address[2]==4:chain.append('target_response')
                            elif role=='runner' and address[2] in (0,3):chain.append('runner_receive')
                if probe.response_required:
                    # AF_PACKET and NETLINK are independent queues; arrival in
                    # userspace is not wire order. Exact nonce/ACK and kernel
                    # hook provenance establish the bounded causal relation.
                    require(sorted(chain)==sorted(['send','ingress','target_delivery','target_response','runner_receive']),
                            'physical_allow_chain_incomplete')
                    observations.append(reply)
                else:
                    require(sorted(chain)==['drop','ingress','send'],'physical_drop_trace_missing')
                    observations.append('drop_observed')
            sockets.finish();self._guard(budget);budget.record('collector',started)
            reason='native_nftrace_continuity_unproven'
        except Exception as error:
            allowed={'physical_drop_trace_missing','physical_allow_chain_incomplete','physical_capture_killed',
                'physical_capture_deadline','physical_deadline_expired','physical_packet_capture_loss',
                'physical_packet_truncated','physical_kernel_event_not_kernel','physical_pid_namespace_reuse',
                'physical_foreign_kernel_packet','physical_foreign_kernel_hook','physical_veth_identity_changed',
                'physical_extra_namespace_interface','physical_capture_replay'}
            reason=str(error) if type(error) is Denied and str(error) in allowed else 'physical_collector_unknown'
        finally:
            if sockets is not None:sockets.close()
        self.journal.stop()
        a=self.activation.approval
        report=CollectionReport(context,a.binding.digest,self.activation.origin,reason,tuple(observations),deepcopy(budget.timings),a.scope)
        with self.journal.transaction() as db:self.journal.put(db,'capture_unknown',context,asdict(report))
        return report


class CollectorSealer:
    """Keys in collector service, never in the namespace/socket helper."""
    def __init__(self,activation,journal,principal):
        principal.__post_init__();require(principal.role=='collector','physical_collector_principal_required')
        self.activation,self.journal,self.principal=activation,journal,principal
    def seal(self,report):
        from .contracts import Authenticator,Signed
        require(type(report) is CollectionReport and report.origin==self.activation.origin and
                report.scope==self.principal.scope,'physical_capture_origin_mismatch')
        report.__post_init__()
        with self.journal.transaction() as db:
            import json
            require(self.journal.get(db,'capture_unknown',report.context_uuid)==json.loads(json.dumps(asdict(report))),
                    'physical_capture_not_issued')
        raw=Authenticator.raw('capture',self.principal.name,report)
        return Signed('capture',self.principal.name,report,hmac.new(self.principal.key,raw,hashlib.sha256).hexdigest())


class PhysicalProbeGate:
    """No authority token conversion. Full matrix proof is currently unavailable."""
    @staticmethod
    def permit(report):
        require(type(report) is CollectionReport and report.origin=='physical_linux' and report.matrix_complete is True and
                report.probe_permitted is True,'physical_network_boundary_not_accepted')
        require(False,'physical_network_boundary_not_accepted')
