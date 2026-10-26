"""Versioned closed DTOs; candidate metadata never has an enrollment conversion."""

from dataclasses import asdict, dataclass
from datetime import datetime
from enum import StrEnum
import math
import re
from uuid import UUID

from trusted_checker_shadow.policy import POLICY, TASK, digest
from .profiles import LIMITS, RUNNER_PROFILE, TARGET_PROFILE, Limits, NetworkProfile, require
from .live_contract import LIVE_POLICY, LIVE_RUNNER, LIVE_TARGET, LIVE_PREFLIGHT_CASES, live_environment


def uid(value):
    try:
        good = type(value) is str and str(UUID(value)) == value
    except (ValueError, TypeError, AttributeError):
        good = False
    require(good, "uuid_invalid")


def full_id(value, image=False):
    require(type(value) is str and re.fullmatch(r"sha256:[0-9a-f]{64}" if image else r"[0-9a-f]{64}", value)
            is not None, "image_invalid" if image else "full_id_required")


def atom(value, prefix=""):
    require(type(value) is str and re.fullmatch(re.escape(prefix)+r"[a-zA-Z0-9][a-zA-Z0-9_.:-]{0,79}", value)
            is not None, "reference_invalid")


def stamp(value):
    require(type(value) in (int, float) and math.isfinite(value) and value > 0, "timestamp_invalid")


def scope(value):
    require(type(value) is str and re.fullmatch(r"(?:test|staging)-shadow-[a-z0-9-]{1,30}", value) is not None
            and not re.search(r"(?:^|-)(?:prod|production|live)(?:-|$)", value), "nonproduction_scope_required")


def docker_time(value):
    require(type(value) is str and re.fullmatch(
        r"20\d{2}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,9})?(?:Z|[+-]\d{2}:\d{2})", value)
        is not None, "docker_started_at_invalid")
    try:
        datetime.fromisoformat(value)
    except ValueError:
        require(False, "docker_started_at_invalid")


class Resource(StrEnum):
    TARGET = "authority_created_target"
    RUNNER = "shadow_runner"


class Phase(StrEnum):
    ENROLL = "enrollment"
    BEFORE_CREATE = "before_runner_create"
    BEFORE_START = "before_runner_start"
    BEFORE_PROBE = 'before_probe'
    AFTER_PROBE = "after_probe"
    BEFORE_PUBLISH = "before_publish"


@dataclass(frozen=True)
class AttemptReference:
    sandbox_instance: str
    attempt_id: int
    owner_id: int
    task: str = TASK

    def __post_init__(self):
        atom(self.sandbox_instance)
        require(all(type(n) is int and 0 < n <= 2**63-1 for n in (self.attempt_id, self.owner_id)), "attempt_reference_invalid")
        require(type(self.task) is str and self.task == TASK, "task_not_allowed")


@dataclass(frozen=True)
class DaemonIdentity:
    daemon_id: str
    endpoint_reference: str
    endpoint_config_digest: str
    session_uuid: str

    def __post_init__(self):
        atom(self.daemon_id)
        atom(self.endpoint_reference, "endpoint:")
        full_id(self.endpoint_config_digest)
        uid(self.session_uuid)


