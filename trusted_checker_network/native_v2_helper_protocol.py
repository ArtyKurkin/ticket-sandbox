"""H1 fixed binary protocol and independently pinned offline invocation records.

Binding/digests are NOT MACs or native peer attestation. The future control FD
must be independently authenticated/owned; helper and supervisor remain TCB.
"""
from dataclasses import dataclass
import hashlib
import struct
from uuid import UUID

from . import native_v2_contracts as c
from . import native_v2_capture_contracts as cap
from . import native_v2_os_contracts as os_contract

VERSION=1
MAGIC=b'TCH1'
CHUNK=4096
HEADER=struct.Struct('!4sBBHI')
BINDING=struct.Struct('!16s16s32s32s32s32s32s16s16sQQ32s')
MAX_BODY=BINDING.size+CHUNK
MAX_FRAME=HEADER.size+MAX_BODY
MAX_MESSAGES=4096
KINDS=('invoke','ready','entered','credentials','exec','stdout','stderr','stdout_eof',
       'stderr_eof','exit','reaped','complete','error','cancel')
SLOTS=('namespace','executable','stdin_null','stdout_pipe','stderr_pipe','control','parent_watch')
SLOT_KINDS=('netns','regular','char','pipe_write','pipe_write','unix_control','pidfd')
REASONS=('protocol_invalid','binding_mismatch','replay','sequence_invalid','fd_transfer_invalid',
         'identity_mismatch','pid_reuse','credential_drift','executable_mismatch','privilege_drop_failed',
         'timeout','clock_rollback','killed','parent_died','helper_crashed','spawn_response_lost',
         'incomplete_output','stdout_limit','stderr_limit','aggregate_limit','cleanup_unproven',
         'native_identity_unreviewed','disabled','evidence_invalid')


def require(condition,reason):c._require(condition,'v2_helper_'+reason)
def sha(raw):return hashlib.sha256(raw).hexdigest()


@dataclass(frozen=True,slots=True)
class DescriptorIdentityH1(c._Offline2):
    kind: str
    device: int
    inode: int
    generation: int
    object_digest: str

    def __post_init__(self):
        c._Offline2.__post_init__(self);c._enum(self.kind,SLOT_KINDS)
        c._integer(self.device,0);c._integer(self.inode);c._integer(self.generation);c._hex(self.object_digest)


@dataclass(frozen=True,slots=True)
class DescriptorSpecH1(c._Offline2):
    slot: str
    identity: DescriptorIdentityH1

    def __post_init__(self):
        c._Offline2.__post_init__(self);c._enum(self.slot,SLOTS);c._typed(self.identity,DescriptorIdentityH1)
        require(self.identity.kind==SLOT_KINDS[SLOTS.index(self.slot)],'fd_transfer_invalid')


@dataclass(frozen=True,slots=True)
class ReceivedDescriptorH1:
    slot: str
    local_fd: int

    def __post_init__(self):c._enum(self.slot,SLOTS);c._integer(self.local_fd,3,2**20-1)


def executable_object_digest_h1(executable):
    c._typed(executable,os_contract.ExecutableObservation2)
    # Descriptor numbers differ across processes; object identity does not.
    return c._hash('helper_executable_object',(executable.device,executable.inode,executable.size,
        executable.ctime_ns,executable.mode,executable.uid,executable.gid,executable.links,
        executable.sha256,executable.source_manifest_digest))


def validate_executable_h1(executable,principal):
    """Conservative fixture admission, not ACL/mount/LSM or native exec proof."""
    c._typed(executable,os_contract.ExecutableObservation2)
    c._typed(principal,os_contract.OSPrincipal2)
    require(executable.no_symlink_components and executable.protected_ancestors and
            executable.no_file_capabilities and executable.uid==0 and executable.links==1 and
            executable.mode & 0o170000==0o100000 and executable.mode & 0o6022==0 and
            executable.mode & 0o111!=0,'executable_mismatch')
    bit=0o100 if principal.uid==executable.uid else (
        0o010 if executable.gid in (principal.gid,*principal.supplementary_groups) else 0o001)
    require(principal.uid==0 or executable.mode & bit!=0,'executable_mismatch')


