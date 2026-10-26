"""Explicit fake process/FD/clock driver. No actual OS or old mock transport.

Configuration is trusted test setup, never independent host evidence. Clock is
a separate driver method; stdout and completion messages do not set the clock.
"""
from dataclasses import replace

from . import native_v2_contracts as c
from . import native_v2_capture_contracts as capture
from . import native_v2_os_contracts as o
from .native_v2_os_reader import OSReadDriver2,ProcessPoll2


class FakeOSReadDriver2(OSReadDriver2):
    def __init__(self,policy,started,scripts):
        c._typed(policy,o.OSReadPolicy2);c._typed(started,capture.CaptureTime2)
        o.require(type(scripts) is tuple and len(scripts)<=256,'driver_protocol_invalid')
        for key,polls in scripts:
            c._uuid(key);c._rows(polls,ProcessPoll2,0,4096)
        o.require(len({k for k,_ in scripts})==len(scripts),'driver_protocol_invalid')
        self.policy=policy;self.scripts=scripts;self.calls=[];self.now=started;self.step_us=100
        self.clock_sequence=();self.observations=();self.executable_overrides=();self.after_executable=None
        self.spawn_error_after_registration=False;self.spawn_override=None;self.term_effective=True
        self.reap_ok=True;self.close_ok=True;self.executable_close_ok=True;self.drain_bytes=b''
        self.poll_exception=None;self.on_poll=None;self.fail_terminate=False;self.fail_drain=False
        self.helper_override=None;self.helper_transform=None;self._helper=None
        self._active=None;self._polls=();self._index=0;self._running=False;self._reaped=False
        self.default_observation=o.ReaderObservation2(policy.helper_principal,
            policy.template.reader.namespaces[0].key.host_boot_uuid,policy.template.reader.reader_session_uuid,
            5000,10000,policy.template.reader.writer_epoch_uuid,policy.allowed_inherited_fds,
            policy.namespace_fds,tuple(n.reference.key.netns_inode for n in policy.namespace_fds),
            (True,)*len(policy.namespace_fds))

    def clock(self):
        self.calls.append(('clock',))
        if self.clock_sequence:
            now,self.clock_sequence=self.clock_sequence[0],self.clock_sequence[1:];self.now=now;return now
        self.now=capture.CaptureTime2(self.now.wall_utc_us+self.step_us,self.now.monotonic_us+self.step_us)
        return self.now

    def observe(self):
        self.calls.append(('observe',))
        if self.observations:
            value,self.observations=self.observations[0],self.observations[1:];return value
        return self.default_observation

    def open_executable(self,path):
        self.calls.append(('open_executable',path))
        for observed in self.executable_overrides:
            # Tests can deliberately return a wrong path for substitution faults.
            return observed
        expected=self.policy.template.binaries.binary(path)
        return o.ExecutableObservation2(path,100,1,500,1000,1000,0o100755,0,0,1,
            expected.binary_sha256,expected.source_manifest_digest,True,True,True)

    def executable_after(self,executable):
        self.calls.append(('executable_after',executable.fd))
        return self.after_executable if self.after_executable is not None else executable

    def close_executable(self,executable):
        self.calls.append(('close_executable',executable.fd));return self.executable_close_ok

    def spawn(self,request,executable,namespace,policy,invocation):
        o.require(self._active is None and policy==self.policy,'driver_protocol_invalid')
        # The future supervisor must register before dispatch as well.
        self._active=invocation;self._running=True;self._reaped=False
        self._polls=dict(self.scripts).get(request.capture_uuid,());self._index=0
        self.calls.append(('spawn',request.argv,executable.fd,namespace.fd,policy.environment,
                           policy.command_principal.digest,invocation))
        if self.spawn_error_after_registration:raise RuntimeError('fake lost spawn response')
        child=o.ChildHandle2(6000+invocation[1],20000,request.capture_uuid,namespace.digest,executable.digest)
        self._helper=o.HelperAttestation2(invocation[0],child,namespace,executable.fd,policy.command_principal,
                                          (0,1,2),policy.environment,'dev_null')
        return self.spawn_override if self.spawn_override is not None else child

    def _owned(self,invocation):o.require(invocation==self._active,'driver_protocol_invalid')

    def poll(self,invocation,max_bytes,deadline):
        self._owned(invocation);self.calls.append(('poll',max_bytes,deadline))
        if self.on_poll is not None:self.on_poll()
        if self.poll_exception is not None:raise self.poll_exception
        if self._index==len(self._polls):return ProcessPoll2()
        poll=self._polls[self._index];self._index+=1
        if poll.helper_completed:
            record=self.helper_override if self.helper_override is not None else self._helper
            if self.helper_transform is not None:record=self.helper_transform(record)
            poll=replace(poll,helper_record=record)
        if poll.exit_status is not None:self._running=False
        return poll

    def terminate(self,invocation):
        self._owned(invocation);self.calls.append(('terminate',invocation))
        if self.fail_terminate:raise RuntimeError('fake terminate failure')
        if self.term_effective:self._running=False

    def running(self,invocation):self._owned(invocation);return self._running

    def kill(self,invocation):
        self._owned(invocation);self.calls.append(('kill',invocation));self._running=False

    def drain(self,invocation,max_bytes,deadline):
        self._owned(invocation);self.calls.append(('drain',max_bytes,deadline))
        if self.fail_drain:raise RuntimeError('fake drain failure')
        return self.drain_bytes

    def reap(self,invocation,deadline):
        self._owned(invocation);self.calls.append(('reap',invocation,deadline))
        self._reaped=self.reap_ok and not self._running
        return self._reaped

    def close(self,invocation):
        self._owned(invocation);self.calls.append(('close',invocation))
        safe=self.close_ok and self._reaped and not self._running
        self._active=None;return safe
