"""Bounded identity decoding/validation; native facts never come from JSON.

Pure source parsers operate on explicitly synthetic test captures. Native adapter
returns native_identity_unreviewed until Linux source/syscall/permission review.
"""
from dataclasses import dataclass,field
import re

from . import native_v2_contracts as c
from . import native_v2_os_contracts as o
from . import native_v2_helper_protocol as p

SOURCE_CAPS=(('boot',64),('helper_stat',4096),('parent_stat',4096),('namespace_stat',4096),
             ('helper_status',16384),('inherited_fds',4096),('protected_references',4096))


def source_bytes_h1(source,raw):
    c._enum(source,tuple(dict(SOURCE_CAPS)))
    p.require(type(raw) is bytes and 0<len(raw)<=dict(SOURCE_CAPS)[source],'native_identity_unreviewed')
    try:return raw.decode('ascii',errors='strict')
    except UnicodeDecodeError:raise c.ContractViolation2('v2_helper_native_identity_unreviewed') from None


def decimal_h1(value):
    p.require(type(value) is str and re.fullmatch(r'0|[1-9][0-9]{0,18}',value) is not None,'native_identity_unreviewed')
    result=int(value);c._integer(result,0);return result


def parse_boot_h1(raw):
    text=source_bytes_h1('boot',raw)
    p.require(text.endswith('\n') and len(text)==37,'native_identity_unreviewed')
    value=text[:-1];c._uuid(value);return value


def parse_fd_inventory_h1(raw):
    text=source_bytes_h1('inherited_fds',raw);lines=text.splitlines()
    p.require(len(lines)<=256,'native_identity_unreviewed')
    values=tuple(decimal_h1(line) for line in lines)
    p.require(len(values)==len(set(values)),'native_identity_unreviewed')
    return tuple(sorted(values))


def parse_pid_stat_h1(raw,source):
    c._enum(source,('helper_stat','parent_stat','namespace_stat'))
    text=source_bytes_h1(source,raw).rstrip('\n')
    first,separator,rest=text.partition(' (');comm,closing,tail=rest.rpartition(') ')
    p.require(separator==' (' and closing==') ' and len(comm)<=256,'native_identity_unreviewed')
    fields=tail.split();p.require(len(fields)>=20 and len(fields)<=64,'native_identity_unreviewed')
    pid=decimal_h1(first);ticks=decimal_h1(fields[19]);p.require(pid>0 and ticks>0,'native_identity_unreviewed')
    return pid,ticks


def parse_status_h1(raw,capability_mapping):
    """Exact bounded projection schema, not an accepted complete /proc profile.

    Capability bit mapping is independently supplied fixture data, never guessed
    kernel constants or discovered from the inspected status document.
    """
    text=source_bytes_h1('helper_status',raw);values={}
    keys=('Uid','Gid','Groups','CapInh','CapPrm','CapEff','CapBnd','CapAmb','NoNewPrivs')
    for line in text.splitlines():
        key,separator,value=line.partition(':')
        p.require(separator==':' and key in keys and key not in values,'native_identity_unreviewed')
        values[key]=value.strip()
    p.require(set(values)==set(keys),'native_identity_unreviewed')
    p.require(type(capability_mapping) is tuple and len(capability_mapping)<=2,'native_identity_unreviewed')
    bits=[];names=[]
    for name,bit in capability_mapping:
        c._enum(name,o.CAPABILITIES);c._integer(bit,0,63);bits.append(bit);names.append(name)
    p.require(len(bits)==len(set(bits)) and len(names)==len(set(names)),'native_identity_unreviewed')
    def ids(key):
        items=values[key].split();p.require(len(items)==4,'native_identity_unreviewed')
        parsed=tuple(decimal_h1(x) for x in items)
        p.require(len(set(parsed))==1,'credential_drift');return parsed[0]
    def caps(key):
        value=values[key];p.require(re.fullmatch('[0-9a-f]{16}',value) is not None,'native_identity_unreviewed')
        mask=int(value,16);known=sum(1<<bit for _,bit in capability_mapping)
        p.require(mask & ~known==0,'native_identity_unreviewed')
        return tuple(sorted(name for name,bit in capability_mapping if mask & (1<<bit)))
    p.require(caps('CapInh')==(),'credential_drift')
    groups=tuple(decimal_h1(x) for x in values['Groups'].split())
    p.require(values['NoNewPrivs']=='1','credential_drift')
    return o.OSPrincipal2(ids('Uid'),ids('Gid'),groups,caps('CapEff'),caps('CapPrm'),caps('CapBnd'),caps('CapAmb'))


