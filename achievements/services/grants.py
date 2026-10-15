"""All projection mutations serialize on an existing user, including first grant."""
import hashlib
import json

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from achievements.models import AchievementDefinition, AchievementEvent, AchievementTier, UserAchievement, AchievementOperation
from .catalog import validate_definition, validate_tier


class GrantConflict(Exception):
    pass


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


def staff_reason(actor, reason):
    if actor is None or not actor.is_authenticated or not actor.is_staff:
        raise PermissionDenied
    if not isinstance(reason, str) or not reason.strip():
        raise ValidationError("Обязательна причина ручного действия.")


def lock_user(user_id):
    # NO KEY UPDATE serializes grants while allowing owning writers to insert
    # source rows with a user FK. FOR UPDATE would deadlock with a journey lock.
    return get_user_model().objects.select_for_update(no_key=True).get(pk=user_id)


def operation_key(user_id, definition_id, action, operation_id):
    if not isinstance(operation_id, str) or not operation_id.strip() or len(operation_id) > 150:
        raise ValidationError("Нужен operation_id до 150 символов.")
    return digest([user_id, definition_id, action, operation_id])


def repeated(key, request_digest):
    receipt = AchievementOperation.objects.select_related("entitlement", "event").filter(key=key).first()
    if receipt:
        if receipt.request_digest != request_digest:
            raise GrantConflict("operation_id уже использован с другими параметрами.")
        return receipt.entitlement, "duplicate", receipt.event


def remember(key, request_digest, entitlement, outcome, event=None):
    AchievementOperation.objects.create(key=key, request_digest=request_digest, entitlement=entitlement,
                                       outcome=outcome, event=event)
    return entitlement, outcome, event


def current_metric_problem(entitlement):
    """Read-only drift check also used by explicit reconciliation of maintenance edits."""
    if not entitlement or not entitlement.active_tier_id:
        return None
    proof = entitlement.events.filter(action__in=["grant", "upgrade"]).last()
    if not proof or proof.source_type == "manual" or not proof.evidence.get("metric_id"):
        return None
    from traineediary.models import WeeklyMetric
    current = WeeklyMetric.objects.filter(pk=proof.evidence["metric_id"], journey__user_id=entitlement.user_id).first()
    field_name = "quality_percent" if entitlement.definition.evaluator_key == "review_quality" else "speed_hours"
    state = {"metric_id": proof.evidence["metric_id"], "missing": current is None}
    if current:
        value = getattr(current, field_name)
        start = current.week_start_date.isoformat() if current.week_start_date else None
        state.update(value=str(value) if value is not None else None, period_start=start)
        if state["value"] == proof.evidence.get(field_name) and start == proof.evidence.get("period_start"):
            return None
    return state


@transaction.atomic
def grant(*, user_id, definition_id, tier_code, evidence, occurred_at, source_type,
          source_ref, operation_id, actor=None, reason="", expected_revision=None, rule_version=1):
    manual = source_type == "manual"
    if manual:
        staff_reason(actor, reason)
    elif actor is not None:
        raise ValidationError("Автор автоматической выдачи задаётся доверенным provider.")
    if occurred_at is None or timezone.is_naive(occurred_at) or occurred_at > timezone.now():
        raise ValidationError("Некорректная дата доказательства.")
    lock_user(user_id)
    definition = AchievementDefinition.objects.select_for_update().get(pk=definition_id)
    validate_definition(definition)
    if not definition.active or definition.rule_version != rule_version:
        raise GrantConflict("Определение отключено или версия правила изменилась.")
    tier = AchievementTier.objects.get(definition=definition, code=tier_code)
    validate_tier(tier)
    if not manual and not tier.parameters.get("automatic"):
        raise ValidationError("Автоматическая выдача уровня отключена.")
    key = operation_key(user_id, definition.pk, "grant", operation_id)
    request_digest = digest([tier.pk, evidence, source_type, source_ref, reason.strip(), actor.pk if actor else None, rule_version])
    repeat = repeated(key, request_digest)
    if repeat:
        if not manual and repeat[0].auto_grant_blocked:
            return repeat[0], "suppressed", None
        return repeat
    entitlement, _ = UserAchievement.objects.get_or_create(user_id=user_id, definition=definition)
    entitlement = UserAchievement.objects.select_for_update(of=("self",)).select_related("active_tier").get(pk=entitlement.pk)
    if expected_revision is not None and entitlement.revision != expected_revision:
        raise GrantConflict("Ревизия награды изменилась.")
    if not manual and entitlement.auto_grant_blocked:
        return remember(key, request_digest, entitlement, "suppressed")
    if entitlement.active_tier and tier.rank <= entitlement.active_tier.rank:
        return remember(key, request_digest, entitlement, "no_op")
    now = timezone.now()
    action = "upgrade" if entitlement.active_tier_id else "grant"
    event = AchievementEvent.objects.create(entitlement=entitlement, action=action,
        from_tier=entitlement.active_tier, to_tier=tier, actor=actor, occurred_at=occurred_at,
        source_type=source_type, source_ref=source_ref, rule_version=rule_version,
        evidence=evidence, evidence_digest=digest(evidence), reason=reason.strip(), idempotency_key=key)
    entitlement.active_tier = tier
    entitlement.first_granted_at = entitlement.first_granted_at or now
    if action == "upgrade":
        entitlement.last_upgraded_at = now
    entitlement.last_changed_at = now
    entitlement.revision += 1
    # A staff regrant is permitted, but does not silently release the automatic block.
    entitlement.save()
    from achievements.services.notifications import enqueue
    enqueue(event)
    return remember(key, request_digest, entitlement, action, event)


