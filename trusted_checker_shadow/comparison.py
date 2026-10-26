"""Offline comparison never authenticates or mutates supplied ordinary evidence."""

from dataclasses import dataclass

from .contracts import OrdinaryEvidence, Verdict
from .policy import CRITERIA_SCOPE


@dataclass(frozen=True)
class Comparison:
    status: str
    reason: str


def compare(ordinary, target, result, observed_from, observed_until):
    def cannot(reason):
        return Comparison("incomparable", reason)

    if type(ordinary) is not OrdinaryEvidence or ordinary.check_run_id is None:
        return cannot("ordinary_check_missing")
    if (ordinary.attempt_id, ordinary.owner_id, ordinary.task) != (target.attempt_id, target.owner_id, target.task):
        return cannot("ordinary_identity_mismatch")
    if result == Verdict.UNKNOWN or ordinary.result == Verdict.UNKNOWN:
        return cannot("outcome_unknown")
    if ordinary.criteria_scope != CRITERIA_SCOPE:
        return cannot("criteria_scope_differs")
    if ordinary.correlation_quality != "same_generation_proven":
        return cannot("correlation_unproven")
    if (ordinary.runtime_binding_uuid, ordinary.generation) != (target.runtime_binding_uuid, target.generation):
        return cannot("generation_differs")
    if (ordinary.observed_from is None or observed_from is None or observed_until is None or
            max(ordinary.observed_from, observed_from) > min(ordinary.observed_until, observed_until)):
        return cannot("observation_windows_differ")
    return Comparison("agrees" if ordinary.result == result else "differs", "scoped_observations_only")
