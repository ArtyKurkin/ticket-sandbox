"""SELECT-only evaluator registry; no executable catalog expressions."""
from django.core.exceptions import ValidationError
from achievements.services.catalog import validate_definition, validate_tier
from traineediary.models import EntryType, TraineeJourney
from .base import Evaluation, at_date, unknown
from .training import training
from .sandbox import sandbox
from .weekly import weekly
from .probation import probation
from .independent import independent

REGISTRY = {
    "training_program": training,
    "sandbox_program": sandbox,
    "sandbox_first_five_clean_answers": sandbox,
    "sandbox_first_success": sandbox,
    "sandbox_five_successes": sandbox,
    "review_quality": weekly,
    "independent_speed": weekly,
    "probation_new_hire": probation,
    "independent_engineer": independent,
}
PENDING_EVIDENCE = {
    "sandbox_first_five_clean_answers": ("immutable ordered submissions", "version-linked review events", "coverage from first submission"),
    "review_quality_streak": ("three consecutive finalized complete weeks", "single WITH_REVIEW visit", "measurement coverage"),
    "clean_week": ("finalized complete work week WITH_REVIEW", "100% quality", "verified coverage of workdays and assessments"),
}


def evaluate(*, user_id, definition, evidence_cache=None):
    try:
        validate_definition(definition)
        tiers = list(definition.tiers.all())
        for tier in tiers:
            validate_tier(tier)
        from achievements.services.catalog import SCHEMAS
        if {t.code for t in tiers} != {t[0] for t in SCHEMAS[definition.evaluator_key]["tiers"]}:
            return unknown("invalid_catalog", "complete validated tier schema")
    except ValidationError:
        return unknown("invalid_catalog", "validated rule schema/version")
    if not definition.active:
        return Evaluation("not_applicable", reason="inactive_definition")
    journey = TraineeJourney.objects.select_related("current_stage", "completed_by").filter(user_id=user_id).first()
    if definition.applicability == "new_hire":
        if journey is None:
            return unknown("adaptation_context_missing", "NEW_HIRE adaptation")
        if journey.entry_type != EntryType.NEW_HIRE:
            return Evaluation("not_applicable", reason="new_hire_only")
    if definition.evaluator_key not in REGISTRY:
        return unknown("source_not_ready", *PENDING_EVIDENCE.get(definition.evaluator_key, ("complete source history",)))
    function = REGISTRY[definition.evaluator_key]
    if function == sandbox:
        return sandbox(user_id, tiers, definition, evidence_cache)
    if journey is None:
        return unknown("adaptation_context_missing", "adaptation and stage history")
    if function == weekly:
        return weekly(journey, tiers, definition)
    return function(journey, tiers)