@dataclass(frozen=True)
class RuntimeApproval:
    approval_uuid: str
    operator_principal: str
    scope: str
    daemon: DaemonIdentity
    target_image_id: str
    runner_image_id: str
    checker_source_digest: str
    network: NetworkProfile
    created_at: float
    expires_at: float
    limits: Limits = LIMITS
    task: str = TASK
    policy_id: str = POLICY.policy_id
    policy_version: int = POLICY.version
    policy_digest: str = POLICY.digest
    target_profile_digest: str = TARGET_PROFILE.digest
    runner_profile_digest: str = RUNNER_PROFILE.digest
    schema_version: int = 1
    authority_mode: str = "offline_runtime_contract_only"

    def __post_init__(self):
        uid(self.approval_uuid)
        atom(self.operator_principal, "operator:")
        scope(self.scope)
        require(type(self.daemon) is DaemonIdentity and type(self.network) is NetworkProfile
                and type(self.limits) is Limits, "approval_contract_invalid")
        self.daemon.__post_init__()
        self.network.__post_init__()
        self.limits.__post_init__()
        full_id(self.target_image_id, True)
        full_id(self.runner_image_id, True)
        full_id(self.checker_source_digest)
        require(self.target_image_id != self.runner_image_id, "images_must_be_distinct")
        stamp(self.created_at)
        stamp(self.expires_at)
        require(0 < self.expires_at-self.created_at <= 3600, "approval_lifetime_invalid")
        live = self.authority_mode == 'live_runtime_v2'
        policy = LIVE_POLICY if live else POLICY
        require(self.task == TASK and (self.policy_id, self.policy_version, self.policy_digest) ==
                (policy.policy_id, policy.version, policy.digest) and type(self.policy_version) is int,
                "approval_policy_mismatch")
        target, runner = (LIVE_TARGET, LIVE_RUNNER) if live else (TARGET_PROFILE, RUNNER_PROFILE)
        require(self.target_profile_digest == target.digest and self.runner_profile_digest == runner.digest,
                "approval_profile_mismatch")
        require(type(self.schema_version) is int and self.schema_version == (2 if live else 1) and
                self.authority_mode in ('live_runtime_v2', 'offline_runtime_contract_only'), "approval_version_invalid")

    @property
    def digest(self):
        return digest(asdict(self))

    @classmethod
    def from_dict(cls, body):
        return cls(**{**body, "daemon": DaemonIdentity(**body["daemon"]),
                      "network": NetworkProfile(**body["network"]), "limits": Limits(**body["limits"])})


@dataclass(frozen=True)
class ProvisionRequest:
    request_uuid: str
    approval_uuid: str
    attempt: AttemptReference

    def __post_init__(self):
        uid(self.request_uuid)
        uid(self.approval_uuid)
        require(type(self.attempt) is AttemptReference, "attempt_reference_invalid")
        self.attempt.__post_init__()


@dataclass(frozen=True)
class CreateIntent:
    intent_uuid: str
    resource: Resource
    approval_uuid: str
    approval_digest: str
    scope: str
    attempt: AttemptReference
    runtime_binding_uuid: str
    generation_uuid: str
    daemon: DaemonIdentity
    image_id: str
    network_profile_digest: str
    policy_digest: str
    profile_digest: str
    request_fingerprint: str
    created_at: float
    deadline: float

    def __post_init__(self):
        for value in (self.intent_uuid, self.approval_uuid, self.runtime_binding_uuid, self.generation_uuid):
            uid(value)
        require(type(self.resource) is Resource, "resource_domain_invalid")
        scope(self.scope)
        require(type(self.attempt) is AttemptReference and type(self.daemon) is DaemonIdentity, "intent_invalid")
        self.attempt.__post_init__()
        self.daemon.__post_init__()
        full_id(self.image_id, True)
        for value in (self.approval_digest, self.network_profile_digest, self.policy_digest, self.profile_digest, self.request_fingerprint):
            full_id(value)
        stamp(self.created_at)
        stamp(self.deadline)
        require(0 < self.deadline-self.created_at <= LIMITS.run_seconds, "intent_deadline_invalid")

    @classmethod
    def from_dict(cls, body):
        return cls(**{**body, "resource": Resource(body["resource"]), "attempt": AttemptReference(**body["attempt"]),
                      "daemon": DaemonIdentity(**body["daemon"])})


@dataclass(frozen=True)
class DispatchPermit:
    permit_uuid: str
    intent_uuid: str
    resource: Resource
    intent_digest: str
    control_epoch: int
    deadline: float

    def __post_init__(self):
        uid(self.permit_uuid)
        uid(self.intent_uuid)
        require(type(self.resource) is Resource and type(self.control_epoch) is int and self.control_epoch >= 0,
                "permit_invalid")
        full_id(self.intent_digest)
        stamp(self.deadline)


