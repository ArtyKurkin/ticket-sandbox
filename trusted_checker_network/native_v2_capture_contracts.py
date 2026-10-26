"""V2-06a offline capture contracts. Content references never attest Linux facts.

The sole executable boundary in this revision is a deterministic fake. All OS
identity, permissions, build provenance and transport attestation stay unproven.
"""
from dataclasses import dataclass, field
import hashlib
from datetime import datetime, timezone

from . import native_v2_contracts as c


REGISTRY_VERSION = 'tc-read-only-argv-v2-offline-1'
MAX_AGGREGATE = 16 * 1048576
MAX_COMMANDS = 256
MAX_WINDOW_US = 2000000
CHUNK_BYTES = 16384
UNOBSERVED = ('namespace_fd_identity', 'reciprocal_peer_nsid_identity',
              'binary_build_source_provenance', 'authenticated_transport',
              'reader_permissions_capabilities', 'namespace_entry_privileges',
              'protected_executables_config_secrets_journals', 'exclusive_writers',
              'tc_ingress_egress', 'xdp', 'flowtables', 'forwarding_ipv4_ipv6',
              'proxy_arp_nd', 'bridge_netfilter', 'offloads', 'external_inherited_fds',
              'full_namespace_inventory', 'native_profile_acceptance')


def require(condition, reason):
    c._require(condition, 'v2_capture_' + reason)


def rows(value, cls, minimum=1, maximum=MAX_COMMANDS):
    c._rows(value, cls, minimum, maximum)


def unique(values):
    require(len(values) == len(set(values)), 'duplicate')


@dataclass(frozen=True, slots=True)
class ReadOperation2:
    source: str
    binary: str
    argv: tuple[str, ...]
    stdout_cap: int
    stderr_cap: int = 4096
    duration_us: int = 500000
    roles: tuple[str, ...] = ('host', 'runner', 'target')


# Static data, never executed at import or by a native backend in this revision.
OPERATIONS = tuple(ReadOperation2(source, binary, (binary, *args), cap) for source, binary, args, cap in (
    ('nft', '/usr/sbin/nft', ('-j', '-a', 'list', 'ruleset'), 262144),
    ('link', '/usr/sbin/ip', ('-j', '-d', 'link', 'show'), 1048576),
    ('address', '/usr/sbin/ip', ('-j', 'address', 'show'), 1048576),
    ('bridge_link', '/usr/sbin/bridge', ('-j', '-d', 'link', 'show'), 1048576),
    ('bridge_vlan', '/usr/sbin/bridge', ('-j', 'vlan', 'show'), 1048576),
    ('bridge_fdb', '/usr/sbin/bridge', ('-j', 'fdb', 'show'), 1048576),
    ('route4', '/usr/sbin/ip', ('-j', '-4', 'route', 'show', 'table', 'all'), 1048576),
    ('route6', '/usr/sbin/ip', ('-j', '-6', 'route', 'show', 'table', 'all'), 1048576),
    ('rule4', '/usr/sbin/ip', ('-j', '-4', 'rule', 'show'), 1048576),
    ('rule6', '/usr/sbin/ip', ('-j', '-6', 'rule', 'show'), 1048576),
))
REGISTRY_DIGEST = c._hash('read_only_registry',
    tuple((o.source, o.binary, o.argv, o.stdout_cap, o.stderr_cap, o.duration_us, o.roles) for o in OPERATIONS))


def operation2(source):
    c._enum(source, tuple(o.source for o in OPERATIONS))
    return next(o for o in OPERATIONS if o.source == source)


@dataclass(frozen=True, slots=True)
class BinaryReference2(c._Offline2):
    path: str
    binary_sha256: str
    build_version: str
    source_manifest_digest: str
    protection_review_digest: str

    def __post_init__(self):
        c._Offline2.__post_init__(self)
        c._enum(self.path, tuple(sorted({o.binary for o in OPERATIONS})))
        require(type(self.build_version) is str and 0 < len(self.build_version) <= 128, 'binary_version_invalid')
        try: version_bytes = self.build_version.encode('utf-8', errors='strict')
        except UnicodeEncodeError: raise c.ContractViolation2('v2_capture_binary_version_invalid') from None
        require(len(version_bytes) <= 128, 'binary_version_invalid')
        for value in (self.binary_sha256, self.source_manifest_digest, self.protection_review_digest):
            c._hex(value)


