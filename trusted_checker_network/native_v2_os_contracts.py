"""Dormant Linux reader descriptions. No OS activation grant or attestation.

All supplied references are offline inputs. The old CapturePlan2 is a structural
template only; neither it nor this profile can authorize native execution.
"""
from dataclasses import dataclass, field
import hashlib

from . import native_v2_contracts as c
from . import native_v2_capture_contracts as capture


PREFIX = 'v2_os_reader_'
ENVIRONMENT = (('LANG', 'C'), ('LC_ALL', 'C'))
CAPABILITIES = ('CAP_NET_ADMIN', 'CAP_SYS_ADMIN')
UNRESOLVED = ('native_execution_authority', 'namespace_helper_privilege_review',
              'descriptor_exec_and_dependency_closure', 'binary_write_exclusion',
              'os_principal_protection', 'authenticated_transport', 'durable_replay',
              'full_os_source_coverage', 'native_timing_calibration')


def require(condition, reason): c._require(condition, PREFIX + reason)


def integer_tuple(value, maximum=32):
    require(type(value) is tuple and len(value) <= maximum, 'collection_invalid')
    for item in value: c._integer(item, 0, 2**31-1)
    require(value == tuple(sorted(set(value))), 'collection_invalid')


@dataclass(frozen=True, slots=True)
class OSPrincipal2(c._Offline2):
    uid: int
    gid: int
    supplementary_groups: tuple[int, ...]
    effective_caps: tuple[str, ...]
    permitted_caps: tuple[str, ...]
    bounding_caps: tuple[str, ...]
    ambient_caps: tuple[str, ...] = ()
    no_new_privileges: bool = True

    def __post_init__(self):
        c._Offline2.__post_init__(self)
        c._integer(self.uid, 0, 2**31-1); c._integer(self.gid, 0, 2**31-1)
        integer_tuple(self.supplementary_groups)
        for caps in (self.effective_caps, self.permitted_caps, self.bounding_caps, self.ambient_caps):
            require(type(caps) is tuple and len(caps) <= len(CAPABILITIES), 'capabilities_invalid')
            for cap in caps: c._enum(cap, CAPABILITIES)
            require(caps == tuple(sorted(set(caps))), 'capabilities_invalid')
        require(set(self.effective_caps) <= set(self.permitted_caps) <= set(self.bounding_caps), 'capabilities_invalid')
        require(self.ambient_caps == () and self.no_new_privileges is True, 'privileges_invalid')


@dataclass(frozen=True, slots=True)
class NamespaceFdPin2(c._Offline2):
    reference: capture.NamespaceReference2
    fd: int
    fd_generation: int
    device: int
    lookup_pid: int
    lookup_start_ticks: int

    def __post_init__(self):
        c._Offline2.__post_init__(self); c._typed(self.reference, capture.NamespaceReference2)
        c._integer(self.fd, 3, 2**20-1); c._integer(self.fd_generation)
        c._integer(self.device, 0); c._integer(self.lookup_pid); c._integer(self.lookup_start_ticks)
        require(self.lookup_pid == self.reference.lookup_pid and
                self.lookup_start_ticks == self.reference.process_start_ticks, 'pid_generation_mismatch')


@dataclass(frozen=True, slots=True)
class InventoryTimingProposal2(c._Offline2):
    profile_id: str = 'os-inventory-timing-proposal-v2-1'
    capture_us: int = 2000000
    command_us: int = 500000
    terminate_us: int = 50000
    drain_us: int = 50000
    reap_us: int = 100000
    acceptance: str = 'unmeasured_not_approved'

    def __post_init__(self):
        c._Offline2.__post_init__(self)
        for actual, expected in ((self.profile_id, 'os-inventory-timing-proposal-v2-1'),
                                  (self.acceptance, 'unmeasured_not_approved')):
            require(type(actual) is str and actual == expected, 'timing_profile_invalid')
        for actual, expected in ((self.capture_us,2000000),(self.command_us,500000),
                                  (self.terminate_us,50000),(self.drain_us,50000),(self.reap_us,100000)):
            require(type(actual) is int and actual == expected, 'timing_profile_invalid')