@dataclass(frozen=True)
class DaemonObservation:
    receipt_uuid: str
    context_uuid: str
    scope: str
    daemon: DaemonIdentity
    observed_at: float

    def __post_init__(self):
        common(self)
        require(type(self.daemon) is DaemonIdentity, "daemon_observation_invalid")
        self.daemon.__post_init__()


def common(value):
    uid(value.receipt_uuid)
    uid(value.context_uuid)
    scope(value.scope)
    stamp(value.observed_at)


@dataclass(frozen=True)
class CreateResponse:
    receipt_uuid: str
    context_uuid: str
    scope: str
    daemon: DaemonIdentity
    observed_at: float
    permit_uuid: str
    resource: Resource
    intent_digest: str
    container_id: str
    image_id: str

    def __post_init__(self):
        common(self)
        uid(self.permit_uuid)
        full_id(self.intent_digest)
        full_id(self.container_id)
        full_id(self.image_id, True)
        require(type(self.daemon) is DaemonIdentity and type(self.resource) is Resource, "create_response_invalid")
        self.daemon.__post_init__()


@dataclass(frozen=True)
class CreateTrace:
    receipt_uuid: str
    context_uuid: str
    scope: str
    observed_at: float
    resource: Resource
    daemon: DaemonIdentity
    intent_digest: str
    container_id: str
    image_id: str
    create_at: float
    source_kind: str
    source_digest: str

    def __post_init__(self):
        common(self)
        require(type(self.resource) is Resource and type(self.daemon) is DaemonIdentity and
                self.source_kind in ('independent_daemon_create_event', 'contemporaneous_trusted_trace'), 'create_trace_invalid')
        self.daemon.__post_init__()
        for value in (self.intent_digest, self.container_id, self.source_digest):
            full_id(value)
        full_id(self.image_id, True)
        stamp(self.create_at)
        require(self.create_at <= self.observed_at, 'create_trace_time_invalid')


@dataclass(frozen=True)
class Endpoint:
    container_id: str
    network_id: str
    endpoint_id: str
    ipv4: str

    def __post_init__(self):
        import ipaddress
        for value in (self.container_id, self.network_id, self.endpoint_id):
            full_id(value)
        try:
            good = type(self.ipv4) is str and str(ipaddress.IPv4Address(self.ipv4)) == self.ipv4
        except (ValueError, TypeError):
            good = False
        require(good, "endpoint_ipv4_invalid")


@dataclass(frozen=True)
class RuntimeConfig:
    user: str
    read_only: bool
    privileged: bool
    cap_drop: tuple
    cap_add: tuple
    no_new_privileges: bool
    pid_mode: str
    ipc_mode: str
    host_mounts: int
    docker_socket: bool
    tmpfs_digest: str
    entrypoint_digest: str
    cpu_nanos: int
    memory: int
    pids: int
    network_mode: str
    log_limit_bytes: int
    output_limit_bytes: int
    network_count: int = 1
    environment_digest: str = digest([])
    log_files: int = 1
    stdin_open: bool = False
    tty: bool = False
    working_dir: str = ''

    def __post_init__(self):
        require(type(self.user) is str and re.fullmatch(r"\d{1,5}:\d{1,5}", self.user) is not None, "runtime_config_invalid")
        require(all(type(getattr(self, n)) is bool for n in
                ("read_only", "privileged", "no_new_privileges", "docker_socket", "stdin_open", "tty")), "runtime_config_invalid")
        require(self.working_dir in ('', '/', '/scratch'), 'runtime_workdir_invalid')
        require(all(type(getattr(self, n)) is int and 0 <= getattr(self, n) <= 2**40 for n in
                ("host_mounts", "cpu_nanos", "memory", "pids", "log_limit_bytes", "output_limit_bytes", "network_count", "log_files")), "runtime_config_invalid")
        for caps in (self.cap_drop, self.cap_add):
            require(type(caps) is tuple and len(caps) <= 16 and all(type(c) is str and
                    re.fullmatch(r"[A-Z_]{1,30}", c) for c in caps), "runtime_config_invalid")
        require(self.pid_mode in ("private", "host") and self.ipc_mode in ("private", "host"), "runtime_config_invalid")
        for value in (self.tmpfs_digest, self.entrypoint_digest, self.network_mode, self.environment_digest):
            full_id(value)