@dataclass(frozen=True, slots=True)
class BinaryManifest2(c._Offline2):
    binaries: tuple[BinaryReference2, ...]
    review_digest: str

    def __post_init__(self):
        c._Offline2.__post_init__(self); rows(self.binaries, BinaryReference2, 3, 3)
        c._hex(self.review_digest)
        require(tuple(b.path for b in self.binaries) == tuple(sorted({o.binary for o in OPERATIONS})),
                'binary_inventory_invalid')

    def binary(self, path):
        return next(b for b in self.binaries if b.path == path)


@dataclass(frozen=True, slots=True)
class NamespaceReference2(c._Offline2):
    role: str
    key: c.NamespaceKey2
    fd_reference_uuid: str
    reference_digest: str
    lookup_pid: int
    process_start_ticks: int
    nsid_mappings: tuple[tuple[int, int], ...]
    reciprocal_peer_reference_digests: tuple[str, ...]
    fd_state: str = 'open_in_mock_model'

    def __post_init__(self):
        c._Offline2.__post_init__(self); c._enum(self.role, ('host', 'runner', 'target'))
        c._typed(self.key, c.NamespaceKey2); c._uuid(self.fd_reference_uuid)
        c._hex(self.reference_digest); c._integer(self.lookup_pid); c._integer(self.process_start_ticks)
        require(type(self.nsid_mappings) is tuple and len(self.nsid_mappings) <= 16, 'nsid_invalid')
        for item in self.nsid_mappings:
            require(type(item) is tuple and len(item) == 2, 'nsid_invalid')
            c._integer(item[0], 0, 2**31-1); c._integer(item[1])
        unique([m[0] for m in self.nsid_mappings])
        require(type(self.reciprocal_peer_reference_digests) is tuple and
                len(self.reciprocal_peer_reference_digests) <= 16, 'peer_invalid')
        for value in self.reciprocal_peer_reference_digests: c._hex(value)
        unique(self.reciprocal_peer_reference_digests)
        c._enum(self.fd_state, ('open_in_mock_model', 'lost_in_mock_model'))


@dataclass(frozen=True, slots=True)
class ReaderPeerReference2(c._Offline2):
    first: c.NamespaceKey2
    first_ifindex: int
    first_nsid: int
    second: c.NamespaceKey2
    second_ifindex: int
    second_nsid: int
    witness_reference_digest: str

    def __post_init__(self):
        c._Offline2.__post_init__(self)
        c._typed(self.first, c.NamespaceKey2); c._typed(self.second, c.NamespaceKey2)
        for value in (self.first_ifindex, self.second_ifindex): c._integer(value, 1, 2**31-1)
        for value in (self.first_nsid, self.second_nsid): c._integer(value, 0, 2**31-1)
        c._hex(self.witness_reference_digest)
        require(self.first != self.second and self.first.host_boot_uuid == self.second.host_boot_uuid and
                self.first.reader_session_uuid == self.second.reader_session_uuid, 'peer_invalid')


