"""Durable source record in the owning transaction; best-effort wake after commit.

The inline wake needs no running broker. A crashed wake leaves a retryable record;
the management worker drains it, including weeks which mature later.
"""
import logging
import uuid

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import models, transaction
from django.utils import timezone

from achievements.models import AchievementSourceEvent
from .evaluators import at_date, evaluate
from .grants import current_metric_problem, digest, flag_disputed, grant, lock_user

logger = logging.getLogger(__name__)
PROVIDERS = {
    "roadmap_confirmation": ("training_program",),
    "sandbox_completion": ("sandbox_program", "sandbox_first_success", "sandbox_five_successes"),
    "sandbox_technical": ("sandbox_first_success", "sandbox_five_successes"),
    "weekly_metric": ("review_quality", "independent_speed"),
    "stage_transition": ("independent_engineer", "review_quality", "independent_speed"),
    "probation_completion": ("probation_new_hire",),
}


@transaction.atomic
def publish(*, provider, external_id, user_id, context, payload, available_at=None):
    if provider not in PROVIDERS:
        raise ValidationError("Неизвестный provider.")
    event, created = AchievementSourceEvent.objects.get_or_create(
        provider=provider, external_id=str(external_id), defaults=dict(
            user_id=user_id, context=context, payload=payload, available_at=available_at))
    if not created and (event.user_id != user_id or event.context != context or event.payload != payload):
        raise ValidationError("Повторный ID источника с другим содержимым.")
    if event.status != "processed":
        transaction.on_commit(lambda: wake(event.pk))
    return event


def wake(event_id):
    try:
        process_source_event(event_id)
    except Exception:
        # The owning transaction has committed. Keep the durable failure for retry.
        logger.exception("Achievement source %s awaits retry", event_id)


def metric_values(metric):
    return dict(metric_id=metric.pk, journey_id=metric.journey_id,
                week_number=metric.week_number,
                week_start_date=metric.week_start_date.isoformat() if metric.week_start_date else None,
                quality_percent=metric.quality_percent,
                speed_hours=str(metric.speed_hours) if metric.speed_hours is not None else None)


@transaction.atomic
def save_metric_with_event(*, metric, actor):
    from traineediary.models import TraineeJourney, WeeklyMetric
    from datetime import timedelta
    if not actor.is_authenticated or not actor.is_staff:
        raise PermissionDenied
    lock = TraineeJourney.objects.select_for_update().get(pk=metric.journey_id)
    previous = WeeklyMetric.objects.filter(pk=metric.pk).first() if metric.pk else None
    before = metric_values(previous) if previous else None
    metric.save()
    after = metric_values(metric)
    if before == after:
        return metric
    ready_at = at_date(metric.week_start_date + timedelta(days=7)) if metric.week_start_date else None
    # Corrections must flag already issued proofs immediately, even if period moves forward.
    if before:
        ready_at = None
    publish(provider="weekly_metric", external_id=f"{metric.pk}:{uuid.uuid4()}", user_id=lock.user_id,
            context={"journey_id": lock.pk}, payload={"values": after, "previous_values": before, "actor_id": actor.pk},
            available_at=ready_at)
    return metric


@transaction.atomic
def _process(event_id):
    from achievements.models import AchievementDefinition
    from traineediary.models import TraineeJourney, WeeklyMetric
    raw = AchievementSourceEvent.objects.get(pk=event_id)
    lock_user(raw.user_id)
    event = AchievementSourceEvent.objects.select_for_update().get(pk=event_id)
    if event.status == "processed":
        return event.result
    if event.available_at and event.available_at > timezone.now():
        return [{"status": "pending", "reason": "period_not_finished"}]
    if event.provider not in PROVIDERS or event.schema_version != 1:
        raise ValidationError("Неизвестный provider/schema.")
    journey_id = event.context.get("journey_id")
    # Serialize evaluation with metric/stage writers. Read after their commit,
    # so a superseded 96% cannot race a correction to 80% into a gold grant.
    TraineeJourney.objects.select_for_update().filter(user_id=event.user_id).first()
    if journey_id is not None and not TraineeJourney.objects.filter(pk=journey_id, user_id=event.user_id).exists():
        results = [{"status": "unknown", "reason": "source_adaptation_no_longer_available"}]
    else:
        if event.provider == "weekly_metric":
            metric_id = event.payload["values"]["metric_id"]
            current = WeeklyMetric.objects.filter(pk=metric_id, journey__user_id=event.user_id).first()
            if current is None:
                flag_disputed(user_id=event.user_id, metric_id=metric_id, source_id=event.pk)
            else:
                # Only a changed proof, not a new week or edited comment, is disputed.
                from achievements.models import UserAchievement
                for entitlement in UserAchievement.objects.filter(user_id=event.user_id, active_tier__isnull=False):
                    proof = entitlement.events.filter(action__in=["grant", "upgrade"]).last()
                    if proof and proof.evidence.get("metric_id") == metric_id:
                        if current_metric_problem(entitlement):
                            flag_disputed(user_id=event.user_id, metric_id=metric_id, source_id=event.pk,
                                          definition_id=entitlement.definition_id)
        if event.provider == "roadmap_confirmation" and event.payload.get("action") == "revoked":
            flag_disputed(user_id=event.user_id, confirmation_revoked=True, source_id=event.pk)
        results = []
        definitions = list(AchievementDefinition.objects.filter(evaluator_key__in=PROVIDERS[event.provider]))
        if not definitions:
            raise ValidationError("Каталог evaluator отсутствует; источник ожидает повторной обработки.")
        for definition in definitions:
            result = evaluate(user_id=event.user_id, definition=definition)
            report = {"definition": definition.code, **result.report()}
            if result.status == "eligible":
                _, outcome, earned_event = grant(user_id=event.user_id, definition_id=definition.pk,
                    tier_code=result.tier_code, evidence=result.evidence, occurred_at=result.occurred_at,
                    source_type=event.provider, source_ref=str(event.pk), rule_version=result.rule_version,
                    operation_id=f"source:{event.pk}:{digest(result.report())}")
                report["action"] = outcome
                report["event_id"] = earned_event.pk if earned_event else None
            results.append(report)
    event.status = "processed"
    if event.provider == "weekly_metric":
        from datetime import timedelta
        current = WeeklyMetric.objects.filter(pk=event.payload["values"]["metric_id"], journey__user_id=event.user_id).first()
        if current and current.week_start_date:
            ready = at_date(current.week_start_date + timedelta(days=7))
            if ready > timezone.now():
                event.status = "pending"
                event.available_at = ready
    event.attempts += 1
    event.error = ""
    event.result = results
    event.processed_at = timezone.now() if event.status == "processed" else None
    event.save(update_fields=["status", "attempts", "error", "result", "processed_at", "available_at"])
    return results


def process_source_event(event_id):
    try:
        return _process(event_id)
    except Exception as error:
        AchievementSourceEvent.objects.filter(pk=event_id).exclude(status="processed").update(
            status="error", attempts=models.F("attempts") + 1, error=f"{type(error).__name__}: {error}"[:2000])
        raise
