"""Standalone H1 helper state machine and supervisor, fake execution only.

No native launch on import/construction. No shell, pathname exec, stdin command
or generic PID kill surface. Wire acceptance alone never establishes OS facts.
"""
from dataclasses import dataclass,field
from threading import Event,Lock,RLock

from . import native_v2_contracts as c
from . import native_v2_capture_contracts as cap
from . import native_v2_helper_protocol as p
from . import native_v2_helper_identity as identity


def phase_commitment_h1(invocation,phase):
    c._enum(phase,('ready','entered','credentials','exec'))
    return bytes.fromhex(c._hash('helper_phase',(invocation.digest,phase,invocation.fd_catalog_digest,
                                               invocation.policy.environment)))


class ControlChannelH1:
    """Owned in-memory channel; raw protocol is NOT cryptographic authentication."""
    def __init__(self,invocation):
        self.codec=p.HelperCodecH1(invocation);self.frames=[];self.bytes=0;self.closed=False
        self.cancel_frames=[];self.transform=None;self._sequence=0
        self.finished_at=None;self._control=RLock();self._cancelled=False;self.dispatch_committed=False

    def send(self,kind,payload=b''):
        p.require(not self.closed,'sequence_invalid')
        raw=self.codec.encode(p.HelperMessageH1(kind,self._sequence,payload));self._sequence+=1
        if self.transform is not None:raw=self.transform(raw)
        p.require(type(raw) is bytes and len(raw)<=p.MAX_FRAME and len(self.frames)<p.MAX_MESSAGES and
                  self.bytes+len(raw)<=cap.MAX_AGGREGATE+2*1048576,'protocol_invalid')
        self.bytes+=len(raw);self.frames.append(raw)

    def cancel(self):
        with self._control:
            if self.closed or self._cancelled:return
            p.require(not self.cancel_frames,'sequence_invalid')
            raw=self.codec.encode(p.HelperMessageH1('cancel',1,b''))
            self.cancel_frames.append(raw);self._cancelled=True

    def receive_cancel(self):
        with self._control:
            if not self.cancel_frames:return self._cancelled
            p.require(len(self.cancel_frames)==1,'sequence_invalid')
            message=self.codec.decode(self.cancel_frames.pop())
            p.require(message.kind=='cancel' and message.sequence==1,'sequence_invalid')
            return True

    def dispatch(self,operation):
        # Cancellation and dispatch commit serialize here. Once committed, a
        # concurrent cancel stops polling/cleanup; it cannot undo the dispatch.
        with self._control:
            p.require(not self.closed and not self._cancelled,'killed')
            self.dispatch_committed=True
            return operation()

    def seal(self):
        with self._control:self.closed=True;self.cancel_frames.clear()


