"""Separate dormant OS orchestration; exercised ONLY with an exact fake driver.

Native entry has no accepted activation authority in this revision. The old
collector/fake are not imported, replaced or used as native execution fallback.
The driver contract requires a standalone namespace helper, descriptor execution
and an attempt-owned child supervisor; launching from Django is never allowed.
"""
from dataclasses import dataclass, field
from threading import Event, Lock

from . import native_v2_contracts as c
from . import native_v2_capture_contracts as capture
from . import native_v2_os_contracts as o


@dataclass(frozen=True, slots=True)
class ProcessPoll2:
    chunks: tuple[tuple[str,bytes], ...] = field(default=(),repr=False)
    stdout_eof: bool = False
    stderr_eof: bool = False
    exit_status: int | None = None
    helper_completed: bool = False
    control_eof: bool = False
    reader_alive: bool = True
    interrupted: bool = False
    helper_record: o.HelperAttestation2 | None = None

    def __post_init__(self):
        o.require(type(self.chunks) is tuple and len(self.chunks)<=2,'driver_protocol_invalid')
        for item in self.chunks:
            o.require(type(item) is tuple and len(item)==2,'driver_protocol_invalid')
            c._enum(item[0],('stdout','stderr'));o.require(type(item[1]) is bytes,'driver_protocol_invalid')
        for value in (self.stdout_eof,self.stderr_eof,self.helper_completed,self.control_eof,self.reader_alive,self.interrupted):
            o.require(type(value) is bool,'driver_protocol_invalid')
        if self.exit_status is not None:c._integer(self.exit_status,0,255)
        if self.helper_record is not None:c._typed(self.helper_record,o.HelperAttestation2)


class OSReadDriver2:
    """Port contract, with no default OS implementation or implicit discovery.

    clock(): independent supervisor wall+monotonic clock, not child stdout.
    observe(): trusted supervisor principal/FD/PID/session/epoch observations.
    open_executable(): secure component walk, descriptor hash+identity, held FD.
    spawn(): ONLY a separately reviewed standalone helper; parent never setns.
      Must register invocation in supervisor before dispatch, so lost spawn
      response can still cancel/reap the owned child. No arbitrary child PIDs.
    poll(): deadline-bounded multiplexed reads, at most max_bytes PER stream.
    terminate/kill/drain/reap/close(): owned invocation/pidfd only, finite waits.

    Native authority, privilege dropping and helper protocol are unreviewed;
    subclasses do not gain execution permission merely by implementing methods.
    """
    def clock(self): raise NotImplementedError
    def observe(self): raise NotImplementedError
    def open_executable(self,path): raise NotImplementedError
    def executable_after(self,executable): raise NotImplementedError
    def close_executable(self,executable): raise NotImplementedError
    def spawn(self,request,executable,namespace,policy,invocation): raise NotImplementedError
    def poll(self,invocation,max_bytes,deadline): raise NotImplementedError
    def terminate(self,invocation): raise NotImplementedError
    def running(self,invocation): raise NotImplementedError
    def kill(self,invocation): raise NotImplementedError
    def drain(self,invocation,max_bytes,deadline): raise NotImplementedError
    def reap(self,invocation,deadline): raise NotImplementedError
    def close(self,invocation): raise NotImplementedError