@dataclass(frozen=True, slots=True)
class OSReadPolicy2(c._Offline2):
    template: capture.CapturePlan2
    helper_principal: OSPrincipal2
    command_principal: OSPrincipal2
    namespace_fds: tuple[NamespaceFdPin2, ...]
    allowed_inherited_fds: tuple[int, ...]
    executable_review_digest: str
    configuration_review_digest: str
    secret_journal_protection_digest: str
    timing: InventoryTimingProposal2
    registry_version: str = capture.REGISTRY_VERSION
    environment: tuple[tuple[str,str], ...] = ENVIRONMENT

    def __post_init__(self):
        c._Offline2.__post_init__(self); c._typed(self.template,capture.CapturePlan2)
        c._typed(self.helper_principal,OSPrincipal2); c._typed(self.command_principal,OSPrincipal2)
        c._rows(self.namespace_fds,NamespaceFdPin2,1,3)
        require(tuple(n.reference for n in self.namespace_fds) == self.template.reader.namespaces,
                'namespace_inventory_mismatch')
        require(len({n.fd for n in self.namespace_fds}) == len(self.namespace_fds), 'fd_collision')
        integer_tuple(self.allowed_inherited_fds)
        require(self.allowed_inherited_fds == tuple(sorted((0,1,2,*(n.fd for n in self.namespace_fds)))),
                'fd_allowlist_invalid')
        require(type(self.registry_version) is str and self.registry_version == capture.REGISTRY_VERSION and
                self.environment == ENVIRONMENT and type(self.environment) is tuple, 'execution_profile_invalid')
        for value in (self.executable_review_digest,self.configuration_review_digest,self.secret_journal_protection_digest):
            c._hex(value)
        c._typed(self.timing,InventoryTimingProposal2)


@dataclass(frozen=True, slots=True)
class ExecutableObservation2(c._Offline2):
    path: str
    fd: int
    device: int
    inode: int
    size: int
    ctime_ns: int
    mode: int
    uid: int
    gid: int
    links: int
    sha256: str
    source_manifest_digest: str
    no_symlink_components: bool
    protected_ancestors: bool
    no_file_capabilities: bool
    descriptor_execution: str = 'required_not_native_proven'

    def __post_init__(self):
        c._Offline2.__post_init__(self)
        c._enum(self.path,tuple(sorted({o.binary for o in capture.OPERATIONS})))
        c._integer(self.fd,3,2**20-1);c._integer(self.device,0);c._integer(self.inode)
        c._integer(self.size,1,67108864);c._integer(self.ctime_ns);c._integer(self.mode,0,0o177777)
        c._integer(self.uid,0,2**31-1);c._integer(self.gid,0,2**31-1);c._integer(self.links,1,65536)
        c._hex(self.sha256);c._hex(self.source_manifest_digest)
        for value in (self.no_symlink_components,self.protected_ancestors,self.no_file_capabilities):
            require(type(value) is bool,'observation_invalid')
        c._enum(self.descriptor_execution,('required_not_native_proven',))


@dataclass(frozen=True, slots=True)
class ReaderObservation2(c._Offline2):
    principal: OSPrincipal2
    host_boot_uuid: str
    reader_session_uuid: str
    reader_pid: int
    reader_start_ticks: int
    writer_epoch_uuid: str
    inherited_fds: tuple[int,...]
    namespace_fds: tuple[NamespaceFdPin2,...]
    namespace_inodes: tuple[int,...]
    fd_open: tuple[bool,...]

    def __post_init__(self):
        c._Offline2.__post_init__(self);c._typed(self.principal,OSPrincipal2)
        for value in (self.host_boot_uuid,self.reader_session_uuid,self.writer_epoch_uuid):c._uuid(value)
        c._integer(self.reader_pid);c._integer(self.reader_start_ticks);integer_tuple(self.inherited_fds)
        c._rows(self.namespace_fds,NamespaceFdPin2,1,3)
        require(type(self.namespace_inodes) is tuple and type(self.fd_open) is tuple and
                len(self.namespace_fds)==len(self.namespace_inodes)==len(self.fd_open),'observation_invalid')
        for value in self.namespace_inodes:c._integer(value)
        for value in self.fd_open:require(type(value) is bool,'observation_invalid')