class HelperTranscriptH1:
    """Pure order/length/byte/hash validation, independent of helper emission."""
    def __init__(self,invocation):
        self.invocation=invocation;self.codec=p.HelperCodecH1(invocation);self.sequence=0
        self.stage=0;self.eof=set();self.stdout=bytearray();self.stderr=bytearray()
        self.exit=False;self.cleanup=None;self.complete=False;self.error=None
        self._failed=False

    def accept(self,raw):
        p.require(not self._failed,'protocol_invalid')
        try:return self._accept(raw)
        except BaseException:
            self._failed=True;raise

    def _accept(self,raw):
        message=self.codec.decode(raw)
        p.require(not self.complete and self.error is None and message.sequence==self.sequence,'sequence_invalid')
        self.sequence+=1;kind=message.kind;data=message.payload
        if kind=='error':
            self.error=(p.REASONS[int.from_bytes(data[:2],'big')],bool(data[2]));return
        phases=('ready','entered','credentials','exec')
        if self.stage<4:
            p.require(kind==phases[self.stage] and data==phase_commitment_h1(self.invocation,kind),'sequence_invalid')
            self.stage+=1;return
        if kind in ('stdout','stderr'):
            p.require(kind not in self.eof and not self.exit and self.cleanup is None,'sequence_invalid')
            buffer=self.stdout if kind=='stdout' else self.stderr
            op=cap.operation2(self.invocation.request.source)
            bound=op.stdout_cap if kind=='stdout' else op.stderr_cap
            p.require(len(buffer)+len(data)<=bound,kind+'_limit')
            p.require(len(self.stdout)+len(self.stderr)+len(data)<=cap.MAX_AGGREGATE,'aggregate_limit')
            buffer.extend(data)
        elif kind in ('stdout_eof','stderr_eof'):
            stream=kind[:-4];p.require(stream not in self.eof and not self.exit,'sequence_invalid');self.eof.add(stream)
        elif kind=='exit':
            p.require(self.eof=={'stdout','stderr'} and not self.exit and int.from_bytes(data,'big')==0,'incomplete_output')
            self.exit=True
        elif kind=='reaped':
            p.require(self.exit and self.cleanup is None,'sequence_invalid');self.cleanup=data
        elif kind=='complete':
            p.require(self.exit and self.cleanup is not None,'sequence_invalid')
            expected=bytes.fromhex(p.sha(bytes(self.stdout)))+bytes.fromhex(p.sha(bytes(self.stderr)))
            expected+=len(self.stdout).to_bytes(8,'big')+len(self.stderr).to_bytes(8,'big')+self.cleanup
            p.require(data==expected,'incomplete_output');self.complete=True
        else:raise c.ContractViolation2('v2_helper_sequence_invalid')

    def finish(self):
        try:p.require(not self._failed and (self.complete or self.error is not None),'incomplete_output')
        except BaseException:
            self._failed=True;raise


@dataclass(frozen=True,slots=True)
class HelperResultH1(c._Offline2):
    invocation_digest: str
    result: str
    reason: str
    cleanup: str
    stdout: bytes = field(repr=False)
    stderr: bytes = field(repr=False)
    transcript_digest: str
    isolation_verified: bool = field(default=False,init=False)
    management_policy_verified: bool = field(default=False,init=False)
    measurement_verified: bool = field(default=False,init=False)
    native_identity: str = field(default='native_identity_unreviewed',init=False)
    native_process_tree: str = field(default='unproven',init=False)

    def __post_init__(self):
        c._Offline2.__post_init__(self);c._hex(self.invocation_digest);c._hex(self.transcript_digest)
        c._enum(self.result,('helper_fake_capture_preserved','unknown'))
        c._enum(self.reason,('offline_helper_model_complete',*p.REASONS))
        c._enum(self.cleanup,('no_dispatch','reaped_closed','cleanup_unproven'))
        p.require(type(self.stdout) is bytes and len(self.stdout)<=1048576 and
                  type(self.stderr) is bytes and len(self.stderr)<=4096,'incomplete_output')
        p.require((self.result=='helper_fake_capture_preserved' and self.reason=='offline_helper_model_complete' and
                   self.cleanup=='reaped_closed') or (self.result=='unknown' and self.stdout==self.stderr==b'' and
                   self.reason!='offline_helper_model_complete'),'incomplete_output')
        p.require(self.isolation_verified is False and self.management_policy_verified is False and
                  self.measurement_verified is False and self.native_identity=='native_identity_unreviewed' and
                  self.native_process_tree=='unproven','identity_mismatch')

    @property
    def digest(self):
        self.__post_init__()
        return c._hash('helper_result',(self.invocation_digest,self.result,self.reason,self.cleanup,
                       p.sha(self.stdout),len(self.stdout),p.sha(self.stderr),len(self.stderr),self.transcript_digest))


def _finite_reason(error):
    if type(error) is c.ContractViolation2:
        reason=str(error).removeprefix('v2_helper_')
        if reason in p.REASONS:return reason
    if isinstance(error,TimeoutError):return 'timeout'
    return 'evidence_invalid'


