from django.core.exceptions import ValidationError
from django.db import transaction

from achievements.models import AchievementDefinition, UserAchievement
from .evaluators import evaluate
from .grants import current_metric_problem, digest, flag_disputed, grant, lock_user


def reconcile(*, user_id, definition, apply=False, expected_rule_version=1):
    if definition.rule_version != expected_rule_version:
        raise ValidationError("Версия правила изменилась.")
    if apply:
        with transaction.atomic():
            lock_user(user_id)
            from traineediary.models import TraineeJourney
            TraineeJourney.objects.select_for_update().filter(user_id=user_id).first()
            current = AchievementDefinition.objects.select_for_update().get(pk=definition.pk)
            return _run(user_id, current, True, expected_rule_version)
    return _run(user_id, definition, False, expected_rule_version)


def _run(user_id, definition, apply, version):
    if definition.rule_version != version:
        raise ValidationError("Версия правила изменилась.")
    evaluation = evaluate(user_id=user_id, definition=definition)
    report = {"user_id": user_id, "definition": definition.code, **evaluation.report()}
    entitlement = UserAchievement.objects.select_related("active_tier").filter(user_id=user_id, definition=definition).first()
    problem = current_metric_problem(entitlement)
    report["evidence_disputed"] = bool(problem or (entitlement and entitlement.evidence_disputed))
    if apply and problem:
        flag_disputed(user_id=user_id, metric_id=problem["metric_id"], definition_id=definition.pk,
                      source_id=f"reconciliation:{digest(problem)}")
    if evaluation.status == "eligible":
        tier = definition.tiers.get(code=evaluation.tier_code)
        if entitlement and entitlement.auto_grant_blocked:
            report["action"] = "suppressed"
        elif entitlement and entitlement.active_tier and entitlement.active_tier.rank >= tier.rank:
            report["action"] = "no_op"
        else:
            report["action"] = "upgrade" if entitlement and entitlement.active_tier_id else "grant"
        if apply:
            _, report["action"], event = grant(user_id=user_id, definition_id=definition.pk,
                tier_code=evaluation.tier_code, evidence=evaluation.evidence, occurred_at=evaluation.occurred_at,
                source_type="reconciliation", source_ref=digest(evaluation.report()), rule_version=version,
                operation_id=f"reconcile:{digest(evaluation.report())}")
            report["event_id"] = event.pk if event else None
    report["applied"] = apply
    return report