@dataclass(frozen=True, slots=True)
class ChildHandle2(c._Offline2):
    pid: int
    start_ticks: int
    invocation_uuid: str
    namespace_pin_digest: str
    executable_digest: str

    def __post_init__(self):
        c._Offline2.__post_init__(self);c._integer(self.pid);c._integer(self.start_ticks)
        c._uuid(self.invocation_uuid);c._hex(self.namespace_pin_digest);c._hex(self.executable_digest)


@dataclass(frozen=True, slots=True)
class HelperAttestation2(c._Offline2):
    """Fake helper setup description, not accepted native attestation."""
    session_uuid: str
    child: ChildHandle2
    namespace: NamespaceFdPin2
    executable_fd: int
    command_principal: OSPrincipal2
    inherited_fds_after_exec: tuple[int,...]
    environment: tuple[tuple[str,str],...]
    stdin_kind: str
    basis: str = 'fake_helper_setup_only'

    def __post_init__(self):
        c._Offline2.__post_init__(self);c._uuid(self.session_uuid);c._typed(self.child,ChildHandle2)
        c._typed(self.namespace,NamespaceFdPin2);c._integer(self.executable_fd,3,2**20-1)
        c._typed(self.command_principal,OSPrincipal2);integer_tuple(self.inherited_fds_after_exec)
        require(type(self.environment) is tuple and len(self.environment)<=8,'helper_invalid')
        for pair in self.environment:
            require(type(pair) is tuple and len(pair)==2 and all(type(x) is str and len(x)<=128 for x in pair),'helper_invalid')
        c._enum(self.stdin_kind,('dev_null','untrusted_inherited'))
        c._enum(self.basis,('fake_helper_setup_only',))


@dataclass(frozen=True, slots=True)
class OSCommandArtifact2(c._Offline2):
    """New unproven transport record; never mislabelled with an old mock receipt."""
    session: capture.CaptureSession2
    request: capture.CaptureRequest2
    executable: ExecutableObservation2
    child: ChildHandle2
    started: capture.CaptureTime2
    finished: capture.CaptureTime2
    stdout: bytes = field(repr=False)
    stderr: bytes = field(repr=False)
    reader_before: ReaderObservation2
    reader_after: ReaderObservation2
    helper: HelperAttestation2
    completion: str = 'fake_os_driver_eofs_exit_reap_and_handshake'
    exit_status: int = 0
    stdout_eof: bool = True
    stderr_eof: bool = True
    truncated: bool = False
    interrupted: bool = False
    timed_out: bool = False

    def __post_init__(self):
        c._Offline2.__post_init__(self)
        for value,cls in ((self.session,capture.CaptureSession2),(self.request,capture.CaptureRequest2),
                           (self.executable,ExecutableObservation2),(self.child,ChildHandle2),
                           (self.started,capture.CaptureTime2),(self.finished,capture.CaptureTime2),
                           (self.reader_before,ReaderObservation2),(self.reader_after,ReaderObservation2),
                           (self.helper,HelperAttestation2)):
            c._typed(value,cls)
        op=capture.operation2(self.request.source)
        require(type(self.stdout) is bytes and len(self.stdout)<=op.stdout_cap and
                type(self.stderr) is bytes and len(self.stderr)<=op.stderr_cap,'output_limit')
        require(self.reader_before==self.reader_after,'identity_changed')
        require(self.child.namespace_pin_digest in tuple(n.digest for n in self.reader_before.namespace_fds) and
                self.child.executable_digest==self.executable.digest,'child_mismatch')
        require(self.executable.path==op.binary,'executable_mismatch')
        require(self.helper.session_uuid==self.session.session_uuid and self.helper.child==self.child and
                self.helper.executable_fd==self.executable.fd and self.helper.namespace.digest==self.child.namespace_pin_digest,
                'child_mismatch')
        require(type(self.exit_status) is int and self.exit_status==0 and self.stdout_eof is True and
                self.stderr_eof is True and self.truncated is False and self.interrupted is False and
                self.timed_out is False,'incomplete_output')
        require(self.session.started.monotonic_us<=self.started.monotonic_us<=self.finished.monotonic_us<=
                self.session.deadline_monotonic_us and self.started.wall_utc_us<=self.finished.wall_utc_us and
                self.finished.monotonic_us-self.started.monotonic_us<=op.duration_us and
                self.session.started.wall_utc_us<=self.started.wall_utc_us and
                self.finished.wall_utc_us-self.started.wall_utc_us<=op.duration_us and
                self.finished.wall_utc_us-self.session.started.wall_utc_us<=capture.MAX_WINDOW_US,'timing_unproven')
        c._enum(self.completion,('fake_os_driver_eofs_exit_reap_and_handshake',))

    @property
    def digest(self):
        self.__post_init__()
        return c._hash('os_command_artifact',(self.session.digest,self.request.digest,self.executable.digest,
                       self.child.digest,self.started.wall_utc_us,self.started.monotonic_us,
                       self.finished.wall_utc_us,self.finished.monotonic_us,
                       hashlib.sha256(self.stdout).hexdigest(),len(self.stdout),
                       hashlib.sha256(self.stderr).hexdigest(),len(self.stderr),self.reader_before.digest,
                       self.reader_after.digest,self.helper.digest,self.completion,
                       self.exit_status,self.stdout_eof,self.stderr_eof,self.truncated,self.interrupted,self.timed_out))


