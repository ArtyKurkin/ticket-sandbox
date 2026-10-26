"""Finite fake ownership/FD/clock model. Never an OS attestation source.

The received projection is distinct from the bounded owned-transfer catalog.
Observations are copied at fixture setup and subsequently read from live fake
state, never reconstructed from the expected invocation during verification.
"""
from dataclasses import dataclass,replace

from . import native_v2_contracts as c
from . import native_v2_capture_contracts as cap
from . import native_v2_helper_protocol as p
from . import native_v2_helper_identity as identity
from . import native_v2_os_contracts as os_contracts
from .native_v2_helper_runtime import ChildPollH1

MAX_TRANSFER_FDS=16


@dataclass(frozen=True,slots=True)
class FakeObservationsH1:
    """Separately authored fake facts; never supplied by inspected wire input."""
    received: tuple[p.ReceivedDescriptorH1,...]
    descriptor_facts: tuple[tuple[int,p.DescriptorIdentityH1],...]
    executable: os_contracts.ExecutableObservation2
    identity: identity.IdentitySnapshotH1

    def __post_init__(self):
        c._rows(self.received,p.ReceivedDescriptorH1,0,MAX_TRANSFER_FDS)
        p.require(type(self.descriptor_facts) is tuple and len(self.descriptor_facts)<=MAX_TRANSFER_FDS,
                  'fd_transfer_invalid')
        seen=set()
        for row in self.descriptor_facts:
            p.require(type(row) is tuple and len(row)==2,'fd_transfer_invalid')
            c._integer(row[0],3,2**20-1);c._typed(row[1],p.DescriptorIdentityH1)
            p.require(row[0] not in seen,'fd_transfer_invalid');seen.add(row[0])
        c._typed(self.executable,os_contracts.ExecutableObservation2)
        c._typed(self.identity,identity.IdentitySnapshotH1)