class StandaloneHelperH1:
    """Single fake invocation, with recoverable resources on every exit path."""
    def __init__(self):self._used=False

    def run_fake(self,invocation,invoke_frame,transferred,kernel,channel):
        from .native_v2_helper_fake import FakeHelperKernelH1,MAX_TRANSFER_FDS
        p.require(type(kernel) is FakeHelperKernelH1 and type(channel) is ControlChannelH1,'native_identity_unreviewed')
        c._typed(invocation,p.HelperInvocationH1);p.require(not self._used,'replay');self._used=True
        i=invocation;codec=p.HelperCodecH1(i);owned=None;fds=();receipt=();last=i.session.started
        stdout=bytearray();stderr=bytearray();reason=None;clean=True;interruptions=[]
        def fence():
            nonlocal last
            now=kernel.clock();c._typed(now,cap.CaptureTime2)
            p.require(now.monotonic_us>=last.monotonic_us and now.wall_utc_us>=last.wall_utc_us,'clock_rollback')
            last=now
            p.require(now.monotonic_us<=i.deadline_monotonic_us and
                      now.wall_utc_us-i.session.started.wall_utc_us<=i.policy.timing.command_us,'timeout')
            watch=next((fd.local_fd for fd in fds if fd.slot=='parent_watch'),None)
            p.require(watch is not None and kernel.parent_alive(watch,i.parent_pid,i.parent_start_ticks),'parent_died')
            p.require(not channel.receive_cancel(),'killed')
        try:
            # Driver-owned bounded receipt exists before any untrusted semantic
            # validation. A malformed projection cannot erase actual ownership.
            receipt=kernel.transfer_receipt(i)
            p.require(type(receipt) is tuple and len(receipt)<=MAX_TRANSFER_FDS,'fd_transfer_invalid')
            p.require(type(transferred) is tuple and len(transferred)==7,'fd_transfer_invalid')
            fds=transferred
            for fd in fds:c._typed(fd,p.ReceivedDescriptorH1)
            p.require(tuple(fd.slot for fd in fds)==p.SLOTS and len({fd.local_fd for fd in fds})==7 and
                      {fd.local_fd for fd in fds}=={fd.local_fd for fd in receipt},'fd_transfer_invalid')
            message=codec.decode(invoke_frame)
            p.require(message.kind=='invoke' and message.sequence==0 and
                      message.payload==bytes.fromhex(i.fd_catalog_digest),'binding_mismatch')
            actual_fds=tuple(sorted(fd.local_fd for fd in fds))
            for fd,spec in zip(fds,i.descriptors):
                observed=kernel.describe_fd(fd.local_fd);c._typed(observed,p.DescriptorIdentityH1)
                p.require(observed==spec.identity,'fd_transfer_invalid')
            fence()
            identity.validate_identity_h1(kernel.identity('before'),i,'before',actual_fds)
            channel.send('ready',phase_commitment_h1(i,'ready'));fdmap={fd.slot:fd.local_fd for fd in fds}
            kernel.verify_executable_fd(fdmap['executable'],i.executable)
            kernel.enter_namespace(fdmap['namespace'])
            fence();identity.validate_identity_h1(kernel.identity('entered'),i,'entered',actual_fds)
            channel.send('entered',phase_commitment_h1(i,'entered'))
            p.require(kernel.drop_credentials(i.policy.command_principal) is True,'privilege_drop_failed')
            identity.validate_identity_h1(kernel.identity('credentials'),i,'credentials',actual_fds)
            channel.send('credentials',phase_commitment_h1(i,'credentials'))
            kernel.prepare_child_fds(fdmap,(0,1,2));fence()
            kernel.prepare_owned(i,'child')
            owned=kernel.reserve_child(i.invocation_uuid)
            p.require(owned==kernel.recover_owned(i,'child'),'identity_mismatch')
            # This fence and the channel commit check cover cancellation during
            # reserve. The commit itself serializes with cancel enqueue.
            fence()
            child=channel.dispatch(lambda:kernel.exec_fd_child(owned,fdmap['executable'],
                                                              i.request.argv,i.policy.environment))
            p.require(child==owned,'identity_mismatch');channel.send('exec',phase_commitment_h1(i,'exec'))
            eof=set();exit_code=None
            for _ in range(p.MAX_MESSAGES-16):
                fence();poll=kernel.poll_child(owned,p.CHUNK,i.deadline_monotonic_us)
                p.require(type(poll) is ChildPollH1,'protocol_invalid');poll.__post_init__()
                fence();p.require(poll.helper_alive,'helper_crashed')
                for stream,data in poll.chunks:
                    p.require(stream not in eof and len(data)<=p.CHUNK,'sequence_invalid')
                    buffer=stdout if stream=='stdout' else stderr
                    op=cap.operation2(i.request.source);bound=op.stdout_cap if stream=='stdout' else op.stderr_cap
                    p.require(len(buffer)+len(data)<=bound,stream+'_limit')
                    p.require(len(stdout)+len(stderr)+len(data)<=cap.MAX_AGGREGATE,'aggregate_limit')
                    buffer.extend(data);channel.send(stream,data)
                for stream,ended in (('stdout',poll.stdout_eof),('stderr',poll.stderr_eof)):
                    if ended and stream not in eof:eof.add(stream);channel.send(stream+'_eof')
                if poll.exit_code is not None:
                    p.require(exit_code is None or exit_code==poll.exit_code,'sequence_invalid');exit_code=poll.exit_code
                if eof=={'stdout','stderr'} and exit_code is not None:break
            p.require(eof=={'stdout','stderr'} and exit_code==0,'incomplete_output')
            fence();identity.validate_identity_h1(kernel.identity('final'),i,'final',actual_fds)
            kernel.verify_executable_fd(fdmap['executable'],i.executable)
            channel.send('exit',(0).to_bytes(2,'big'))
        except BaseException as error:
            reason=_finite_reason(error);_remember_interrupt_h1(error,interruptions)
        finally:
            child_clean,_=_recover_cleanup_h1(kernel,i,'child',reason is None,last,interruptions)
            clean=child_clean and clean
            # Last FD-dependent fence precedes closing *any* transferred FD.
            if reason is None and clean:
                try:fence()
                except BaseException as error:
                    reason=_finite_reason(error);_remember_interrupt_h1(error,interruptions)
            try:
                # Retrieve by owned invocation again if the receipt return was
                # lost. Never use untrusted row numbers as close authority.
                receipt=kernel.transfer_receipt(i)
                clean=kernel.close_transferred(tuple(fd for fd in receipt if fd.slot!='control')) is True and clean
            except BaseException as error:
                clean=False;_remember_interrupt_h1(error,interruptions)
        if not clean:reason='cleanup_unproven'
        try:
            if reason is None:
                cleanup=bytes.fromhex(c._hash('helper_child_cleanup',(i.digest,owned,'reaped_closed')))
                channel.send('reaped',cleanup)
                payload=bytes.fromhex(p.sha(bytes(stdout)))+bytes.fromhex(p.sha(bytes(stderr)))
                payload+=len(stdout).to_bytes(8,'big')+len(stderr).to_bytes(8,'big')+cleanup
                channel.send('complete',payload);channel.finished_at=last
            else:channel.send('error',p.REASONS.index(reason).to_bytes(2,'big')+bytes((int(clean),)))
        except BaseException as error:
            reason=_finite_reason(error);_remember_interrupt_h1(error,interruptions)
        finally:
            try:
                if kernel.close_control() is not True:clean=False
            except BaseException as error:
                clean=False;_remember_interrupt_h1(error,interruptions)
            channel.seal();stdout.clear();stderr.clear()
        if not clean:kernel.cleanup_failed=True
        if interruptions:raise interruptions[0]
        return reason,clean