@dataclass(frozen=True,slots=True)
class HelperInvocationH1(c._Offline2):
    policy: os_contract.OSReadPolicy2
    session: cap.CaptureSession2
    request: cap.CaptureRequest2
    invocation_uuid: str
    nonce: str
    namespace: os_contract.NamespaceFdPin2
    executable: os_contract.ExecutableObservation2
    descriptors: tuple[DescriptorSpecH1,...]
    helper_pid: int
    helper_start_ticks: int
    parent_pid: int
    parent_start_ticks: int
    deadline_monotonic_us: int
    initial_namespace_inode: int

    def __post_init__(self):
        c._Offline2.__post_init__(self)
        for value,cls in ((self.policy,os_contract.OSReadPolicy2),(self.session,cap.CaptureSession2),
            (self.request,cap.CaptureRequest2),(self.namespace,os_contract.NamespaceFdPin2),
            (self.executable,os_contract.ExecutableObservation2)):c._typed(value,cls)
        c._uuid(self.invocation_uuid);c._hex(self.nonce);require(self.nonce!='0'*64,'binding_mismatch')
        for value in (self.helper_pid,self.helper_start_ticks,self.parent_pid,self.parent_start_ticks,
                      self.deadline_monotonic_us,self.initial_namespace_inode):c._integer(value)
        require(self.helper_pid!=self.parent_pid,'identity_mismatch')
        require(self.request in self.policy.template.requests and self.namespace in self.policy.namespace_fds and
                self.namespace.reference==self.request.namespace and self.session.plan_digest==self.policy.template.digest and
                self.session.reader==self.policy.template.reader,'binding_mismatch')
        require(self.session.started.monotonic_us<self.deadline_monotonic_us<=min(self.session.deadline_monotonic_us,
                self.session.started.monotonic_us+cap.operation2(self.request.source).duration_us),'timeout')
        expected=self.policy.template.binaries.binary(cap.operation2(self.request.source).binary)
        require(self.executable.path==expected.path and self.executable.sha256==expected.binary_sha256 and
                self.executable.source_manifest_digest==expected.source_manifest_digest,'executable_mismatch')
        validate_executable_h1(self.executable,self.policy.command_principal)
        c._rows(self.descriptors,DescriptorSpecH1,7,7)
        require(tuple(d.slot for d in self.descriptors)==SLOTS,'fd_transfer_invalid')
        require(len({(d.identity.kind,d.identity.device,d.identity.inode,d.identity.generation)
                     for d in self.descriptors})==7,'fd_transfer_invalid')
        ns,exe=self.descriptors[:2]
        require((ns.identity.device,ns.identity.inode,ns.identity.generation,ns.identity.object_digest)==
                (self.namespace.device,self.namespace.reference.key.netns_inode,self.namespace.fd_generation,
                 self.namespace.reference.digest),'fd_transfer_invalid')
        require((exe.identity.device,exe.identity.inode,exe.identity.object_digest)==
                (self.executable.device,self.executable.inode,executable_object_digest_h1(self.executable)),
                'fd_transfer_invalid')
        require(self.descriptors[-1].identity.object_digest==c._hash('helper_parent_pidfd',
                (self.namespace.reference.key.host_boot_uuid,self.parent_pid,self.parent_start_ticks)),
                'fd_transfer_invalid')

    @property
    def fd_catalog_digest(self):return c._hash('helper_fd_catalog',tuple(d.digest for d in self.descriptors))


def binding_h1(invocation):
    c._typed(invocation,HelperInvocationH1);i=invocation;install=i.policy.template.installation
    return BINDING.pack(UUID(i.session.session_uuid).bytes,UUID(i.invocation_uuid).bytes,bytes.fromhex(i.nonce),
        bytes.fromhex(i.request.digest),bytes.fromhex(i.namespace.reference.digest),
        bytes.fromhex(executable_object_digest_h1(i.executable)),bytes.fromhex(i.policy.command_principal.digest),
        UUID(install.writer_epoch_uuid).bytes,UUID(install.install_epoch_uuid).bytes,install.install_generation,
        i.deadline_monotonic_us,bytes.fromhex(i.digest))