@transaction.atomic
def revoke(*, user_id, definition_id, actor, reason, operation_id, expected_revision=None):
    staff_reason(actor, reason)
    lock_user(user_id)
    definition = AchievementDefinition.objects.get(pk=definition_id)
    key = operation_key(user_id, definition_id, "revoke", operation_id)
    request_digest = digest([actor.pk, reason.strip()])
    repeat = repeated(key, request_digest)
    if repeat:
        return repeat
    entitlement = UserAchievement.objects.select_for_update(of=("self",)).select_related("active_tier").get(user_id=user_id, definition=definition)
    if expected_revision is not None and expected_revision != entitlement.revision:
        raise GrantConflict("Ревизия награды изменилась.")
    if entitlement.active_tier_id is None:
        return remember(key, request_digest, entitlement, "no_op")
    last = entitlement.events.filter(action__in=["grant", "upgrade"]).last()
    now = timezone.now()
    event = AchievementEvent.objects.create(entitlement=entitlement, action="revoke", from_tier=entitlement.active_tier,
        to_tier=None, actor=actor, occurred_at=now, source_type="manual", source_ref=operation_id,
        rule_version=definition.rule_version, evidence={"revoked_event_id": last.pk},
        evidence_digest=digest({"revoked_event_id": last.pk}), reason=reason.strip(),
        idempotency_key=key, revoked_event=last)
    entitlement.active_tier = None
    entitlement.auto_grant_blocked = True
    entitlement.last_changed_at = now
    entitlement.revision += 1
    entitlement.save()
    return remember(key, request_digest, entitlement, "revoke", event)


@transaction.atomic
def flag_disputed(*, user_id, metric_id=None, confirmation_revoked=False, source_id, definition_id=None, sandbox_invalid=False):
    """Correction invalidates the proof, never silently lowers the entitlement."""
    lock_user(user_id)
    for entitlement in UserAchievement.objects.filter(user_id=user_id, active_tier__isnull=False):
        if definition_id is not None and entitlement.definition_id != definition_id:
            continue
        event = entitlement.events.filter(action__in=["grant", "upgrade"]).last()
        if event is None or event.source_type == "manual":
            continue
        affected = (metric_id is not None and event.evidence.get("metric_id") == metric_id) or (
            confirmation_revoked and entitlement.definition.evaluator_key == "training_program") or (
            sandbox_invalid and entitlement.definition.evaluator_key in ("sandbox_program", "sandbox_first_five_clean_answers"))
        if not affected:
            continue
        key = digest(["dispute", source_id, entitlement.pk])
        if AchievementEvent.objects.filter(idempotency_key=key).exists():
            continue
        AchievementEvent.objects.create(entitlement=entitlement, action="evidence_disputed",
            from_tier=entitlement.active_tier, to_tier=entitlement.active_tier, occurred_at=timezone.now(),
            source_type="source_correction", source_ref=str(source_id), rule_version=event.rule_version,
            evidence={"disputed_event_id": event.pk}, evidence_digest=digest({"disputed_event_id": event.pk}),
            reason="Исходное доказательство изменено; необходим явный staff review/revoke.", idempotency_key=key)
        entitlement.evidence_disputed = True
        entitlement.revision += 1
        entitlement.last_changed_at = timezone.now()
        entitlement.save()