@dataclass(frozen=True, slots=True)
class ReaderIdentity2(c._Offline2):
    reader_session_uuid: str
    reader_principal_digest: str
    installer_principal_digest: str
    writer_principal_digest: str
    validator_principal_digest: str
    approval_principal_digest: str
    permissions_review_digest: str
    configuration_digest: str
    writer_epoch_uuid: str
    namespaces: tuple[NamespaceReference2, ...]
    peers: tuple[ReaderPeerReference2, ...] = ()
    proof_basis: str = 'deterministic_mock_only'

    def __post_init__(self):
        c._Offline2.__post_init__(self); c._uuid(self.reader_session_uuid); c._uuid(self.writer_epoch_uuid)
        principals = (self.reader_principal_digest, self.installer_principal_digest, self.writer_principal_digest,
                      self.validator_principal_digest, self.approval_principal_digest)
        for value in (*principals, self.permissions_review_digest, self.configuration_digest): c._hex(value)
        unique(principals); rows(self.namespaces, NamespaceReference2, 1, 3)
        unique([n.role for n in self.namespaces]); unique([n.key.netns_inode for n in self.namespaces])
        unique([n.fd_reference_uuid for n in self.namespaces])
        require(len({n.key.host_boot_uuid for n in self.namespaces}) == 1 and
                all(n.key.reader_session_uuid == self.reader_session_uuid for n in self.namespaces),
                'session_mismatch')
        inodes = {n.key.netns_inode for n in self.namespaces}
        require(all(inode in inodes and inode != n.key.netns_inode
                    for n in self.namespaces for _, inode in n.nsid_mappings), 'nsid_invalid')
        rows(self.peers, ReaderPeerReference2, 0, 16)
        endpoints = []
        for peer in self.peers:
            first = next((n for n in self.namespaces if n.key == peer.first), None)
            second = next((n for n in self.namespaces if n.key == peer.second), None)
            require(first is not None and second is not None, 'peer_invalid')
            require((peer.first_nsid, second.key.netns_inode) in first.nsid_mappings and
                    (peer.second_nsid, first.key.netns_inode) in second.nsid_mappings and
                    peer.witness_reference_digest in first.reciprocal_peer_reference_digests and
                    peer.witness_reference_digest in second.reciprocal_peer_reference_digests, 'peer_invalid')
            endpoints.extend(((peer.first, peer.first_ifindex), (peer.second, peer.second_ifindex)))
        unique(endpoints)
        c._enum(self.proof_basis, ('deterministic_mock_only',))


@dataclass(frozen=True, slots=True)
class CaptureRequest2(c._Offline2):
    capture_uuid: str
    namespace: NamespaceReference2
    source: str
    decoder_profile_digest: str

    def __post_init__(self):
        c._Offline2.__post_init__(self); c._uuid(self.capture_uuid)
        c._typed(self.namespace, NamespaceReference2); c._hex(self.decoder_profile_digest)
        require(self.namespace.role in operation2(self.source).roles, 'role_invalid')

    @property
    def argv(self): return operation2(self.source).argv


@dataclass(frozen=True, slots=True)
class CapturePlan2(c._Offline2):
    plan_uuid: str
    installation: c.InstallKey2
    reader: ReaderIdentity2
    binaries: BinaryManifest2
    requests: tuple[CaptureRequest2, ...]
    registry_digest: str = REGISTRY_DIGEST
    purpose: str = 'inventory_preflight_only'

    def __post_init__(self):
        c._Offline2.__post_init__(self); c._uuid(self.plan_uuid)
        c._typed(self.installation, c.InstallKey2); c._typed(self.reader, ReaderIdentity2)
        c._typed(self.binaries, BinaryManifest2); rows(self.requests, CaptureRequest2)
        require(type(self.registry_digest) is str and self.registry_digest == REGISTRY_DIGEST, 'registry_mismatch')
        c._enum(self.purpose, ('inventory_preflight_only',))
        require(self.reader.writer_epoch_uuid == self.installation.writer_epoch_uuid, 'epoch_changed')
        require(all(n.fd_state == 'open_in_mock_model' for n in self.reader.namespaces), 'namespace_fd_lost')
        for request in self.requests:
            require(request.namespace in self.reader.namespaces, 'namespace_mismatch')
        unique([r.capture_uuid for r in self.requests])
        unique([(r.namespace.key, r.source) for r in self.requests])


@dataclass(frozen=True, slots=True)
class CaptureTime2:
    wall_utc_us: int
    monotonic_us: int

    def __post_init__(self):
        c._integer(self.wall_utc_us, 1, 253402300799000000)
        c._integer(self.monotonic_us, 0)

    @property
    def wall_utc(self):
        # Integer arithmetic preserves microseconds; this reads no clock.
        seconds, micros = divmod(self.wall_utc_us, 1000000)
        return datetime.fromtimestamp(seconds, timezone.utc).replace(microsecond=micros).isoformat()


