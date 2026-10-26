"""Dormant Linux FD primitives and conservative descriptor resolver.

Native activation has NO accepted grant in this revision. Every concrete Linux
primitive checks the closed guard before a syscall. No import/constructor I/O.
The namespace/credential/descriptor-exec supervisor is an explicit blocker,
never a pathname Popen/preexec_fn/setns fallback in the application process.
"""
from dataclasses import dataclass
import errno
import hashlib
import os
import selectors
import signal
import time

from . import native_v2_contracts as c
from . import native_v2_capture_contracts as capture
from . import native_v2_os_contracts as o
from .native_v2_os_reader import OSReadDriver2,ProcessPoll2


def _native_guard2():
    # Intentionally no accepted token, environment switch, callback or boolean.
    raise c.ContractViolation2(o.PREFIX+'native_activation_unreviewed')


@dataclass(frozen=True,slots=True)
class FileIdentity2:
    device: int
    inode: int
    mode: int
    uid: int
    gid: int
    links: int
    size: int
    ctime_ns: int

    def __post_init__(self):
        for value in (self.device,self.mode,self.uid,self.gid,self.size):c._integer(value,0)
        for value in (self.inode,self.links,self.ctime_ns):c._integer(value)


def _protected(identity,directory):
    c._typed(identity,FileIdentity2)
    wanted=0o040000 if directory else 0o100000
    o.require(identity.mode & 0o170000==wanted and identity.uid==0 and
              identity.mode & 0o6022==0,'executable_unprotected')
    if not directory:o.require(identity.links==1 and identity.mode & 0o111!=0,'executable_unprotected')


def resolve_executable2(kernel,expected,deadline_us):
    """Bounded component walk + hash of the HELD FD, against an independent pin.

    Kernel port operations MUST implement openat(O_NOFOLLOW|O_CLOEXEC), no path
    re-open for hash/exec. This protects pathname substitution in the model; it
    does not prove exclusion of privileged in-place writes or loader dependencies.
    The returned observation therefore cannot authorize native execution.
    """
    c._typed(expected,capture.BinaryReference2);c._integer(deadline_us)
    parts=expected.path.split('/')[1:];opened=[];result_fd=None
    try:
        parent=kernel.open_root();opened.append(parent);_protected(kernel.identity(parent),True)
        for index,component in enumerate(parts):
            o.require(kernel.monotonic_us()<=deadline_us,'timeout')
            directory=index<len(parts)-1
            child=kernel.open_component(parent,component,directory);opened.append(child)
            before=kernel.identity(child);_protected(before,directory)
            if directory:parent=child;continue
            o.require(before.size<=67108864 and before.size>0 and not kernel.file_capabilities(child),
                      'executable_unprotected')
            digest=hashlib.sha256();total=0
            while True:
                o.require(kernel.monotonic_us()<=deadline_us,'timeout')
                chunk=kernel.read(child,65536)
                o.require(type(chunk) is bytes and len(chunk)<=65536,'driver_protocol_invalid')
                if not chunk:break
                total+=len(chunk);o.require(total<=before.size,'executable_changed');digest.update(chunk)
            after=kernel.identity(child)
            o.require(before==after and total==before.size,'executable_changed')
            o.require(digest.hexdigest()==expected.binary_sha256,'executable_mismatch')
            kernel.rewind(child)
            observed=o.ExecutableObservation2(expected.path,child,before.device,before.inode,before.size,
                before.ctime_ns,before.mode,before.uid,before.gid,before.links,digest.hexdigest(),
                expected.source_manifest_digest,True,True,True)
            result_fd=child
            return observed
    finally:
        # Parent descriptors always close. Failure closes the final FD too.
        close_failed=False
        for fd in reversed(opened):
            if fd!=result_fd:
                try:kernel.close(fd)
                except Exception:close_failed=True
        if close_failed:
            if result_fd is not None:
                try:kernel.close(result_fd)
                except Exception:pass
            raise c.ContractViolation2(o.PREFIX+'cleanup_unproven')


class LinuxDescriptorKernel2:
    """Concrete syscall mapping, guarded BEFORE every possible native read."""
    def open_root(self):
        _native_guard2()
        return os.open('/',os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC)

    def open_component(self,parent,component,directory):
        _native_guard2()
        o.require(type(component) is str and component not in ('','.','..') and '/' not in component,'path_invalid')
        flags=os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC
        if directory:flags|=os.O_DIRECTORY
        return os.open(component,flags,dir_fd=parent)

    def identity(self,fd):
        _native_guard2();s=os.fstat(fd)
        return FileIdentity2(s.st_dev,s.st_ino,s.st_mode,s.st_uid,s.st_gid,s.st_nlink,s.st_size,s.st_ctime_ns)

    def file_capabilities(self,fd):
        _native_guard2()
        try:return bool(os.getxattr(fd,'security.capability'))
        except OSError as error:
            if error.errno==errno.ENODATA:return False
            raise

    def read(self,fd,maximum):
        _native_guard2();o.require(type(maximum) is int and 0<maximum<=65536,'read_bound_invalid')
        return os.read(fd,maximum)

    def rewind(self,fd):_native_guard2();os.lseek(fd,0,os.SEEK_SET)
    def close(self,fd):_native_guard2();os.close(fd)
    def monotonic_us(self):_native_guard2();return time.monotonic_ns()//1000


