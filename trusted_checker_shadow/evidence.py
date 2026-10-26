"""Only this explicit DTO leaves local state. No arbitrary payload or exception text."""

from dataclasses import asdict, dataclass
import json

from .comparison import Comparison
from .contracts import (CreationProvenance, OrdinaryEvidence, ProbeResult,
                        RuntimeObservation, TargetIdentity, require)
from .policy import CRITERIA_SCOPE, PeerPolicy


@dataclass(frozen=True)
class AuditEvent:
    sequence: int
    code: str
    occurred_at: float


@dataclass(frozen=True)
class OperatorReport:
    shadow_run_uuid: str
    execution_uuid: str
    canonical_idempotency_key: str
    sample_slot: str
    enrollment_uuid: str
    authority_id: str
    operator_id: str
    target: TargetIdentity
    provenance: CreationProvenance
    policy: PeerPolicy
    policy_digest: str
    ordinary: OrdinaryEvidence | None
    lifecycle: str
    verdict: ProbeResult | None
    cleanup_state: str
    unresolved: bool
    created_at: float
    started_at: float | None
    finished_at: float | None
    observed_from: float | None
    observed_until: float | None
    deadline: float
    comparison: Comparison
    diagnostics: tuple[AuditEvent, ...]
    audit_event_count: int
    schema_version: int = 1
    source: str = "operator"
    execution_mode: str = "offline_fake_only"
    enrollment_verification: str = "offline_fixture_only"
    criteria_scope: str = CRITERIA_SCOPE
    local_access: str = "unverified"
    application_authenticity: str = "unproven"
    persistence: str = "unverified"
    observed_before: RuntimeObservation | None = None
    observed_after: RuntimeObservation | None = None

    def to_dict(self):
        result = asdict(self)
        require(len(json.dumps(result, allow_nan=False).encode()) <= 16384, "report_limit_exceeded")
        return result