@dataclass(frozen=True,slots=True)
class IdentitySnapshotH1(c._Offline2):
    boot_uuid: str
    helper_pid: int
    helper_start_ticks: int
    parent_pid: int
    parent_start_ticks: int
    namespace_lookup_pid: int
    namespace_lookup_start_ticks: int
    namespace_inode: int
    namespace_fs: str
    principal: o.OSPrincipal2
    inherited_fds: tuple[int,...]
    nsid_references_digest: str
    executable_object_digest: str
    configuration_reference_digest: str
    journal_reference_digest: str

    def __post_init__(self):
        c._Offline2.__post_init__(self);c._uuid(self.boot_uuid)
        for value in (self.helper_pid,self.helper_start_ticks,self.parent_pid,self.parent_start_ticks,
                      self.namespace_lookup_pid,self.namespace_lookup_start_ticks,self.namespace_inode):c._integer(value)
        c._enum(self.namespace_fs,('nsfs_net','unreviewed'))
        c._typed(self.principal,o.OSPrincipal2);o.integer_tuple(self.inherited_fds)
        for value in (self.nsid_references_digest,self.executable_object_digest,
                      self.configuration_reference_digest,self.journal_reference_digest):c._hex(value)


def nsid_digest_h1(invocation):
    ref=invocation.namespace.reference
    return c._hash('helper_session_nsid',(ref.key.reader_session_uuid,ref.nsid_mappings,
                                        ref.reciprocal_peer_reference_digests))


def validate_identity_h1(snapshot,invocation,phase,expected_fds):
    c._typed(snapshot,IdentitySnapshotH1);c._typed(invocation,p.HelperInvocationH1)
    c._enum(phase,('before','entered','credentials','final'))
    i=invocation;ref=i.namespace.reference
    p.require((snapshot.helper_pid,snapshot.helper_start_ticks,snapshot.parent_pid,snapshot.parent_start_ticks,
               snapshot.namespace_lookup_pid,snapshot.namespace_lookup_start_ticks)==
              (i.helper_pid,i.helper_start_ticks,i.parent_pid,i.parent_start_ticks,
               i.namespace.lookup_pid,i.namespace.lookup_start_ticks),'pid_reuse')
    p.require(snapshot.boot_uuid==ref.key.host_boot_uuid and snapshot.namespace_fs=='nsfs_net' and
              snapshot.namespace_inode==(i.initial_namespace_inode if phase=='before' else ref.key.netns_inode) and
              snapshot.nsid_references_digest==nsid_digest_h1(i),'identity_mismatch')
    expected=i.policy.helper_principal if phase in ('before','entered') else i.policy.command_principal
    p.require(snapshot.principal==expected,'credential_drift')
    p.require(snapshot.inherited_fds==expected_fds,'fd_transfer_invalid')
    p.require(snapshot.executable_object_digest==p.executable_object_digest_h1(i.executable),'executable_mismatch')
    p.require(snapshot.configuration_reference_digest==i.policy.configuration_review_digest and
              snapshot.journal_reference_digest==i.policy.secret_journal_protection_digest,'identity_mismatch')
    return snapshot


@dataclass(frozen=True,slots=True)
class NativeIdentityStatusH1(c._Offline2):
    result: str = field(default='native_identity_unreviewed',init=False)
    isolation_verified: bool = field(default=False,init=False)
    management_policy_verified: bool = field(default=False,init=False)


class NativeIdentityAdapterH1:
    """No supplied JSON or synthetic observer can issue native attestation."""
    def observe_native(self):return NativeIdentityStatusH1()
