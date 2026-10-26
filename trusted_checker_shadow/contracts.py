"""Closed, bounded DTOs. Python callers/authority/state are trusted process code.

Frozen dataclasses alone are NOT authority. Enrollment is checked against the
explicit fake authority's provenance fixture on every submission.
"""

from dataclasses import asdict, dataclass
from datetime import datetime
from enum import StrEnum
import ipaddress
import math
import re
from uuid import UUID

from .policy import CRITERIA_SCOPE, POLICY, TASK


class Rejected(ValueError):
    """Only constant codes cross the diagnostic boundary."""


def require(condition, code):
    if not condition:
        raise Rejected(code)


def uuid_value(value):
    try:
        require(type(value) is str and str(UUID(value)) == value, "uuid_invalid")
    except (ValueError, TypeError, AttributeError):
        raise Rejected("uuid_invalid") from None


def identity(value, *, image=False):
    require(type(value) is str and re.fullmatch(
        r"sha256:[0-9a-f]{64}" if image else r"[0-9a-f]{64}", value) is not None,
        "image_invalid" if image else "identity_invalid")


def positive(value):
    require(type(value) is int and 0 < value <= 2**63 - 1, "reference_invalid")


def instant(value):
    require(type(value) in (int, float) and math.isfinite(value) and value > 0,
            "timestamp_invalid")


def atom(value, prefix):
    require(type(value) is str and re.fullmatch(prefix + r"[a-z0-9][a-z0-9-]{0,47}", value)
            is not None, "offline_identity_invalid")


class Verdict(StrEnum):
    PASSED = "passed"
    FAILED = "failed"
    UNKNOWN = "unknown"


class Reason(StrEnum):
    HTTP_OBSERVED = "external_ipv4_http_observed"
    STATUS = "unexpected_http_status"
    BODY = "unexpected_http_body"
    REDIRECT = "redirect_rejected"
    OVERSIZED = "response_too_large"
    TRANSPORT = "transport_uncertain"
    TIMEOUT = "transport_timeout"
    PROTOCOL = "response_protocol_invalid"
    IDENTITY = "target_identity_uncertain"
    INFRASTRUCTURE = "infrastructure_uncertain"
    DEADLINE = "run_deadline_exceeded"
    KILLED = "kill_switch"
    ISSUE = "issue_outcome_unknown"
    REPLAY = "execution_receipt_mismatch"


TECHNICAL_FAILURES = {Reason.STATUS, Reason.BODY, Reason.REDIRECT, Reason.OVERSIZED}