class DormantOSReadOnlyBackend2:
    __slots__=('_policy','_driver','_enabled','_session','_lock','_state','_cancel','_terminal',
               '_last','_total','_before','_mode')

    def __init__(self,policy,pinned_policy_digest,pinned_binary_manifest_digest,driver,
                 session_uuid,started,*,enabled=False):
        c._typed(policy,o.OSReadPolicy2);c._typed(started,capture.CaptureTime2)
        o.require(policy.digest==pinned_policy_digest and
                  policy.template.binaries.digest==pinned_binary_manifest_digest,'pin_mismatch')
        o.require(isinstance(driver,OSReadDriver2) and type(enabled) is bool,'driver_invalid')
        self._policy=policy;self._driver=driver;self._enabled=enabled
        self._session=capture.CaptureSession2(session_uuid,policy.template.digest,policy.template.reader,
                                             started,started.monotonic_us+policy.timing.capture_us)
        self._lock=Lock();self._state=Lock();self._cancel=Event();self._terminal=None
        self._last=started;self._total=0;self._before=None;self._mode=None

    def capture_os(self):
        """Explicit native entry point. Always stops BEFORE any driver I/O.

        An offline OSReadPolicy2/mock approval is NOT a native activation grant.
        A future authority/namespace-helper review must introduce a new boundary,
        not repurpose enabled=True or a mock result as physical permission.
        """
        o.require(self._enabled,'disabled')
        raise c.ContractViolation2(o.PREFIX+'native_activation_unreviewed')

    def exercise_fake_driver(self):
        # Lazy import avoids any OS-driver module on the old collector path.
        from .native_v2_os_fake import FakeOSReadDriver2
        o.require(type(self._driver) is FakeOSReadDriver2,'fake_driver_required')
        o.require(self._lock.acquire(blocking=False),'concurrent_attempt')
        try:
            if self._terminal is not None:return self._terminal
            self._mode='fake_os_driver'
            return self._attempt()
        finally:self._lock.release()

    def kill(self):
        # Signal only in-process cancellation here. The owning attempt performs
        # bounded child termination/drain/reap before any result publication.
        with self._state:self._cancel.set()
        return self._terminal

    def _clock(self,deadline=None):
        now=self._driver.clock();c._typed(now,capture.CaptureTime2)
        o.require(now.monotonic_us>=self._last.monotonic_us and now.wall_utc_us>=self._last.wall_utc_us,'clock_rollback')
        self._last=now
        if deadline is not None:
            o.require(now.monotonic_us<=deadline and now.wall_utc_us-self._session.started.wall_utc_us<=
                      self._policy.timing.capture_us,'timeout')
        return now

    def _identity(self):
        observed=self._driver.observe();c._typed(observed,o.ReaderObservation2)
        policy=self._policy;reader=policy.template.reader
        o.require(observed.principal==policy.helper_principal,'principal_mismatch')
        o.require(observed.inherited_fds==policy.allowed_inherited_fds,'inherited_fd')
        o.require(observed.namespace_fds==policy.namespace_fds and
                  observed.namespace_inodes==tuple(n.reference.key.netns_inode for n in policy.namespace_fds),
                  'namespace_mismatch')
        o.require(all(observed.fd_open),'namespace_fd_lost')
        o.require(observed.host_boot_uuid==reader.namespaces[0].key.host_boot_uuid and
                  observed.reader_session_uuid==reader.reader_session_uuid and
                  observed.writer_epoch_uuid==reader.writer_epoch_uuid,'identity_changed')
        if self._before is not None:
            o.require((observed.reader_pid,observed.reader_start_ticks)==
                      (self._before.reader_pid,self._before.reader_start_ticks),'pid_reuse')
            o.require(observed==self._before,'identity_changed')
        else:self._before=observed
        return observed

    def _executable(self,observed,request):
        c._typed(observed,o.ExecutableObservation2)
        expected=self._policy.template.binaries.binary(capture.operation2(request.source).binary)
        o.require(observed.path==expected.path and observed.sha256==expected.binary_sha256 and
                  observed.source_manifest_digest==expected.source_manifest_digest,'executable_mismatch')
        # Conservative fixture policy. Symlinked /usr layouts require a NEW
        # reviewed resolver; no realpath fallback or pathname exec is admitted.
        o.require(observed.no_symlink_components and observed.protected_ancestors and observed.no_file_capabilities and
                  observed.uid==0 and observed.links==1 and observed.mode & 0o170000==0o100000 and
                  observed.mode & 0o6022==0 and observed.mode & 0o111!=0,'executable_unprotected')
        forbidden=set(self._policy.allowed_inherited_fds)
        o.require(observed.fd not in forbidden,'inherited_fd')

    def _cleanup(self,invocation,normal):
        """Finite cancellation; unresolved reap/close quarantines the attempt."""
        timing=self._policy.timing;safe=True
        try:
            start=self._clock().monotonic_us
            if not normal:
                self._driver.terminate(invocation)
                # Grace/drain have hard byte AND iteration bounds, even if a
                # faulty fake clock freezes. No discarded bytes become evidence.
                drained=0
                for _ in range(16):
                    now=self._clock().monotonic_us
                    if now>=start+timing.terminate_us or not self._driver.running(invocation):break
                    data=self._driver.drain(invocation,capture.CHUNK_BYTES,start+timing.drain_us)
                    o.require(type(data) is bytes and len(data)<=capture.CHUNK_BYTES,'driver_protocol_invalid')
                    drained+=len(data)
                    if drained>=65536:break
                if self._driver.running(invocation):self._driver.kill(invocation)
            reaped=self._driver.reap(invocation,start+timing.terminate_us+timing.drain_us+timing.reap_us)
            o.require(reaped is True,'reap_unproven')
            end=self._clock().monotonic_us
            o.require(end<=start+timing.terminate_us+timing.drain_us+timing.reap_us,'reap_unproven')
        except Exception:
            safe=False
            # Best effort signal/reap must also be attempted after clock/drain/
            # terminate failure. The outcome stays UNKNOWN even if it succeeds.
            try:self._driver.kill(invocation)
            except Exception:pass
            try:self._driver.reap(invocation,self._last.monotonic_us+timing.reap_us)
            except Exception:pass
        finally:
            try:
                if self._driver.close(invocation) is not True:safe=False
            except Exception:safe=False
        return safe

    def _command(self,request,index):
        op=capture.operation2(request.source);executable=None;invocation=None;normal=False
        stdout=bytearray();stderr=bytearray();artifact=None;failure=None;cleanup='no_child'
        try:
            o.require(not self._cancel.is_set(),'killed')
            before=self._identity();started=self._clock(self._session.deadline_monotonic_us)
            deadline=min(self._session.deadline_monotonic_us,started.monotonic_us+op.duration_us)
            executable=self._driver.open_executable(op.binary);self._executable(executable,request)
            self._clock(deadline);self._identity()
            namespace=next(n for n in self._policy.namespace_fds if n.reference==request.namespace)
            # Invocation key exists BEFORE spawn; a lost response cannot erase
            # the supervisor's obligation to cancel/reap that owned invocation.
            invocation=(self._session.session_uuid,index,request.capture_uuid)
            child=self._driver.spawn(request,executable,namespace,self._policy,invocation)
            c._typed(child,o.ChildHandle2)
            o.require(child.invocation_uuid==request.capture_uuid and child.namespace_pin_digest==namespace.digest and
                      child.executable_digest==executable.digest,'source_substitution')
            eof=set();exit_status=None;handshake=False;helper_record=None
            for _ in range(4096):
                o.require(not self._cancel.is_set(),'killed')
                self._clock(deadline);self._identity()
                poll=self._driver.poll(invocation,capture.CHUNK_BYTES,deadline);c._typed(poll,ProcessPoll2)
                self._clock(deadline)
                o.require(poll.reader_alive,'reader_died');o.require(not poll.interrupted,'interrupted')
                for stream,data in poll.chunks:
                    o.require(stream not in eof and len(data)<=capture.CHUNK_BYTES,'driver_protocol_invalid')
                    buffer=stdout if stream=='stdout' else stderr
                    cap=op.stdout_cap if stream=='stdout' else op.stderr_cap
                    o.require(len(buffer)+len(data)<=cap,stream+'_limit')
                    o.require(self._total+len(data)<=capture.MAX_AGGREGATE,'aggregate_limit')
                    self._total+=len(data);buffer.extend(data)
                if poll.stdout_eof:eof.add('stdout')
                if poll.stderr_eof:eof.add('stderr')
                if poll.exit_status is not None:
                    o.require(exit_status is None or poll.exit_status==exit_status,'driver_protocol_invalid')
                    exit_status=poll.exit_status;o.require(exit_status==0,'nonzero_exit')
                if poll.helper_completed:
                    c._typed(poll.helper_record,o.HelperAttestation2)
                    record=poll.helper_record
                    o.require(record.session_uuid==self._session.session_uuid and record.child==child and
                              record.namespace==namespace and record.executable_fd==executable.fd,'source_substitution')
                    o.require(record.command_principal==self._policy.command_principal,'principal_mismatch')
                    o.require(record.inherited_fds_after_exec==(0,1,2) and record.stdin_kind=='dev_null',
                              'inherited_fd')
                    o.require(record.environment==o.ENVIRONMENT,'driver_protocol_invalid')
                    helper_record=record;handshake=True
                if poll.control_eof:o.require(handshake,'handshake_missing')
                if eof=={'stdout','stderr'} and exit_status==0 and handshake:
                    normal=True;break
            o.require(normal,'incomplete_output')
            self._clock(deadline);after=self._identity()
            after_executable=self._driver.executable_after(executable);c._typed(after_executable,o.ExecutableObservation2)
            o.require(after_executable==executable,'executable_changed')
            artifact=o.OSCommandArtifact2(self._session,request,executable,child,started,self._last,
                                           bytes(stdout),bytes(stderr),before,after,helper_record)
        except c.ContractViolation2 as error:
            code=str(error).removeprefix(o.PREFIX)
            failure=code if code in o.REASONS else 'evidence_invalid'
        except InterruptedError:failure='interrupted'
        except TimeoutError:failure='timeout'
        except Exception:failure='evidence_invalid'
        finally:
            if invocation is not None:
                cleanup='reaped_and_closed' if self._cleanup(invocation,normal) else 'quarantine_cleanup_unproven'
                if cleanup!='reaped_and_closed':failure='cleanup_unproven'
            if executable is not None:
                try:
                    if self._driver.close_executable(executable) is not True:failure='cleanup_unproven';cleanup='quarantine_cleanup_unproven'
                except Exception:failure='cleanup_unproven';cleanup='quarantine_cleanup_unproven'
            stdout.clear();stderr.clear()
        return (artifact if failure is None else None),failure,cleanup

    def _attempt(self):
        artifacts=[];reason='disabled';cleanup='no_child'
        try:
            if self._enabled:
                for index,request in enumerate(self._policy.template.requests):
                    artifact,failure,cleanup=self._command(request,index)
                    if failure is not None:reason=failure;break
                    artifacts.append(artifact)
                else:reason='fake_driver_capture_preserved_os_unproven'
        except Exception:reason='evidence_invalid'
        if reason=='fake_driver_capture_preserved_os_unproven':
            try:self._clock(self._session.deadline_monotonic_us)
            except c.ContractViolation2 as error:
                code=str(error).removeprefix(o.PREFIX)
                reason=code if code in o.REASONS else 'evidence_invalid'
            except Exception:reason='evidence_invalid'
        with self._state:
            if self._cancel.is_set() and reason!='cleanup_unproven':reason='killed'
            successful=reason=='fake_driver_capture_preserved_os_unproven'
            self._terminal=o.OSReadResult2(self._session,self._policy.digest,tuple(artifacts) if successful else (),reason,cleanup)
        return self._terminal

    def admit_fake_result(self,result):
        c._typed(result,o.OSReadResult2)
        o.require(result is self._terminal and not self._cancel.is_set() and
                  result.reason=='fake_driver_capture_preserved_os_unproven','result_unissued')
        o.require(tuple(a.request for a in result.artifacts)==self._policy.template.requests,'source_substitution')
        return result