def expected_config(approval, resource):
    runner = resource == Resource.RUNNER
    profile = RUNNER_PROFILE if runner else TARGET_PROFILE
    live = approval.authority_mode == 'live_runtime_v2'
    if live:
        profile = LIVE_RUNNER if runner else LIVE_TARGET
    return RuntimeConfig(profile.user, profile.read_only, False, ("ALL",), (), True, "private", "private", 0, False,
                         digest(tuple(sorted(profile.tmpfs)) if live else profile.tmpfs),
                         digest({"entrypoint": profile.entrypoint, "command": profile.command}),
                         LIMITS.runner_cpu_nanos if runner else LIMITS.target_cpu_nanos,
                         LIMITS.runner_memory if runner else LIMITS.target_memory,
                         LIMITS.runner_pids if runner else LIMITS.target_pids,
                         approval.network.network_id, 16384, 4096,
                         environment_digest=digest(live_environment(approval, runner)) if live else digest([]),
                         stdin_open=live and runner, working_dir='/scratch' if live and runner else '')


@dataclass(frozen=True)
class TargetSnapshot:
    attempt: AttemptReference
    runtime_binding_uuid: str
    generation_uuid: str
    daemon: DaemonIdentity
    container_id: str
    image_id: str
    started_at: str
    restart_count: int
    running: bool
    paused: bool
    restarting: bool
    dead: bool
    endpoints: tuple[Endpoint, ...]
    config: RuntimeConfig
    policy_digest: str

    def __post_init__(self):
        require(type(self.attempt) is AttemptReference and type(self.daemon) is DaemonIdentity and
                type(self.config) is RuntimeConfig, "snapshot_invalid")
        self.attempt.__post_init__()
        self.daemon.__post_init__()
        self.config.__post_init__()
        uid(self.runtime_binding_uuid)
        uid(self.generation_uuid)
        full_id(self.container_id)
        full_id(self.image_id, True)
        full_id(self.policy_digest)
        docker_time(self.started_at)
        require(type(self.restart_count) is int and 0 <= self.restart_count < 2**31, "restart_count_invalid")
        require(all(type(v) is bool for v in (self.running, self.paused, self.restarting, self.dead)), "target_state_invalid")
        require(type(self.endpoints) is tuple and 1 <= len(self.endpoints) <= 4, "endpoint_list_invalid")
        for endpoint in self.endpoints:
            require(type(endpoint) is Endpoint, "endpoint_list_invalid")
            endpoint.__post_init__()

    @classmethod
    def from_dict(cls, body):
        config = {**body["config"], "cap_drop": tuple(body["config"]["cap_drop"]), "cap_add": tuple(body["config"]["cap_add"])}
        return cls(**{**body, "attempt": AttemptReference(**body["attempt"]), "daemon": DaemonIdentity(**body["daemon"]),
                      "endpoints": tuple(Endpoint(**e) for e in body["endpoints"]), "config": RuntimeConfig(**config)})


@dataclass(frozen=True)
class IdentityObservation:
    receipt_uuid: str
    context_uuid: str
    scope: str
    observed_at: float
    phase: Phase
    target: TargetSnapshot

    def __post_init__(self):
        common(self)
        require(type(self.phase) is Phase and type(self.target) is TargetSnapshot, "identity_observation_invalid")
        self.target.__post_init__()


@dataclass(frozen=True)
class NetworkEvidence:
    receipt_uuid: str
    context_uuid: str
    scope: str
    observed_at: float
    phase: Phase
    daemon: DaemonIdentity
    network_profile_digest: str
    internal: bool
    driver: str
    endpoints: tuple[Endpoint, ...]

    def __post_init__(self):
        common(self)
        require(type(self.phase) is Phase, "network_phase_invalid")
        require(type(self.daemon) is DaemonIdentity and type(self.internal) is bool and self.driver in ("bridge", "host"), "network_evidence_invalid")
        self.daemon.__post_init__()
        full_id(self.network_profile_digest)
        require(type(self.endpoints) is tuple and len(self.endpoints) <= 8, "network_evidence_invalid")
        for endpoint in self.endpoints:
            require(type(endpoint) is Endpoint, "network_evidence_invalid")
            endpoint.__post_init__()