@dataclass(frozen=True,slots=True)
class ChildPollH1:
    chunks: tuple[tuple[str,bytes],...] = field(default=(),repr=False)
    stdout_eof: bool = False
    stderr_eof: bool = False
    exit_code: int | None = None
    helper_alive: bool = True

    def __post_init__(self):
        p.require(type(self.chunks) is tuple and len(self.chunks)<=2,'protocol_invalid')
        for item in self.chunks:
            p.require(type(item) is tuple and len(item)==2,'protocol_invalid');c._enum(item[0],('stdout','stderr'))
            p.require(type(item[1]) is bytes and 0<len(item[1])<=p.CHUNK,'protocol_invalid')
        for value in (self.stdout_eof,self.stderr_eof,self.helper_alive):p.require(type(value) is bool,'protocol_invalid')
        if self.exit_code is not None:c._integer(self.exit_code,0,255)


def _remember_interrupt_h1(error,interruptions):
    if not isinstance(error,Exception):interruptions.append(error)


def _recover_cleanup_h1(kernel,invocation,role,normal,last,interruptions):
    """Recover exclusively by pinned invocation/role, including lost returns."""
    try:owned=kernel.recover_owned(invocation,role)
    except BaseException as error:
        kernel.cleanup_failed=True;_remember_interrupt_h1(error,interruptions);return False,False
    if owned is None:return True,False
    clean=cleanup_owned_h1(kernel,owned,invocation.policy.timing,normal,last,interruptions)
    if not clean:kernel.cleanup_failed=True
    return clean,True