@dataclass(frozen=True, slots=True)
class CaptureSession2(c._Offline2):
    session_uuid: str
    plan_digest: str
    reader: ReaderIdentity2
    started: CaptureTime2
    deadline_monotonic_us: int

    def __post_init__(self):
        c._Offline2.__post_init__(self); c._uuid(self.session_uuid); c._hex(self.plan_digest)
        c._typed(self.reader, ReaderIdentity2); c._typed(self.started, CaptureTime2)
        c._integer(self.deadline_monotonic_us, 1)
        require(self.deadline_monotonic_us == self.started.monotonic_us + MAX_WINDOW_US,
                'deadline_invalid')


@dataclass(frozen=True, slots=True)
class TransportCompletion2(c._Offline2):
    session_uuid: str
    request_digest: str
    invocation_ordinal: int
    stdout_sha256: str
    stderr_sha256: str
    status: str = 'mock_stream_eofs_exit_and_completion_observed'

    def __post_init__(self):
        c._Offline2.__post_init__(self); c._uuid(self.session_uuid)
        for value in (self.request_digest, self.stdout_sha256, self.stderr_sha256): c._hex(value)
        c._integer(self.invocation_ordinal, 0, MAX_COMMANDS-1)
        require(self.status == 'mock_stream_eofs_exit_and_completion_observed', 'receipt_invalid')


@dataclass(frozen=True, slots=True)
class CaptureArtifact2(c._Offline2):
    session: CaptureSession2
    request: CaptureRequest2
    observed_binary: BinaryReference2
    started: CaptureTime2
    finished: CaptureTime2
    stdout: bytes = field(repr=False)
    stderr: bytes = field(repr=False)
    completion: TransportCompletion2
    exit_status: int = 0
    truncated: bool = False
    interrupted: bool = False
    timed_out: bool = False

    def __post_init__(self):
        c._Offline2.__post_init__(self)
        for value, cls in ((self.session, CaptureSession2), (self.request, CaptureRequest2),
                           (self.observed_binary, BinaryReference2), (self.started, CaptureTime2),
                           (self.finished, CaptureTime2), (self.completion, TransportCompletion2)):
            c._typed(value, cls)
        op = operation2(self.request.source)
        require(self.observed_binary.path == op.binary, 'binary_mismatch')
        require(type(self.stdout) is bytes and len(self.stdout) <= op.stdout_cap and
                type(self.stderr) is bytes and len(self.stderr) <= op.stderr_cap, 'output_limit')
        require(type(self.exit_status) is int and self.exit_status == 0, 'nonzero_exit')
        require(self.truncated is False and self.interrupted is False and self.timed_out is False,
                'transport_incomplete')
        require(self.request.namespace in self.session.reader.namespaces, 'namespace_mismatch')
        require(self.session.started.monotonic_us <= self.started.monotonic_us <= self.finished.monotonic_us <=
                self.session.deadline_monotonic_us and
                self.finished.monotonic_us-self.started.monotonic_us <= op.duration_us and
                self.session.started.wall_utc_us <= self.started.wall_utc_us <= self.finished.wall_utc_us and
                self.finished.wall_utc_us-self.session.started.wall_utc_us <= MAX_WINDOW_US and
                self.finished.wall_utc_us-self.started.wall_utc_us <= op.duration_us,
                'timing_unproven')
        r = self.completion
        require(r.session_uuid == self.session.session_uuid and r.request_digest == self.request.digest and
                r.stdout_sha256 == self.stdout_sha256 and r.stderr_sha256 == hashlib.sha256(self.stderr).hexdigest(),
                'receipt_mismatch')

    @property
    def stdout_sha256(self): return hashlib.sha256(self.stdout).hexdigest()

    @property
    def stdout_byte_count(self): return len(self.stdout)

    @property
    def stderr_category(self): return 'bounded_stderr_present' if self.stderr else 'empty'

    @property
    def digest(self):
        self.__post_init__()
        return c._hash('capture_artifact', (self.session.digest, self.request.digest, self.observed_binary.digest,
                       self.started.wall_utc_us, self.started.monotonic_us, self.finished.wall_utc_us,
                       self.finished.monotonic_us, self.stdout_sha256, len(self.stdout),
                       self.completion.digest, len(self.stderr), self.stderr_category))