class FakeHelperKernelH1:
    def __init__(self,invocation,polls,*,observations):
        c._typed(invocation,p.HelperInvocationH1);c._rows(polls,ChildPollH1,0,p.MAX_MESSAGES)
        c._typed(observations,FakeObservationsH1)
        self.invocation=invocation;self.polls=polls;self.calls=[];self.now=invocation.session.started
        self.step_us=100;self.clock_sequence=();self.closed_received=set();self._transfer_catalog={};self._fd_pins=None
        self._transfer_claimed=False
        self.received=observations.received
        self.fd_facts={fd:replace(facts) for fd,facts in observations.descriptor_facts}
        self.executable_observation=replace(observations.executable)
        self.identity_observation=replace(observations.identity)
        self.identity_transform=None;self.frame_transform=None;self.invoke_transform=None
        self.drop_ok=True;self.parent_ok=True;self.lost_spawn=False;self.helper_crash=False
        self.term_effective=True;self.reap_ok=True;self.close_ok=True;self.transfer_close_ok=True;self.control_close_ok=True
        self.drain_data=b'';self.executable_ok=True;self.unexpected_child_fd=False;self.on_poll=None
        self.child_exec_error=False;self.close_control_hook=None;self._objects={};self._poll_index=0
        self._namespace_entered=False;self._credentials_dropped=False;self._helper_owned=None
        self._escrows={};self.recovery_ok=True;self._fd_cleanup_failed=False;self.cleanup_failed=False

    @property
    def received(self):return self._received

    @received.setter
    def received(self,rows):
        # Trusted fake receiver setup, not a wire-directed FD close API. The
        # receive boundary cannot create/retain more than 16 owned descriptors.
        p.require(not self._transfer_claimed and type(rows) is tuple and len(rows)<=MAX_TRANSFER_FDS,
                  'fd_transfer_invalid')
        self._received=rows
        if all(type(row) is p.ReceivedDescriptorH1 for row in rows):
            for row in rows:row.__post_init__()
            self._transfer_catalog={row.local_fd:row for row in rows}
        # A malformed projection cannot erase the separately recorded actual
        # transfer. Tests can corrupt rows while the real owned catalog remains.

    def transfer_receipt(self,invocation):
        p.require(invocation==self.invocation,'identity_mismatch')
        if not self._transfer_claimed:
            self._transfer_claimed=True
            self._fd_pins={fd:self.fd_facts.get(fd) for fd in self._transfer_catalog}
        return tuple(self._transfer_catalog.values())

    @property
    def open_transferred_count(self):return len(set(self._transfer_catalog)-self.closed_received)

    def _open_fd(self,fd):
        p.require(type(fd) is int and fd in self._transfer_catalog and fd not in self.closed_received,
                  'fd_transfer_invalid')
        facts=self.fd_facts.get(fd);p.require(type(facts) is p.DescriptorIdentityH1,'fd_transfer_invalid')
        facts.__post_init__()
        if self._fd_pins is not None:
            p.require(facts==self._fd_pins[fd],'fd_transfer_invalid')
        return facts

    def clock(self):
        if self.clock_sequence:
            value,self.clock_sequence=self.clock_sequence[0],self.clock_sequence[1:];self.now=value;return value
        self.now=cap.CaptureTime2(self.now.wall_utc_us+self.step_us,self.now.monotonic_us+self.step_us);return self.now

    def parent_alive(self,watch_fd,pid,ticks):
        self.calls.append(('parent_check',watch_fd,pid,ticks));facts=self._open_fd(watch_fd)
        return self.parent_ok and facts.kind=='pidfd' and (pid,ticks)==(
            self.identity_observation.parent_pid,self.identity_observation.parent_start_ticks)

    def describe_fd(self,fd):self.calls.append(('describe_fd',fd));return self._open_fd(fd)

    def identity(self,phase):
        self.calls.append(('identity',phase))
        for fd in self._transfer_catalog:self._open_fd(fd)
        snapshot=replace(self.identity_observation,inherited_fds=tuple(sorted(self._transfer_catalog)),
                         executable_object_digest=p.executable_object_digest_h1(self.executable_observation))
        return self.identity_transform(snapshot,phase) if self.identity_transform is not None else snapshot

    def verify_executable_fd(self,fd,expected):
        self.calls.append(('verify_executable',fd));facts=self._open_fd(fd)
        observed=self.executable_observation;c._typed(observed,type(expected))
        p.validate_executable_h1(observed,self.invocation.policy.command_principal)
        p.require(self.executable_ok and facts.kind=='regular' and
                  (facts.device,facts.inode,facts.object_digest)==(observed.device,observed.inode,
                      p.executable_object_digest_h1(observed)) and
                  p.executable_object_digest_h1(observed)==p.executable_object_digest_h1(expected),
                  'executable_mismatch')

    def enter_namespace(self,fd):
        facts=self._open_fd(fd);p.require(facts.kind=='netns','fd_transfer_invalid')
        self.calls.append(('enter_namespace_child_only',fd));self._namespace_entered=True
        self.identity_observation=replace(self.identity_observation,namespace_inode=facts.inode)

    def drop_credentials(self,principal):
        self.calls.append(('drop_credentials',principal.digest))
        if self.drop_ok:
            self._credentials_dropped=True;self.identity_observation=replace(self.identity_observation,principal=principal)
        return self.drop_ok

    def prepare_child_fds(self,fdmap,allowlist):
        for fd in fdmap.values():self._open_fd(fd)
        self.calls.append(('prepare_child_fds',tuple(sorted(fdmap.items())),allowlist))
        p.require(allowlist==(0,1,2) and not self.unexpected_child_fd,'fd_transfer_invalid')

    def prepare_owned(self,invocation,role):
        p.require(invocation==self.invocation,'identity_mismatch');c._enum(role,('helper','child'))
        key=(invocation.digest,role)
        p.require(key not in self._escrows,'replay')
        self._escrows[key]=c._hash('fake_owned_process',(key,invocation.invocation_uuid))

    def recover_owned(self,invocation,role):
        p.require(self.recovery_ok and invocation==self.invocation,'cleanup_unproven')
        c._enum(role,('helper','child'));token=self._escrows.get((invocation.digest,role))
        obj=self._objects.get(token)
        if obj is None or (obj['closed'] and obj['reaped']):return None
        return token

    def _reserve(self,role,key):
        p.require(key==self.invocation.invocation_uuid,'identity_mismatch')
        token=self._escrows.get((self.invocation.digest,role))
        p.require(token is not None and token not in self._objects,'replay')
        self._objects[token]={'role':role,'running':True,'reaped':False,'closed':False}
        self.calls.append(('register_owned',role,token));return token

    def register_helper(self,invocation):
        p.require(invocation==self.invocation,'identity_mismatch')
        self._helper_owned=self._reserve('helper',invocation.invocation_uuid);return self._helper_owned

    def dispatch_helper(self,owned,invocation):
        self._owned(owned);self.calls.append(('dispatch_helper',owned))
        if self.lost_spawn:raise c.ContractViolation2('v2_helper_spawn_response_lost')
        if self.helper_crash:raise c.ContractViolation2('v2_helper_helper_crashed')

    def reserve_child(self,invocation_uuid):return self._reserve('child',invocation_uuid)

    def exec_fd_child(self,owned,fd,argv,environment):
        self._owned(owned);self.verify_executable_fd(fd,self.invocation.executable)
        self.calls.append(('exec_fd_child',owned,fd,argv,environment))
        p.require(argv==self.invocation.request.argv and environment==self.invocation.policy.environment,'protocol_invalid')
        if self.child_exec_error:raise c.ContractViolation2('v2_helper_helper_crashed')
        return owned

    def poll_child(self,owned,maximum,deadline):
        self._owned(owned);self.calls.append(('poll_child',maximum,deadline))
        if self.on_poll is not None:self.on_poll()
        if self._poll_index>=len(self.polls):return ChildPollH1()
        result=self.polls[self._poll_index];self._poll_index+=1
        if result.exit_code is not None:self._objects[owned]['running']=False
        return result

    def _owned(self,owned):
        p.require(type(owned) is str and owned in self._objects and not self._objects[owned]['closed'],'identity_mismatch')
        return self._objects[owned]

    def terminate_owned(self,owned):
        obj=self._owned(owned);self.calls.append(('term',obj['role'],owned))
        if self.term_effective:obj['running']=False

    def owned_running(self,owned):return self._owned(owned)['running']

    def kill_owned(self,owned):
        obj=self._owned(owned);self.calls.append(('kill',obj['role'],owned));obj['running']=False

    def drain_owned(self,owned,maximum,deadline):
        self._owned(owned);self.calls.append(('drain',maximum,deadline));return self.drain_data

    def reap_owned(self,owned,deadline):
        obj=self._owned(owned);self.calls.append(('reap',obj['role'],owned,deadline))
        # Finite fake direct-child model only. No accepted native exit/signal or
        # descendant/process-tree proof follows from this boolean.
        if obj['role']=='helper' and self.control_close_ok:obj['running']=False
        obj['reaped']=self.reap_ok and not obj['running'];return obj['reaped']

    def close_owned(self,owned):
        obj=self._owned(owned);self.calls.append(('close_owned',obj['role'],owned))
        if self.close_ok and obj['reaped']:obj['closed']=True;return True
        return False

    def close_transferred(self,received):
        # Close authority comes from the actual owned catalog, not row.slot or
        # arbitrary supplied FD numbers. Each owned FD is attempted once here.
        self.calls.append(('close_transferred',tuple(fd.local_fd for fd in received)))
        safe=True;seen=set()
        for row in received:
            c._typed(row,p.ReceivedDescriptorH1);fd=row.local_fd
            p.require(fd in self._transfer_catalog,'fd_transfer_invalid')
            if fd in seen or fd in self.closed_received:continue
            seen.add(fd)
            if not self.transfer_close_ok:
                self._fd_cleanup_failed=True;safe=False;continue
            if self._fd_pins is not None and self.fd_facts.get(fd)!=self._fd_pins.get(fd):
                self._fd_cleanup_failed=True;safe=False;continue  # Replacement is not our close target.
            self.calls.append(('close_fd',fd));self.closed_received.add(fd)
        return safe

    def close_control(self):
        rows=tuple(row for fd,row in self._transfer_catalog.items()
                   if row.slot=='control' and fd not in self.closed_received)
        if not rows:return True
        self.calls.append(('close_control',))
        if self.close_control_hook is not None:self.close_control_hook()
        if not self.control_close_ok:self._fd_cleanup_failed=True;return False
        return self.close_transferred(rows)

    def close_remaining_transferred(self):
        rows=tuple(row for fd,row in self._transfer_catalog.items()
                   if fd not in self.closed_received and row.slot!='control')
        safe=self.close_transferred(rows) if rows else True
        control=self.close_control()
        return safe and control and self.open_transferred_count==0 and not self._fd_cleanup_failed
