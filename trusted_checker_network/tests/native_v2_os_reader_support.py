"""Deterministic fake process/FD/kernel fixtures; no Linux commands or syscalls."""
from dataclasses import dataclass,replace
import hashlib

from trusted_checker_network import native_v2_capture_contracts as capture
from trusted_checker_network import native_v2_os_contracts as o
from trusted_checker_network import native_v2_os_reader as reader
from trusted_checker_network import native_v2_os_fake as fake
from trusted_checker_network.native_v2_os_linux import FileIdentity2
from .native_v2_collector_support import CollectorFixture2,stamp
from .native_v2_support import uid,hd


@dataclass
class OSFixture2:
    policy: o.OSReadPolicy2
    scripts: tuple

    @classmethod
    def create(cls,*,full=False):
        f=CollectorFixture2.create()
        template=f.plan if full else replace(f.plan,requests=f.plan.requests[:1])
        pins=tuple(o.NamespaceFdPin2(n,10+i,1,1,n.lookup_pid,n.process_start_ticks)
                   for i,n in enumerate(template.reader.namespaces))
        helper=o.OSPrincipal2(1001,1001,(),('CAP_SYS_ADMIN',),('CAP_SYS_ADMIN',),('CAP_SYS_ADMIN',))
        command=o.OSPrincipal2(1002,1002,(),('CAP_NET_ADMIN',),('CAP_NET_ADMIN',),('CAP_NET_ADMIN',))
        policy=o.OSReadPolicy2(template,helper,command,pins,(0,1,2,10,11,12),
                hd('exec-review-not-accepted'),hd('config-review'),hd('secrets-journal-review'),o.InventoryTimingProposal2())
        scripts=tuple((q.capture_uuid,(reader.ProcessPoll2((('stdout',b'[]'),)),
                reader.ProcessPoll2(stdout_eof=True,stderr_eof=True,exit_status=0,helper_completed=True,control_eof=True)))
                for q in template.requests)
        return cls(policy,scripts)

    def driver(self):return fake.FakeOSReadDriver2(self.policy,stamp(),self.scripts)

    def backend(self,driver=None,*,enabled=True):
        driver=self.driver() if driver is None else driver
        backend=reader.DormantOSReadOnlyBackend2(self.policy,self.policy.digest,self.policy.template.binaries.digest,
                                               driver,uid(9000),stamp(),enabled=enabled)
        return backend,driver

    def run(self,driver=None):
        backend,driver=self.backend(driver)
        return backend.exercise_fake_driver(),backend,driver


class FakeDescriptorKernel2:
    def __init__(self):
        self.raw=b'EXPLICIT SYNTHETIC EXECUTABLE CONTENT'
        self.closed=[];self.calls=[];self.now=0;self.parts=('/', 'usr','sbin','nft')
        self.identities={3+i:FileIdentity2(1,100+i,0o040755 if i<3 else 0o100755,0,0,1,
                                         1 if i<3 else len(self.raw),100) for i in range(4)}
        self.positions={};self.after_identity=None;self.file_caps=False;self.fail_component=None
        self.close_failure=None;self.return_oversized=False;self.read_count=0

    @property
    def expected(self):
        return capture.BinaryReference2('/usr/sbin/nft',hashlib.sha256(self.raw).hexdigest(),
                                         'synthetic',hd('source'),hd('protection'))

    def open_root(self):self.calls.append(('root',));return 3
    def open_component(self,parent,component,directory):
        self.calls.append(('openat_nofollow',parent,component,directory))
        if component==self.fail_component:raise OSError('synthetic nofollow refusal')
        return parent+1
    def identity(self,fd):
        if fd==6 and self.read_count and self.after_identity is not None:return self.after_identity
        return self.identities[fd]
    def monotonic_us(self):self.now+=1;return self.now
    def file_capabilities(self,fd):return self.file_caps
    def read(self,fd,maximum):
        self.read_count+=1;self.calls.append(('read',fd,maximum))
        if self.return_oversized:return b'x'*(maximum+1)
        pos=self.positions.get(fd,0);self.positions[fd]=pos+maximum
        return self.raw[pos:pos+maximum]
    def rewind(self,fd):self.positions[fd]=0
    def close(self,fd):
        self.closed.append(fd)
        if self.close_failure==fd:raise OSError('synthetic close error')