@dataclass(frozen=True, slots=True)
class CaptureManifest2(c._Offline2):
    plan: CapturePlan2
    session: CaptureSession2
    artifacts: tuple[CaptureArtifact2, ...]

    def __post_init__(self):
        c._Offline2.__post_init__(self); c._typed(self.plan, CapturePlan2); c._typed(self.session, CaptureSession2)
        rows(self.artifacts, CaptureArtifact2, 0)
        require(self.session.plan_digest == self.plan.digest and self.session.reader == self.plan.reader,
                'plan_mismatch')
        require(tuple(a.request for a in self.artifacts) == self.plan.requests, 'source_coverage_incomplete')
        total = 0; previous = self.session.started
        for index, artifact in enumerate(self.artifacts):
            require(artifact.session == self.session and artifact.completion.invocation_ordinal == index,
                    'replay_or_substitution')
            require(artifact.observed_binary == self.plan.binaries.binary(operation2(artifact.request.source).binary),
                    'binary_mismatch')
            require(artifact.started.monotonic_us >= previous.monotonic_us and
                    artifact.started.wall_utc_us >= previous.wall_utc_us, 'clock_rollback')
            previous = artifact.finished
            total += len(artifact.stdout) + len(artifact.stderr)
            require(total <= MAX_AGGREGATE, 'aggregate_limit')

    @property
    def digest(self):
        self.__post_init__()
        return c._hash('capture_manifest', (self.plan.digest, self.session.digest,
                                          tuple(a.digest for a in self.artifacts)))


@dataclass(frozen=True, slots=True)
class UnsupportedEvidence2:
    namespace_reference_digest: str
    surface: str
    status: str = 'unsupported_unobserved'

    def __post_init__(self):
        c._hex(self.namespace_reference_digest); c._enum(self.surface, UNOBSERVED)
        require(self.status == 'unsupported_unobserved', 'os_evidence_unproven')


@dataclass(frozen=True, slots=True)
class CaptureValidation2(c._Offline2):
    session: CaptureSession2
    manifest: CaptureManifest2 | None
    reason: str
    result: str = field(init=False)
    os_identity: str = field(default='unproven', init=False)
    timing: str = field(default='timing_unproven_for_physical_inventory', init=False)
    management_policy_verified: bool = field(default=False, init=False)
    isolation_verified: bool = field(default=False, init=False)
    measurement_verified: bool = field(default=False, init=False)
    requirements: tuple[str, ...] = field(default=UNOBSERVED, init=False)
    evidence_statuses: tuple[UnsupportedEvidence2, ...] = field(init=False)

    def __post_init__(self):
        c._Offline2.__post_init__(self); c._typed(self.session, CaptureSession2)
        require(self.management_policy_verified is False and self.isolation_verified is False and
                self.measurement_verified is False and self.requirements == UNOBSERVED and
                self.os_identity == 'unproven' and self.timing == 'timing_unproven_for_physical_inventory',
                'authority_forbidden')
        c._enum(self.reason, REASONS)
        if self.manifest is None:
            require(self.reason != 'mock_capture_preserved_os_unproven', 'result_invalid')
        else:
            c._typed(self.manifest, CaptureManifest2)
            require(self.manifest.session == self.session and self.reason == 'mock_capture_preserved_os_unproven',
                    'result_invalid')
        object.__setattr__(self, 'result', 'capture_preserved_in_mock_model' if self.manifest else 'unknown')
        object.__setattr__(self, 'evidence_statuses', tuple(
            UnsupportedEvidence2(n.reference_digest, surface)
            for n in self.session.reader.namespaces for surface in UNOBSERVED))

    @property
    def digest(self):
        self.__post_init__()
        return c._hash('capture_validation', (self.session.digest,
                       self.manifest.digest if self.manifest else None, self.result, self.reason, self.requirements))


REASONS = ('mock_capture_preserved_os_unproven', 'disabled', 'killed', 'identity_changed',
           'namespace_fd_lost', 'binary_mismatch', 'stream_invalid', 'transport_incomplete',
           'stdout_limit', 'stderr_limit', 'aggregate_limit', 'timeout', 'interrupted',
           'process_died', 'nonzero_exit', 'clock_rollback', 'timing_unproven',
           'missing_source', 'source_substitution', 'evidence_invalid')
