"""Independently authored synthetic H1 invocations and fake child observations."""
from dataclasses import dataclass

from trusted_checker_network import native_v2_contracts as c
from trusted_checker_network import native_v2_capture_contracts as cap
from trusted_checker_network import native_v2_os_contracts as o
from trusted_checker_network import native_v2_helper_protocol as p
from trusted_checker_network import native_v2_helper_runtime as r
from trusted_checker_network import native_v2_helper_fake as fake
from trusted_checker_network import native_v2_helper_identity as identity
from .native_v2_os_reader_support import OSFixture2
from .native_v2_collector_support import stamp
from .native_v2_support import hd,uid


@dataclass
class HelperFixtureH1:
    invocation: p.HelperInvocationH1
    polls: tuple
    observations: fake.FakeObservationsH1 | None = None

    @classmethod
    def create(cls,role='host'):
        base=OSFixture2.create(full=True);policy=base.policy
        request=next(q for q in policy.template.requests if q.namespace.role==role and q.source=='nft')
        namespace=next(n for n in policy.namespace_fds if n.reference==request.namespace)
        binary=policy.template.binaries.binary('/usr/sbin/nft')
        executable=o.ExecutableObservation2('/usr/sbin/nft',100,1,900,1000,1000,0o100755,0,0,1,
            binary.binary_sha256,binary.source_manifest_digest,True,True,True)
        session=cap.CaptureSession2(uid(9000),policy.template.digest,policy.template.reader,stamp(),stamp().monotonic_us+2000000)
        specs=[]
        for index,(slot,kind) in enumerate(zip(p.SLOTS,p.SLOT_KINDS)):
            if slot=='namespace':facts=p.DescriptorIdentityH1(kind,namespace.device,namespace.reference.key.netns_inode,
                                                              namespace.fd_generation,namespace.reference.digest)
            elif slot=='executable':facts=p.DescriptorIdentityH1(kind,executable.device,executable.inode,1,
                                                                 p.executable_object_digest_h1(executable))
            elif slot=='parent_watch':facts=p.DescriptorIdentityH1(kind,1,1000+index,1,
                c._hash('helper_parent_pidfd',(namespace.reference.key.host_boot_uuid,5000,9000)))
            else:facts=p.DescriptorIdentityH1(kind,1,1000+index,1,hd('independent-fd-'+slot))
            specs.append(p.DescriptorSpecH1(slot,facts))
        invocation=p.HelperInvocationH1(policy,session,request,uid(9100),hd('explicit-synthetic-nonce'),namespace,
            executable,tuple(specs),6000,10000,5000,9000,stamp().monotonic_us+500000,100)
        polls=(r.ChildPollH1((('stdout',b'[]'),)),r.ChildPollH1(stdout_eof=True,stderr_eof=True,exit_code=0))
        # Actual fake observations are authored separately from the expected
        # invocation/spec catalog; the production fake has no expected->facts
        # fallback. These are synthetic trusted setup values, not OS acquisition.
        observed_executable=o.ExecutableObservation2('/usr/sbin/nft',31,1,900,1000,1000,0o100755,0,0,1,
            binary.binary_sha256,binary.source_manifest_digest,True,True,True)
        actual_facts=(
            p.DescriptorIdentityH1('netns',namespace.device,namespace.reference.key.netns_inode,
                                   namespace.fd_generation,namespace.reference.digest),
            p.DescriptorIdentityH1('regular',1,900,1,p.executable_object_digest_h1(observed_executable)),
            p.DescriptorIdentityH1('char',1,1002,1,hd('independent-fd-stdin_null')),
            p.DescriptorIdentityH1('pipe_write',1,1003,1,hd('independent-fd-stdout_pipe')),
            p.DescriptorIdentityH1('pipe_write',1,1004,1,hd('independent-fd-stderr_pipe')),
            p.DescriptorIdentityH1('unix_control',1,1005,1,hd('independent-fd-control')),
            p.DescriptorIdentityH1('pidfd',1,1006,1,c._hash('helper_parent_pidfd',
                (namespace.reference.key.host_boot_uuid,5000,9000))))
        observed_identity=identity.IdentitySnapshotH1(namespace.reference.key.host_boot_uuid,6000,10000,
            5000,9000,namespace.lookup_pid,namespace.lookup_start_ticks,100,'nsfs_net',policy.helper_principal,
            tuple(range(30,37)),c._hash('helper_session_nsid',(namespace.reference.key.reader_session_uuid,
                namespace.reference.nsid_mappings,namespace.reference.reciprocal_peer_reference_digests)),
            p.executable_object_digest_h1(observed_executable),policy.configuration_review_digest,
            policy.secret_journal_protection_digest)
        observations=fake.FakeObservationsH1(tuple(p.ReceivedDescriptorH1(s,30+n) for n,s in enumerate(p.SLOTS)),
            tuple((30+n,facts) for n,facts in enumerate(actual_facts)),observed_executable,observed_identity)
        return cls(invocation,polls,observations)

    def kernel(self):return fake.FakeHelperKernelH1(self.invocation,self.polls,observations=self.observations)

    def supervisor(self,kernel=None,registry=None,enabled=True):
        kernel=self.kernel() if kernel is None else kernel
        registry=r.OwnedInvocationRegistryH1(self.invocation.session.session_uuid) if registry is None else registry
        return r.HelperSupervisorH1(self.invocation,self.invocation.digest,kernel,registry,enabled=enabled),kernel

    def run(self,kernel=None):
        supervisor,kernel=self.supervisor(kernel)
        return supervisor.run_fake(),supervisor,kernel


def stat_bytes(pid,ticks,comm='synthetic'):
    fields=['S']+['0']*18+[str(ticks)]
    return (str(pid)+' ('+comm+') '+' '.join(fields)+'\n').encode()


def status_bytes(uid=1002,gid=1002,capmask='0000000000000001'):
    return (f'Uid:\t{uid} {uid} {uid} {uid}\nGid:\t{gid} {gid} {gid} {gid}\nGroups:\t\n'
            'CapInh:\t0000000000000000\n'+f'CapPrm:\t{capmask}\nCapEff:\t{capmask}\nCapBnd:\t{capmask}\n'
            'CapAmb:\t0000000000000000\nNoNewPrivs:\t1\n').encode()