@dataclass(frozen=True,slots=True)
class HelperMessageH1:
    kind: str
    sequence: int
    payload: bytes

    def __post_init__(self):
        c._enum(self.kind,KINDS);c._integer(self.sequence,0,MAX_MESSAGES-1)
        require(type(self.payload) is bytes,'protocol_invalid')
        exact={'invoke':32,'ready':32,'entered':32,'credentials':32,'exec':32,'stdout_eof':0,
               'stderr_eof':0,'exit':2,'reaped':32,'complete':112,'error':3,'cancel':0}
        if self.kind in ('stdout','stderr'):require(0<len(self.payload)<=CHUNK,'protocol_invalid')
        else:require(len(self.payload)==exact[self.kind],'protocol_invalid')
        if self.kind=='exit':require(int.from_bytes(self.payload,'big')<=255,'protocol_invalid')
        if self.kind=='error':
            require(int.from_bytes(self.payload[:2],'big')<len(REASONS) and self.payload[2] in (0,1),'protocol_invalid')


class HelperCodecH1:
    """Fixed widths, exact lengths; no dictionary/JSON fields or passthrough."""
    __slots__=('_binding',)
    def __init__(self,invocation):self._binding=binding_h1(invocation)

    def encode(self,message):
        c._typed(message,HelperMessageH1);body=self._binding+message.payload
        return HEADER.pack(MAGIC,VERSION,KINDS.index(message.kind)+1,message.sequence,len(body))+body

    def decode(self,raw):
        require(type(raw) is bytes and HEADER.size+BINDING.size<=len(raw)<=MAX_FRAME,'protocol_invalid')
        magic,version,kind,sequence,size=HEADER.unpack_from(raw)
        require(magic==MAGIC and version==VERSION and 1<=kind<=len(KINDS) and
                BINDING.size<=size<=MAX_BODY and len(raw)==HEADER.size+size,'protocol_invalid')
        require(raw[HEADER.size:HEADER.size+BINDING.size]==self._binding,'binding_mismatch')
        return HelperMessageH1(KINDS[kind-1],sequence,raw[HEADER.size+BINDING.size:])


class HelperStreamDecoderH1:
    """Incremental one-frame buffer; oversized declaration rejected at header."""
    __slots__=('_codec','_buffer','_failed','_frames','_finished')
    def __init__(self,codec):
        require(type(codec) is HelperCodecH1,'protocol_invalid')
        self._codec=codec;self._buffer=bytearray();self._failed=False;self._frames=0;self._finished=False

    def feed(self,chunk):
        result=[]
        try:
            require(not self._failed and not self._finished and type(chunk) is bytes and
                    len(chunk)<=MAX_FRAME,'protocol_invalid')
            for value in chunk:
                require(len(self._buffer)<MAX_FRAME,'protocol_invalid');self._buffer.append(value)
                if len(self._buffer)>=HEADER.size:
                    magic,version,kind,sequence,size=HEADER.unpack_from(self._buffer)
                    require(magic==MAGIC and version==VERSION and 1<=kind<=len(KINDS) and
                            BINDING.size<=size<=MAX_BODY,'protocol_invalid')
                    if len(self._buffer)==HEADER.size+size:
                        self._frames+=1;require(self._frames<=MAX_MESSAGES,'protocol_invalid')
                        result.append(self._codec.decode(bytes(self._buffer)));self._buffer.clear()
            return tuple(result)
        except BaseException:
            self._failed=True;self._buffer.clear();raise

    def finish(self):
        if self._failed or self._buffer:
            self._failed=True;self._buffer.clear()
            raise c.ContractViolation2('v2_helper_protocol_invalid')
        self._finished=True