def cleanup_owned_h1(kernel,owned,timing,normal,not_before=None,interruptions=None):
    """Finite best-effort cleanup; remember interruptions and propagate outside.

    No failure is erased by a successful fallback. Reap is attempted even when
    clock/TERM/drain fail. Only an exact owned reference can reach the driver.
    """
    pending=[] if interruptions is None else interruptions;safe=True
    try:
        began=kernel.clock();c._typed(began,cap.CaptureTime2)
        if not_before is not None:
            p.require(began.monotonic_us>=not_before.monotonic_us and began.wall_utc_us>=not_before.wall_utc_us,
                      'cleanup_unproven')
        start=began.monotonic_us;previous=began
        if not normal:
            kernel.terminate_owned(owned);total=0
            for _ in range(16):
                if not kernel.owned_running(owned):break
                now=kernel.clock();c._typed(now,cap.CaptureTime2)
                p.require(now.monotonic_us>=previous.monotonic_us and now.wall_utc_us>=previous.wall_utc_us,
                          'cleanup_unproven');previous=now
                if now.monotonic_us>=start+timing.terminate_us:break
                raw=kernel.drain_owned(owned,p.CHUNK,start+timing.drain_us)
                p.require(type(raw) is bytes and len(raw)<=p.CHUNK,'protocol_invalid')
                total+=len(raw)
                if total>=65536:break
            if kernel.owned_running(owned):kernel.kill_owned(owned)
        deadline=start+timing.terminate_us+timing.drain_us+timing.reap_us
        p.require(kernel.reap_owned(owned,deadline) is True,'cleanup_unproven')
        ended=kernel.clock();c._typed(ended,cap.CaptureTime2)
        p.require(previous.monotonic_us<=ended.monotonic_us<=deadline and
                  ended.wall_utc_us>=previous.wall_utc_us,'cleanup_unproven')
    except BaseException as error:
        safe=False;_remember_interrupt_h1(error,pending)
        try:kernel.kill_owned(owned)
        except BaseException as error:_remember_interrupt_h1(error,pending)
        deadline=0  # Expired/nonblocking best effort if no clock can be read.
        try:deadline=kernel.clock().monotonic_us+timing.reap_us
        except BaseException as error:_remember_interrupt_h1(error,pending)
        try:kernel.reap_owned(owned,deadline)
        except BaseException as error:_remember_interrupt_h1(error,pending)
    finally:
        try:
            if kernel.close_owned(owned) is not True:safe=False
        except BaseException as error:
            safe=False;_remember_interrupt_h1(error,pending)
    if interruptions is None and pending:raise pending[0]
    return safe


