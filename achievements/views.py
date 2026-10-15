import json
from functools import wraps

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import OperationalError
from django.http import JsonResponse
from django.shortcuts import get_object_or_404

from achievements.models import AchievementDefinition, AchievementTier, UserAchievement
from achievements.services.catalog import ART_KEYS
from achievements.services.grants import GrantConflict, grant, revoke
from django.utils import timezone
from traineediary.models import TraineeJourney


def api(method="GET", staff=False):
    def decorator(view):
        @wraps(view)
        def wrapped(request, *args, **kwargs):
            if not request.user.is_authenticated:
                response = JsonResponse({"error": "authentication_required"}, status=401)
            elif staff and not request.user.is_staff:
                response = JsonResponse({"error": "staff_required"}, status=403)
            elif request.method != method:
                response = JsonResponse({"error": "method_not_allowed"}, status=405)
                response["Allow"] = method
            else:
                response = view(request, *args, **kwargs)
            response["Cache-Control"] = "private, no-store"
            response["Vary"] = "Cookie"
            return response
        return wrapped
    return decorator


def applicable(definition, journey):
    if definition.applicability == "both":
        return True
    return journey.entry_type == "new_hire" if journey else None


def dto(definition, entitlement, journey, *, management=False):
    tier = entitlement.active_tier if entitlement else None
    hidden = definition.secret and tier is None and not management
    base = dict(public_id=str(definition.public_id), secret=definition.secret, revealed=not hidden,
                status="earned" if tier else ("revoked" if entitlement and entitlement.auto_grant_blocked else "locked"),
                applicable=applicable(definition, journey), highest_tier=None,
                progress=None, earned_at=entitlement.first_granted_at.isoformat() if entitlement and entitlement.first_granted_at else None,
                last_upgraded_at=entitlement.last_upgraded_at.isoformat() if entitlement and entitlement.last_upgraded_at else None,
                revision=entitlement.revision if entitlement else 0)
    if hidden:
        # No semantic code, thresholds, art family, evidence, history or tier parameters.
        return {**base, "title": "Секретное достижение", "description": None, "art_key": "generic"}
    base.update(code=definition.code, title=definition.title, description=definition.description,
                category=definition.category, kind=definition.kind, rule_version=definition.rule_version,
                art_key=definition.art_key if definition.art_key in ART_KEYS else "generic",
                supported_tiers=[dict(code=t.code, rank=t.rank, rarity=t.rarity, criterion=t.criterion,
                                      automatic=t.parameters.get("automatic", False)) for t in definition.tiers.all()],
                highest_tier=dict(code=tier.code, rank=tier.rank, rarity=tier.rarity) if tier else None,
                data_quality="disputed" if entitlement and entitlement.evidence_disputed else ("verified" if tier else "not_evaluated"))
    last = entitlement.events.filter(action__in=["grant", "upgrade"]).last() if entitlement else None
    base["manual"] = bool(tier and last and last.source_type == "manual")
    if management:
        base["auto_grant_blocked"] = bool(entitlement and entitlement.auto_grant_blocked)
        base["last_changed_at"] = entitlement.last_changed_at.isoformat() if entitlement and entitlement.last_changed_at else None
    return base


def collection(user_id, *, management=False):
    definitions = list(AchievementDefinition.objects.filter(active=True).prefetch_related("tiers"))
    entitlements = {a.definition_id: a for a in UserAchievement.objects.filter(user_id=user_id).select_related("active_tier")}
    journey = TraineeJourney.objects.filter(user_id=user_id).first()
    items = [dto(d, entitlements.get(d.pk), journey, management=management) for d in definitions]
    earned = [i for i in items if i["highest_tier"]]
    return dict(items=items, stats={"earned": len(earned), "applicable_total": sum(i["applicable"] is True for i in items),
        "rarities": {r: sum(i["highest_tier"]["rarity"] == r for i in earned) for r in ("bronze", "silver", "gold", "platinum")}},
        pending_source_events=get_user_model().objects.get(pk=user_id).achievementsourceevent_set.exclude(status="processed").count())


@api()
def me(request):
    return JsonResponse(collection(request.user.pk))


@api(staff=True)
def user_collection(request, user_id):
    get_object_or_404(get_user_model(), pk=user_id)
    return JsonResponse(collection(user_id, management=True))


@api()
def detail(request, public_id):
    return detail_response(request, request.user.pk, public_id)


@api(staff=True)
def user_detail(request, user_id, public_id):
    get_object_or_404(get_user_model(), pk=user_id)
    return detail_response(request, user_id, public_id, management=True)


