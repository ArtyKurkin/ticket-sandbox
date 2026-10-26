"""Standalone entry and isolated Linux identity/FD primitives: native CLOSED.

No import-time observer, helper launch, stdin command decoder or CLI command
arguments. Any native call stops before OS I/O pending separate security review.
"""
import os
import hashlib

from . import native_v2_contracts as c
from . import native_v2_os_contracts as o
from . import native_v2_helper_protocol as p
from . import native_v2_helper_identity as identity


def native_guard_h1():raise c.ContractViolation2('v2_helper_native_identity_unreviewed')


def source_path_h1(invocation,source):
    c._typed(invocation,p.HelperInvocationH1);c._enum(source,tuple(dict(identity.SOURCE_CAPS)))
    paths={'boot':'/proc/sys/kernel/random/boot_id','helper_stat':f'/proc/{invocation.helper_pid}/stat',
           'parent_stat':f'/proc/{invocation.parent_pid}/stat',
           'namespace_stat':f'/proc/{invocation.namespace.lookup_pid}/stat',
           'helper_status':f'/proc/{invocation.helper_pid}/status',
           'inherited_fds':f'/proc/{invocation.helper_pid}/fd'}
    p.require(source in paths,'native_identity_unreviewed')
    return paths[source]


class LinuxIdentityKernelH1:
    def read_source(self,invocation,source):
        native_guard_h1()
        path=source_path_h1(invocation,source);maximum=dict(identity.SOURCE_CAPS)[source]
        p.require(source!='inherited_fds','native_identity_unreviewed')
        fd=os.open(path,os.O_RDONLY|os.O_CLOEXEC|os.O_NOFOLLOW)
        try:
            chunks=[];count=0
            while count<=maximum:
                raw=os.read(fd,min(4096,maximum+1-count))
                if not raw:break
                count+=len(raw);p.require(count<=maximum,'native_identity_unreviewed');chunks.append(raw)
            return b''.join(chunks)
        finally:os.close(fd)

    def inherited_fds(self,invocation):
        native_guard_h1()
        found=[]
        with os.scandir(source_path_h1(invocation,'inherited_fds')) as rows:
            for row in rows:
                p.require(len(found)<256 and row.name.isascii() and row.name.isdecimal(),'native_identity_unreviewed')
                found.append(int(row.name))
        # Observer-owned temporary FD exclusion needs a reviewed acquisition
        # protocol. Raw list is not automatically an inherited-FD attestation.
        return tuple(sorted(found))

    def namespace_fd(self,fd):
        native_guard_h1()
        c._integer(fd,3,2**20-1);facts=os.fstat(fd)
        # nsfs filesystem type + NS_GET_NSTYPE ABI is deliberately not guessed.
        # fstat alone is insufficient to release a namespace identity record.
        raise c.ContractViolation2('v2_helper_native_identity_unreviewed')

    def executable_fd_hash(self,fd,maximum=67108864):
        native_guard_h1()
        c._integer(fd,3,2**20-1);p.require(type(maximum) is int and maximum==67108864,'native_identity_unreviewed')
        before=os.fstat(fd);p.require(0<before.st_size<=maximum,'executable_mismatch')
        digest=hashlib.sha256();count=0;os.lseek(fd,0,os.SEEK_SET)
        while count<=maximum:
            raw=os.read(fd,min(65536,maximum+1-count))
            if not raw:break
            count+=len(raw);p.require(count<=maximum,'executable_mismatch');digest.update(raw)
        after=os.fstat(fd)
        p.require((before.st_dev,before.st_ino,before.st_size,before.st_ctime_ns)==
                  (after.st_dev,after.st_ino,after.st_size,after.st_ctime_ns) and count==before.st_size,'executable_mismatch')
        os.lseek(fd,0,os.SEEK_SET);return digest.hexdigest()

    def protected_references(self,invocation):
        native_guard_h1()
        # Current digests are review pointers, not a filesystem/ACL manifest.
        raise c.ContractViolation2('v2_helper_native_identity_unreviewed')


class LinuxHelperKernelH1:
    def enter_namespace(self,namespace_fd):
        native_guard_h1();c._integer(namespace_fd,3,2**20-1)
        # Only the separately launched standalone helper could reach this call;
        # nsfs/net namespace proof is a prerequisite, not nstype=0 inference.
        os.setns(namespace_fd,0)

    def drop_credentials(self,principal):
        native_guard_h1();c._typed(principal,o.OSPrincipal2)
        # capset/prctl/securebits/userns ABI and ordering are unreviewed. Never
        # perform a partial setuid followed by pretending capability drop worked.
        raise c.ContractViolation2('v2_helper_native_identity_unreviewed')

    def exec_verified_fd(self,invocation,local_fd):
        native_guard_h1();c._typed(invocation,p.HelperInvocationH1);c._integer(local_fd,3,2**20-1)
        p.require(os.execve in os.supports_fd,'native_identity_unreviewed')
        # No pathname or /proc/self/fd string fallback. Reaching this code still
        # requires NEW native authority/dependency/write-exclusion review.
        os.execve(local_fd,invocation.request.argv,dict(o.ENVIRONMENT))


def standalone_helper_entry_h1(invocation,invoke_frame,transferred,kernel,channel):
    """Explicit callable entry for offline protocol exercise, never auto-launch."""
    from .native_v2_helper_runtime import StandaloneHelperH1
    return StandaloneHelperH1().run_fake(invocation,invoke_frame,transferred,kernel,channel)


def native_helper_entry_h1():native_guard_h1()


if __name__=='__main__':
    native_helper_entry_h1()