class OwnedInvocationRegistryH1:
    """Process-local session fence, bounded to 256; not a durable journal."""
    def __init__(self,session_uuid):
        c._uuid(session_uuid);self.session_uuid=session_uuid;self._seen=set();self._nonces=set()
        self._active=None;self._owner=None;self._circuit=False;self._lock=Lock();self._captured_bytes=0

    def reserve(self,invocation,owner=None):
        c._typed(invocation,p.HelperInvocationH1)
        with self._lock:
            p.require(self._active is None,'sequence_invalid')
            p.require(not self._circuit and len(self._seen)<256 and invocation.session.session_uuid==self.session_uuid and
                      invocation.invocation_uuid not in self._seen and invocation.nonce not in self._nonces,'replay')
            self._owner=invocation if owner is None else owner;self._active=invocation
            self._seen.add(invocation.invocation_uuid);self._nonces.add(invocation.nonce)

    def finish(self,invocation,successful,owner=None):
        with self._lock:
            p.require(self._active is invocation and self._owner is (invocation if owner is None else owner),
                      'identity_mismatch')
            self._active=None;self._owner=None
            if not successful:self._circuit=True

    def active_for(self,invocation,owner=None):
        with self._lock:
            return self._active is invocation and self._owner is (invocation if owner is None else owner)

    def abort(self,invocation,owner=None):
        # Recovery for interrupted reserve/finish. Do not clear another attempt.
        with self._lock:
            p.require(invocation.session.session_uuid==self.session_uuid,'identity_mismatch')
            expected_owner=invocation if owner is None else owner
            if self._active is not None and self._owner is not expected_owner:return
            self._circuit=True
            if self._owner is expected_owner:self._active=None;self._owner=None

    def debit_data(self,amount):
        c._integer(amount,1,p.CHUNK)
        with self._lock:
            p.require(self._active is not None,'sequence_invalid')
            p.require(self._captured_bytes+amount<=cap.MAX_AGGREGATE,'aggregate_limit')
            self._captured_bytes+=amount