def detail_response(request, user_id, public_id, *, management=False):
    definition = get_object_or_404(AchievementDefinition.objects.prefetch_related("tiers"), public_id=public_id, active=True)
    entitlement = UserAchievement.objects.select_related("active_tier").filter(user_id=user_id, definition=definition).first()
    item = dto(definition, entitlement, TraineeJourney.objects.filter(user_id=user_id).first(), management=management)
    if not item["revealed"] or entitlement is None:
        return JsonResponse({"achievement": item, "history": [], "next_cursor": None})
    try:
        cursor = int(request.GET.get("cursor", "0"))
        if cursor < 0:
            raise ValueError
    except ValueError:
        return JsonResponse({"error": "invalid_cursor"}, status=400)
    events = list(entitlement.events.filter(pk__gt=cursor).select_related("from_tier", "to_tier", "actor").order_by("id")[:51])
    history = [dict(id=e.pk, action=e.action, from_tier=e.from_tier.code if e.from_tier else None,
                    to_tier=e.to_tier.code if e.to_tier else None, occurred_at=e.occurred_at.isoformat(),
                    recorded_at=e.recorded_at.isoformat(), source=e.source_type, manual=e.source_type == "manual",
                    actor_id=e.actor_id, reason=e.reason, rule_version=e.rule_version) for e in events[:50]]
    if management:
        for row, event in zip(history, events[:50]):
            row["actor_name"] = (event.actor.get_full_name() or event.actor.get_username()) if event.actor else None
    return JsonResponse({"achievement": item, "history": history, "next_cursor": events[49].pk if len(events) > 50 else None})


def action_body(request, *, granting):
    if request.content_type != "application/json":
        raise ValidationError("Требуется JSON.")
    try:
        body = json.loads(request.body)
    except (ValueError, UnicodeDecodeError):
        raise ValidationError("Некорректный JSON.")
    allowed = {"reason", "operation_id", "expected_revision"} | ({"tier"} if granting else set())
    if not isinstance(body, dict) or set(body) - allowed:
        raise ValidationError("Неизвестные поля.")
    if not isinstance(body.get("reason"), str) or not body["reason"].strip() or len(body["reason"]) > 10000:
        raise ValidationError("Нужна причина до 10000 символов.")
    if not isinstance(body.get("operation_id"), str) or not body["operation_id"].strip() or len(body["operation_id"]) > 150:
        raise ValidationError("Нужен operation_id до 150 символов.")
    if "expected_revision" in body and (type(body["expected_revision"]) is not int or body["expected_revision"] < 0):
        raise ValidationError("Некорректная ревизия.")
    if granting and not isinstance(body.get("tier"), str):
        raise ValidationError("Нужен код уровня.")
    return body


def mutate(request, user_id, public_id, *, granting):
    definition = get_object_or_404(AchievementDefinition, public_id=public_id)
    get_object_or_404(get_user_model(), pk=user_id)
    try:
        body = action_body(request, granting=granting)
        kwargs = dict(user_id=user_id, definition_id=definition.pk, actor=request.user, reason=body["reason"],
                      operation_id=body["operation_id"], expected_revision=body.get("expected_revision"))
        if granting:
            if not definition.tiers.filter(code=body["tier"]).exists():
                raise ValidationError("Неизвестный уровень.")
            entitlement, outcome, event = grant(**kwargs, tier_code=body["tier"], evidence={"manual": True},
                occurred_at=timezone.now(), source_type="manual", source_ref=body["operation_id"], rule_version=definition.rule_version)
        else:
            if not UserAchievement.objects.filter(user_id=user_id, definition=definition).exists():
                return JsonResponse({"error": "award_not_found"}, status=404)
            entitlement, outcome, event = revoke(**kwargs)
    except ValidationError as error:
        return JsonResponse({"error": "invalid_request", "detail": error.messages}, status=400)
    except (GrantConflict, OperationalError) as error:
        return JsonResponse({"error": "conflict", "detail": str(error)}, status=409)
    except PermissionDenied:
        return JsonResponse({"error": "staff_required"}, status=403)
    return JsonResponse({"action": outcome, "event_id": event.pk if event else None, "revision": entitlement.revision})


@api(method="POST", staff=True)
def manual_grant(request, user_id, public_id):
    return mutate(request, user_id, public_id, granting=True)


@api(method="POST", staff=True)
def manual_revoke(request, user_id, public_id):
    return mutate(request, user_id, public_id, granting=False)