@dataclass(frozen=True)
class EgressEvidence:
    receipt_uuid: str
    context_uuid: str
    scope: str
    observed_at: float
    phase: Phase
    target_digest: str
    runner_id: str | None
    daemon: DaemonIdentity
    network_profile_digest: str
    enforcement_reference: str
    rules_digest: str
    validation_digest: str
    default_deny: bool
    only_target_8080: bool
    denies_host_metadata_platform: bool
    anti_spoofing: bool

    def __post_init__(self):
        common(self)
        require(type(self.phase) is Phase, "egress_phase_invalid")
        full_id(self.target_digest)
        if self.runner_id is not None:
            full_id(self.runner_id)
        require(type(self.daemon) is DaemonIdentity, "egress_evidence_invalid")
        self.daemon.__post_init__()
        for value in (self.network_profile_digest, self.rules_digest, self.validation_digest):
            full_id(value)
        atom(self.enforcement_reference, "egress:")
        require(all(type(v) is bool for v in (self.default_deny, self.only_target_8080,
                self.denies_host_metadata_platform, self.anti_spoofing)), "egress_evidence_invalid")


@dataclass(frozen=True)
class RuntimeEnrollment:
    enrollment_uuid: str
    provisioning_uuid: str
    approval_uuid: str
    approval_digest: str
    scope: str
    target: TargetSnapshot
    creation_receipt_uuid: str
    creation_receipt_digest: str
    policy_digest: str
    verification_mode: str = "offline_runtime_chain_v1"

    def __post_init__(self):
        for value in (self.enrollment_uuid, self.provisioning_uuid, self.approval_uuid, self.creation_receipt_uuid):
            uid(value)
        for value in (self.approval_digest, self.creation_receipt_digest, self.policy_digest):
            full_id(value)
        scope(self.scope)
        require(type(self.target) is TargetSnapshot and self.verification_mode in
                ('offline_runtime_chain_v1', 'live_runtime_chain_v2'), "runtime_enrollment_invalid")
        self.target.__post_init__()

    @classmethod
    def from_dict(cls, body):
        return cls(**{**body, "target": TargetSnapshot.from_dict(body["target"])})


@dataclass(frozen=True)
class OrdinaryMetadata:
    attempt: AttemptReference
    check_run_id: int | None
    execution_uuid: str | None
    result: str
    observed_at: float | None
    claimed_binding_uuid: str | None = None
    criteria_scope: str = "full_task_legacy"

    def __post_init__(self):
        require(type(self.attempt) is AttemptReference, "ordinary_metadata_invalid")
        self.attempt.__post_init__()
        require(self.check_run_id is None or type(self.check_run_id) is int and self.check_run_id > 0, "ordinary_reference_invalid")
        for value in (self.execution_uuid, self.claimed_binding_uuid):
            if value is not None:
                uid(value)
        require(self.result in ("passed", "failed", "unknown") and self.criteria_scope == "full_task_legacy", "ordinary_metadata_invalid")
        if self.observed_at is not None:
            stamp(self.observed_at)


@dataclass(frozen=True)
class RunRequest:
    request_uuid: str
    enrollment_uuid: str
    attempt: AttemptReference
    sample_slot: str
    ordinary: OrdinaryMetadata | None = None

    def __post_init__(self):
        for value in (self.request_uuid, self.enrollment_uuid, self.sample_slot):
            uid(value)
        require(type(self.attempt) is AttemptReference, "run_request_invalid")
        self.attempt.__post_init__()
        if self.ordinary is not None:
            require(type(self.ordinary) is OrdinaryMetadata and self.ordinary.attempt == self.attempt, "ordinary_owner_mismatch")
            self.ordinary.__post_init__()