class HelperSupervisorH1:
    def __init__(self,invocation,pinned_invocation_digest,kernel,registry,*,enabled=False):
        c._typed(invocation,p.HelperInvocationH1);p.require(invocation.digest==pinned_invocation_digest,'binding_mismatch')
        p.require(type(registry) is OwnedInvocationRegistryH1 and type(enabled) is bool,'protocol_invalid')
        p.require(registry.session_uuid==invocation.session.session_uuid,'binding_mismatch')
        self.invocation=invocation;self.kernel=kernel;self.registry=registry;self.enabled=enabled
        self._terminal=None;self._lock=Lock();self._state=RLock();self._cancel=Event();self._channel=None
        self._reservation_attempted=False
        # Prepared before effects: publication failure cannot require another
        # potentially interrupted constructor to produce a safe immutable record.
        self._fallback=HelperResultH1(invocation.digest,'unknown','cleanup_unproven','cleanup_unproven',
                                     b'',b'',c._hash('helper_transcript',()))

    def capture_native(self):raise c.ContractViolation2('v2_helper_native_identity_unreviewed')

    def kill(self):
        with self._state:
            self._cancel.set()
            if self._terminal is None and self._channel is not None:self._channel.cancel()
        return self._terminal

    def run_fake(self):
        from .native_v2_helper_fake import FakeHelperKernelH1
        p.require(type(self.kernel) is FakeHelperKernelH1,'native_identity_unreviewed')
        p.require(self._lock.acquire(blocking=False),'sequence_invalid')
        try:
            if self._terminal is not None:return self._terminal
            return self._run()
        finally:self._lock.release()

    def _publish(self,reason,clean,had_process,verifier):
        i=self.invocation
        with self._state:
            if self._cancel.is_set() and reason!='cleanup_unproven':reason='killed'
            success=reason=='offline_helper_model_complete'
            transcript=c._hash('helper_transcript',tuple(p.sha(raw) for raw in self._channel.frames))
            terminal=HelperResultH1(i.digest,'helper_fake_capture_preserved' if success else 'unknown',reason,
                'cleanup_unproven' if not clean else 'reaped_closed' if had_process else 'no_dispatch',
                bytes(verifier.stdout) if success else b'',bytes(verifier.stderr) if success else b'',transcript)
            # No issued success is visible before registry finalization.
            if self.registry.active_for(i,self):self.registry.finish(i,success,self)
            elif self._reservation_attempted:self.registry.abort(i,self)
            return terminal

    def _run(self):
        i=self.invocation;attempted=False;clean=True;had_process=False;reason='disabled';verifier=None;interruptions=[]
        self._channel=ControlChannelH1(i)
        try:
            if self.enabled:
                p.require(not self._cancel.is_set(),'killed')
                self._reservation_attempted=True
                self.registry.reserve(i,self)
                attempted=True
                self.kernel.prepare_owned(i,'helper')
                owned=self.kernel.register_helper(i)
                p.require(owned==self.kernel.recover_owned(i,'helper'),'identity_mismatch')
                # Helper dispatch commits under the same lock used by kill.
                with self._state:
                    p.require(not self._cancel.is_set(),'killed')
                    self.kernel.dispatch_helper(owned,i)
                request=self._channel.codec.encode(p.HelperMessageH1('invoke',0,bytes.fromhex(i.fd_catalog_digest)))
                if self.kernel.invoke_transform is not None:request=self.kernel.invoke_transform(request)
                self._channel.transform=self.kernel.frame_transform
                helper_reason,helper_clean=StandaloneHelperH1().run_fake(i,request,self.kernel.received,
                                                                       self.kernel,self._channel)
                clean=helper_clean
                verifier=HelperTranscriptH1(i)
                for raw in self._channel.frames:
                    message=verifier.codec.decode(raw)
                    if message.kind in ('stdout','stderr'):self.registry.debit_data(len(message.payload))
                    verifier.accept(raw)
                verifier.finish()
                if verifier.error is not None:
                    reason,error_clean=verifier.error;clean=clean and error_clean
                else:
                    p.require(helper_reason is None and verifier.complete and self._channel.closed,'incomplete_output')
                    reason='offline_helper_model_complete'
        except BaseException as error:
            reason=_finite_reason(error);_remember_interrupt_h1(error,interruptions)
        finally:
            if attempted:
                # The child may have survived a helper interruption before it
                # could return its cleanup status. Recover both roles by scope.
                last=self._channel.finished_at or i.session.started
                child_clean,child_found=_recover_cleanup_h1(self.kernel,i,'child',False,last,interruptions)
                helper_clean,helper_found=_recover_cleanup_h1(self.kernel,i,'helper',
                    reason=='offline_helper_model_complete',last,interruptions)
                had_process=child_found or helper_found
                clean=child_clean and helper_clean and clean
                try:clean=self.kernel.close_remaining_transferred() is True and clean
                except BaseException as error:
                    clean=False;_remember_interrupt_h1(error,interruptions)
                clean=clean and not self.kernel.cleanup_failed
            try:self._channel.seal()
            except BaseException as error:
                clean=False;_remember_interrupt_h1(error,interruptions)
            if not clean:reason='cleanup_unproven'
        if reason=='offline_helper_model_complete':
            try:
                now=self.kernel.clock();c._typed(now,cap.CaptureTime2)
                ended=self._channel.finished_at;c._typed(ended,cap.CaptureTime2)
                p.require(now.monotonic_us>=ended.monotonic_us and now.wall_utc_us>=ended.wall_utc_us,'clock_rollback')
                p.require(now.monotonic_us<=i.deadline_monotonic_us and
                          now.wall_utc_us-i.session.started.wall_utc_us<=i.policy.timing.command_us,'timeout')
            except BaseException as error:
                reason=_finite_reason(error);_remember_interrupt_h1(error,interruptions)
        try:
            with self._state:
                terminal=self._publish(reason,clean,had_process,verifier)
                self._terminal=terminal  # Publication commit; no driver work follows.
        except BaseException as error:
            _remember_interrupt_h1(error,interruptions)
            try:self.registry.abort(i,self)
            except BaseException as error:_remember_interrupt_h1(error,interruptions)
            finally:
                with self._state:self._terminal=self._fallback
        if interruptions:raise interruptions[0]
        return self._terminal

    def admit(self,result):
        c._typed(result,HelperResultH1)
        p.require(result is self._terminal and result.result=='helper_fake_capture_preserved' and
                  not self._cancel.is_set(),'replay')
        return result