class LinuxReadOnlyDriver2(OSReadDriver2):
    """Native implementation scaffold, deliberately NOT execution-ready.

    No helper is launched. Resolving FDs alone cannot attest namespace/capability
    setup or immutable dynamic loader/libnftables/config dependencies. Those
    requirements cannot be replaced by subprocess(executable=pathname), a hash
    followed by pathname exec, or a mock namespace/approval description.
    """
    def __init__(self):
        self._kernel=LinuxDescriptorKernel2()
        self._children={}

    def clock(self):
        _native_guard2()
        return capture.CaptureTime2(time.time_ns()//1000,time.monotonic_ns()//1000)

    def observe(self):
        _native_guard2()
        raise c.ContractViolation2(o.PREFIX+'native_identity_reader_unreviewed')

    def open_executable(self,path):
        _native_guard2()
        # Native activation must bind a new authority-derived, independent binary
        # manifest and absolute deadline BEFORE invoking resolve_executable2.
        raise c.ContractViolation2(o.PREFIX+'native_manifest_binding_unreviewed')

    def spawn(self,request,executable,namespace,policy,invocation):
        _native_guard2()
        raise c.ContractViolation2(o.PREFIX+'namespace_helper_unreviewed')

    def _owned(self,invocation):
        child=self._children.get(invocation)
        o.require(child is not None,'driver_protocol_invalid')
        return child

    def executable_after(self,executable):
        _native_guard2()
        identity=self._kernel.identity(executable.fd)
        o.require((identity.device,identity.inode,identity.size,identity.ctime_ns,identity.mode,identity.uid,identity.gid,identity.links)==
                  (executable.device,executable.inode,executable.size,executable.ctime_ns,executable.mode,executable.uid,executable.gid,executable.links),
                  'executable_changed')
        return executable

    def close_executable(self,executable):
        _native_guard2();self._kernel.close(executable.fd);return True

    def _wait_status(self,child):
        _native_guard2()
        if child['status'] is None:
            pid,status=os.waitpid(child['pid'],os.WNOHANG)
            if pid:
                child['reaped']=True
                code=os.waitstatus_to_exitcode(status)
                child['status']=code if 0<=code<=255 else 255
        return child['status']

    def poll(self,invocation,max_bytes,deadline):
        _native_guard2();o.require(type(max_bytes) is int and 0<max_bytes<=capture.CHUNK_BYTES,'read_bound_invalid')
        child=self._owned(invocation);chunks=[]
        # A future reviewed helper must supply nonblocking CLOEXEC pipes, a
        # pidfd, and the exact nonce-bound acknowledgement; no public registration
        # API accepts caller PIDs/FDs. Native spawn/registration is still blocked.
        with selectors.DefaultSelector() as selector:
            for stream,fd in child['pipes'].items():selector.register(fd,selectors.EVENT_READ,stream)
            remaining=max(0,(deadline-time.monotonic_ns()//1000)/1000000)
            for key,_ in selector.select(min(remaining,0.01)):
                stream=key.data
                limit=256 if stream=='control' else max_bytes
                try:data=os.read(key.fd,limit)
                except BlockingIOError:continue
                if not data:
                    child['eof'].add(stream);os.close(key.fd);del child['pipes'][stream]
                elif stream=='control':
                    o.require(len(child['control'])+len(data)<=256,'driver_protocol_invalid')
                    child['control']+=data
                else:chunks.append((stream,data))
        status=self._wait_status(child)
        handshake=child['control']==child['expected_ack'] and 'control' in child['eof']
        return ProcessPoll2(tuple(chunks),'stdout' in child['eof'],'stderr' in child['eof'],
                            status,handshake,'control' in child['eof'])

    def terminate(self,invocation):
        _native_guard2();child=self._owned(invocation)
        if self._wait_status(child) is None:signal.pidfd_send_signal(child['pidfd'],signal.SIGTERM,None,0)

    def running(self,invocation):
        _native_guard2();return self._wait_status(self._owned(invocation)) is None

    def kill(self,invocation):
        _native_guard2();child=self._owned(invocation)
        if self._wait_status(child) is None:signal.pidfd_send_signal(child['pidfd'],signal.SIGKILL,None,0)

    def drain(self,invocation,max_bytes,deadline):
        _native_guard2()
        polled=self.poll(invocation,max(1,max_bytes//2),deadline)
        # Both streams together stay within the caller's drain byte budget.
        return b''.join(data for _,data in polled.chunks)

    def reap(self,invocation,deadline):
        _native_guard2();child=self._owned(invocation)
        for _ in range(4096):
            if self._wait_status(child) is not None:return child['reaped']
            if time.monotonic_ns()//1000>=deadline:break
            time.sleep(0.001)
        return False

    def close(self,invocation):
        _native_guard2();child=self._owned(invocation);safe=child['reaped']
        for fd in (*child['pipes'].values(),child['pidfd']):
            try:os.close(fd)
            except OSError:safe=False
        del self._children[invocation]
        return safe