@dataclass(frozen=True)
class TargetIdentity:
    sandbox_instance: str
    attempt_id: int
    owner_id: int
    task: str
    daemon_id: str
    container_id: str
    image_id: str
    runtime_binding_uuid: str
    generation: str
    started_at: str
    restart_count: int
    network_id: str
    endpoint_id: str
    ipv4: str
    scope: str

    def __post_init__(self):
        atom(self.sandbox_instance, "fake-")
        atom(self.daemon_id, "fake-")
        atom(self.scope, "offline-")
        positive(self.attempt_id)
        positive(self.owner_id)
        require(self.task == TASK and type(self.task) is str, "task_not_allowed")
        for value in (self.container_id, self.network_id, self.endpoint_id):
            identity(value)
        identity(self.image_id, image=True)
        uuid_value(self.runtime_binding_uuid)
        uuid_value(self.generation)
        require(type(self.restart_count) is int and 0 <= self.restart_count < 2**31,
                "restart_count_invalid")
        require(type(self.started_at) is str and re.fullmatch(
            r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,9})?(?:Z|[+-]\d{2}:\d{2})",
            self.started_at) is not None, "start_time_invalid")
        try:
            stamp = datetime.fromisoformat(self.started_at)
            require(stamp.utcoffset() is not None and stamp.year >= 2020,
                    "start_time_invalid")
        except (TypeError, ValueError):
            raise Rejected("start_time_invalid") from None
        try:
            address = ipaddress.IPv4Address(self.ipv4)
        except (ValueError, TypeError):
            raise Rejected("ipv4_invalid") from None
        require(type(self.ipv4) is str and str(address) == self.ipv4 and any(
            address in ipaddress.IPv4Network(net)
            for net in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16")), "ipv4_invalid")


@dataclass(frozen=True)
class CandidateMetadata:
    target: TargetIdentity
    source: str

    def __post_init__(self):
        require(type(self.target) is TargetIdentity, "candidate_invalid")
        require(self.source in ("sandbox_metadata", "labels", "inspect", "offline_fixture"),
                "candidate_source_invalid")


@dataclass(frozen=True)
class CreationProvenance:
    reference: str
    digest: str

    def __post_init__(self):
        require(type(self.reference) is str and re.fullmatch(
            r"fixture:[a-z0-9][a-z0-9-]{0,47}", self.reference) is not None,
            "fake_provenance_required")
        identity(self.digest)


@dataclass(frozen=True)
class VerifiedEnrollment:
    enrollment_uuid: str
    authority_id: str
    fixture_uuid: str
    target: TargetIdentity
    provenance: CreationProvenance
    policy_id: str
    policy_version: int
    policy_digest: str
    operator_id: str
    verification_mode: str = "offline_fixture_only"
    schema_version: int = 1

    def __post_init__(self):
        uuid_value(self.enrollment_uuid)
        uuid_value(self.fixture_uuid)
        atom(self.authority_id, "fake-")
        atom(self.operator_id, "operator-")
        require(type(self.target) is TargetIdentity and
                type(self.provenance) is CreationProvenance, "enrollment_invalid")
        self.target.__post_init__()
        self.provenance.__post_init__()
        require((self.policy_id, self.policy_version, self.policy_digest) ==
                (POLICY.policy_id, POLICY.version, POLICY.digest) and
                type(self.policy_version) is int, "policy_mismatch")
        require(self.verification_mode == "offline_fixture_only" and
                type(self.schema_version) is int and self.schema_version == 1,
                "enrollment_schema_invalid")


@dataclass(frozen=True)
class RuntimeObservation:
    target: TargetIdentity
    running: bool = True
    paused: bool = False
    restarting: bool = False
    dead: bool = False

    def __post_init__(self):
        require(type(self.target) is TargetIdentity, "runtime_observation_invalid")
        self.target.__post_init__()
        require(all(type(value) is bool for value in
                    (self.running, self.paused, self.restarting, self.dead)), "runtime_observation_invalid")

    def matches(self, target):
        return (type(self.target) is TargetIdentity and self.target == target and
                self.running is True and self.paused is False and
                self.restarting is False and self.dead is False)


@dataclass(frozen=True)
class OrdinaryEvidence:
    attempt_id: int
    owner_id: int
    task: str = TASK
    check_run_id: int | None = None
    technical_execution_uuid: str | None = None
    result: Verdict = Verdict.UNKNOWN
    criteria_scope: str = "full_task_legacy"
    correlation_quality: str = "same_attempt_temporal"
    runtime_binding_uuid: str | None = None
    generation: str | None = None
    observed_from: float | None = None
    observed_until: float | None = None

    def __post_init__(self):
        positive(self.attempt_id)
        positive(self.owner_id)
        require(self.task == TASK, "task_not_allowed")
        if self.check_run_id is not None:
            positive(self.check_run_id)
        for value in (self.technical_execution_uuid, self.runtime_binding_uuid, self.generation):
            if value is not None:
                uuid_value(value)
        require(type(self.result) is Verdict, "ordinary_result_invalid")
        require(self.criteria_scope in ("full_task_legacy", CRITERIA_SCOPE), "criteria_scope_invalid")
        require(self.correlation_quality in ("same_attempt_temporal", "same_generation_proven", "unpaired"),
                "correlation_quality_invalid")
        require((self.observed_from is None) == (self.observed_until is None), "window_invalid")
        if self.observed_from is not None:
            instant(self.observed_from)
            instant(self.observed_until)
            require(self.observed_from <= self.observed_until, "window_invalid")


@dataclass(frozen=True)
class OperatorRequest:
    request_uuid: str
    enrollment_uuid: str
    attempt_id: int
    owner_id: int
    scope: str
    sample_slot: str
    deadline: float
    ordinary: OrdinaryEvidence | None = None
    task: str = TASK
    policy_id: str = POLICY.policy_id
    policy_version: int = POLICY.version
    policy_digest: str = POLICY.digest
    schema_version: int = 1

    def __post_init__(self):
        for value in (self.request_uuid, self.enrollment_uuid, self.sample_slot):
            uuid_value(value)
        positive(self.attempt_id)
        positive(self.owner_id)
        atom(self.scope, "offline-")
        instant(self.deadline)
        require(self.task == TASK, "task_not_allowed")
        require(self.policy_id == POLICY.policy_id and type(self.policy_version) is int and
                self.policy_version == POLICY.version and self.policy_digest == POLICY.digest,
                "policy_mismatch")
        require(type(self.schema_version) is int and self.schema_version == 1, "schema_invalid")
        if self.ordinary is not None:
            require(type(self.ordinary) is OrdinaryEvidence, "ordinary_schema_invalid")
            self.ordinary.__post_init__()
            require((self.ordinary.attempt_id, self.ordinary.owner_id, self.ordinary.task) ==
                    (self.attempt_id, self.owner_id, self.task), "ordinary_identity_mismatch")

    def payload(self):
        return {key: value for key, value in asdict(self).items() if key != "request_uuid"}


@dataclass(frozen=True)
class ProbeResult:
    result: Verdict
    reason: Reason
    http_status: int | None = None
    response_bytes: int | None = None
    response_digest: str | None = None

    def __post_init__(self):
        require(type(self.result) is Verdict and type(self.reason) is Reason, "result_schema_invalid")
        expected = (Verdict.PASSED if self.reason == Reason.HTTP_OBSERVED else
                    Verdict.FAILED if self.reason in TECHNICAL_FAILURES else Verdict.UNKNOWN)
        require(self.result == expected, "result_reason_mismatch")
        if self.http_status is not None:
            require(type(self.http_status) is int and 100 <= self.http_status <= 599, "status_invalid")
        if self.response_bytes is not None:
            require(type(self.response_bytes) is int and 0 <= self.response_bytes <= 1025,
                    "response_length_invalid")
        if self.response_digest is not None:
            identity(self.response_digest)