@dataclass(frozen=True)
class ProbeResponse:
    receipt_uuid: str
    context_uuid: str
    scope: str
    observed_at: float
    runner_id: str
    runner_image_id: str
    checker_source_digest: str
    target_digest: str
    policy_digest: str
    status: int
    body: bytes
    complete: bool = True
    transport: str = "none"

    def __post_init__(self):
        common(self)
        full_id(self.runner_id)
        full_id(self.runner_image_id, True)
        for value in (self.checker_source_digest, self.target_digest, self.policy_digest):
            full_id(value)
        require(type(self.status) is int and 100 <= self.status <= 599 and type(self.body) is bytes
                and len(self.body) <= 1025 and type(self.complete) is bool, "probe_protocol_invalid")
        require(self.transport in ("none", "timeout", "uncertain", "refused"), "probe_protocol_invalid")


@dataclass(frozen=True)
class CleanupConfirmation:
    receipt_uuid: str
    context_uuid: str
    scope: str
    observed_at: float
    resource: Resource
    daemon: DaemonIdentity
    container_id: str
    ownership_digest: str
    removal_evidence_digest: str
    outcome: str

    def __post_init__(self):
        common(self)
        require(type(self.resource) is Resource and type(self.daemon) is DaemonIdentity,
                "cleanup_contract_invalid")
        self.daemon.__post_init__()
        for value in (self.container_id, self.ownership_digest, self.removal_evidence_digest):
            full_id(value)
        require(self.outcome in ("removed_confirmed", "unknown"), "cleanup_outcome_invalid")


@dataclass(frozen=True)
class RunnerObservation:
    receipt_uuid: str
    context_uuid: str
    scope: str
    observed_at: float
    daemon: DaemonIdentity
    container_id: str
    image_id: str
    config: RuntimeConfig
    state: str
    started_at: str | None
    restart_count: int
    endpoint: Endpoint | None
    paused: bool = False
    restarting: bool = False
    dead: bool = False
    exit_code: int | None = None

    def __post_init__(self):
        common(self)
        require(type(self.daemon) is DaemonIdentity and type(self.config) is RuntimeConfig, "runner_observation_invalid")
        self.daemon.__post_init__()
        self.config.__post_init__()
        full_id(self.container_id)
        full_id(self.image_id, True)
        require(self.state in ("created", "running", "exited") and type(self.restart_count) is int
                and 0 <= self.restart_count < 2**31, "runner_state_invalid")
        require(all(type(v) is bool for v in (self.paused, self.restarting, self.dead)), "runner_state_invalid")
        require(self.exit_code is None or type(self.exit_code) is int and 0 <= self.exit_code <= 255, 'runner_exit_invalid')
        if self.started_at is not None:
            docker_time(self.started_at)
        if self.endpoint is not None:
            require(type(self.endpoint) is Endpoint, "runner_endpoint_invalid")
            self.endpoint.__post_init__()


@dataclass(frozen=True)
class StartPermit:
    permit_uuid: str
    run_uuid: str
    enrollment_digest: str
    runner_id: str
    control_epoch: int
    deadline: float

    def __post_init__(self):
        uid(self.permit_uuid)
        uid(self.run_uuid)
        full_id(self.enrollment_digest)
        full_id(self.runner_id)
        require(type(self.control_epoch) is int and self.control_epoch >= 0, "start_permit_invalid")
        stamp(self.deadline)


@dataclass(frozen=True)
class EgressValidation:
    receipt_uuid: str
    context_uuid: str
    scope: str
    observed_at: float
    phase: Phase
    enforcement_receipt_digest: str
    matrix_digest: str
    passed_cases: tuple[str, ...]

    def __post_init__(self):
        from .profiles import EGRESS_CASES
        common(self)
        require(type(self.phase) is Phase, "validation_phase_invalid")
        full_id(self.enforcement_receipt_digest)
        full_id(self.matrix_digest)
        require(type(self.passed_cases) is tuple and len(self.passed_cases) <= len(EGRESS_CASES)
                and all(case in EGRESS_CASES + LIVE_PREFLIGHT_CASES for case in self.passed_cases), "validation_cases_invalid")