REASONS=('fake_driver_capture_preserved_os_unproven','disabled','killed','executable_mismatch',
         'executable_unprotected','executable_changed','namespace_mismatch','namespace_fd_lost',
         'pid_reuse','principal_mismatch','inherited_fd','identity_changed','source_substitution',
         'stdout_limit','stderr_limit','aggregate_limit','timeout','clock_rollback','incomplete_output',
         'nonzero_exit','interrupted','reader_died','handshake_missing','reap_unproven',
         'cleanup_unproven','driver_protocol_invalid','evidence_invalid')


@dataclass(frozen=True, slots=True)
class OSReadResult2(c._Offline2):
    session: capture.CaptureSession2
    policy_digest: str
    artifacts: tuple[OSCommandArtifact2,...]
    reason: str
    cleanup: str
    result: str = field(init=False)
    isolation_verified: bool = field(default=False,init=False)
    management_policy_verified: bool = field(default=False,init=False)
    measurement_verified: bool = field(default=False,init=False)
    os_provenance: str = field(default='unproven',init=False)
    unresolved: tuple[str,...] = field(default=UNRESOLVED,init=False)
    unsupported_surfaces: tuple[str,...] = field(default=capture.UNOBSERVED,init=False)

    def __post_init__(self):
        c._Offline2.__post_init__(self);c._typed(self.session,capture.CaptureSession2);c._hex(self.policy_digest)
        c._rows(self.artifacts,OSCommandArtifact2,0,256);c._enum(self.reason,REASONS)
        c._enum(self.cleanup,('no_child','reaped_and_closed','quarantine_cleanup_unproven'))
        require(self.isolation_verified is False and self.management_policy_verified is False and
                self.measurement_verified is False and self.os_provenance=='unproven' and self.unresolved==UNRESOLVED,
                'authority_forbidden')
        require(self.unsupported_surfaces==capture.UNOBSERVED,'authority_forbidden')
        success=self.reason=='fake_driver_capture_preserved_os_unproven'
        require((success and len(self.artifacts)>0 and self.cleanup=='reaped_and_closed') or
                (not success and self.artifacts==()),'result_invalid')
        require(all(a.session==self.session for a in self.artifacts),'session_mismatch')
        object.__setattr__(self,'result','capture_preserved_in_fake_os_model' if success else 'unknown')

    @property
    def digest(self):
        self.__post_init__()
        return c._hash('os_read_result',(self.session.digest,self.policy_digest,tuple(a.digest for a in self.artifacts),
                                       self.reason,self.cleanup,self.unresolved))
