"""Explicit OFFLINE fixture authority, never real-container adoption/attestation."""

from dataclasses import asdict, dataclass
from uuid import NAMESPACE_URL, uuid5

from .contracts import (CandidateMetadata, CreationProvenance, TargetIdentity,
                        VerifiedEnrollment, atom, require, uuid_value)
from .policy import POLICY, digest


@dataclass(frozen=True)
class ProvenanceFixture:
    fixture_uuid: str
    target: TargetIdentity
    provenance: CreationProvenance
    operator_id: str

    def __post_init__(self):
        uuid_value(self.fixture_uuid)
        require(type(self.target) is TargetIdentity and type(self.provenance) is CreationProvenance,
                "explicit_provenance_fixture_required")
        self.target.__post_init__()
        self.provenance.__post_init__()
        atom(self.operator_id, "operator-")


class FakeTrustedAuthority:
    def __init__(self, authority_id, fixtures):
        atom(authority_id, "fake-")
        self.authority_id = authority_id
        self._fixtures = {}
        self._enrollments = {}
        for fixture in fixtures:
            require(type(fixture) is ProvenanceFixture, "explicit_provenance_fixture_required")
            fixture.__post_init__()
            require(fixture.fixture_uuid not in self._fixtures, "duplicate_fixture")
            self._fixtures[fixture.fixture_uuid] = fixture
            enrollment = self._make(fixture)
            self._enrollments[enrollment.enrollment_uuid] = enrollment

    def _make(self, fixture):
        # Stable across authority restarts with the SAME explicit trusted fixture.
        identifier = str(uuid5(NAMESPACE_URL, digest({"authority": self.authority_id,
                               "fixture": asdict(fixture), "policy": POLICY.digest})))
        return VerifiedEnrollment(identifier, self.authority_id, fixture.fixture_uuid,
                                  fixture.target, fixture.provenance, POLICY.policy_id,
                                  POLICY.version, POLICY.digest, fixture.operator_id)

    def enroll(self, candidate, *, fixture_uuid, operator_id):
        require(type(candidate) is CandidateMetadata, "candidate_required")
        candidate.__post_init__()
        fixture = self._fixtures.get(fixture_uuid)
        require(fixture is not None and candidate.target == fixture.target and
                operator_id == fixture.operator_id, "provenance_fixture_mismatch")
        return self._make(fixture)

    def verify(self, enrollment, *, operator_id):
        require(type(enrollment) is VerifiedEnrollment, "verified_enrollment_required")
        enrollment.__post_init__()
        require(self._enrollments.get(enrollment.enrollment_uuid) == enrollment,
                "enrollment_not_authorized")
        require(enrollment.operator_id == operator_id, "operator_not_authorized")
        return enrollment

    def authorize_operator(self, operator_id):
        require(any(f.operator_id == operator_id for f in self._fixtures.values()), "operator_not_authorized")
