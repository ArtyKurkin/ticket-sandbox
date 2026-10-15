"""Durable delivery projection. AchievementEvent itself is never changed here."""
from datetime import timedelta
from uuid import UUID

from django.db import transaction
from django.db.models import Q
from django.urls import reverse
from django.utils import timezone

from achievements.models import AchievementEvent, AchievementNotification, AchievementNotificationBoundary
from achievements.services.catalog import ART_KEYS

LEASE_SECONDS = 90
PAGE_SIZE = 10


class NotificationConflict(Exception):
    pass


def enqueue(event):
    """Called inside the grant transaction, only after a real grant/upgrade."""
    boundary = AchievementNotificationBoundary.objects.filter(pk=1).first()
    if boundary and event.action in ("grant", "upgrade") and event.recorded_at >= boundary.started_at:
        return AchievementNotification.objects.get_or_create(event=event, defaults={"user_id": event.entitlement.user_id})[1]
    return False


def repair_delivery(limit=100):
    """Catch a rolling-deploy gap, bounded by the recorded migration boundary.

    This creates delivery state only, never awards or acknowledgements.
    """
    boundary = AchievementNotificationBoundary.objects.filter(pk=1).first()
    if not boundary:
        return 0
    events = AchievementEvent.objects.filter(action__in=["grant", "upgrade"],
        recorded_at__gte=boundary.started_at, notification__isnull=True).select_related("entitlement").order_by("id")[:max(0, limit)]
    return sum(enqueue(event) for event in events)


def owned(user_id):
    # Both associations are checked, even if a maintenance writer corrupts the projection.
    return AchievementNotification.objects.filter(user_id=user_id, event__entitlement__user_id=user_id,
        event__action__in=["grant", "upgrade"])


def visible(query):
    return query.filter(event__entitlement__definition__active=True).filter(
        Q(event__entitlement__definition__secret=False) | Q(event__entitlement__active_tier__isnull=False))


def item(notification):
    event = notification.event
    definition = event.entitlement.definition
    def tier(value):
        return {"code": value.code, "rank": value.rank, "rarity": value.rarity} if value else None
    return {"event_id": event.pk, "action": event.action, "public_id": str(definition.public_id),
        "title": definition.title, "secret": definition.secret, "from_tier": tier(event.from_tier),
        "to_tier": tier(event.to_tier), "recorded_at": event.recorded_at.isoformat(),
        "art_key": definition.art_key if definition.art_key in ART_KEYS else "generic",
        "read": notification.read_at is not None, "read_at": notification.read_at.isoformat() if notification.read_at else None}


def related(query):
    return query.select_related("event__entitlement__definition", "event__from_tier", "event__to_tier")


def feed(user_id):
    unread = visible(owned(user_id).filter(read_at__isnull=True))
    available = unread.filter(Q(claim_expires_at__isnull=True) | Q(claim_expires_at__lte=timezone.now()))
    rows = list(related(available).order_by("event_id")[:PAGE_SIZE])
    return {"items": [item(n) for n in rows], "unread_count": unread.count(),
        "has_more": available.count() > len(rows), "poll_after_seconds": 50,
        "trophy_room_url": reverse("achievements")}


def token(value):
    try:
        return UUID(value)
    except (ValueError, TypeError, AttributeError):
        raise ValueError("invalid_claim_token")


@transaction.atomic
def claim(user_id, event_id, claim_token):
    from achievements.services.grants import lock_user
    lock_user(user_id)  # Same ordering as grant/revoke; secret state cannot change mid-claim.
    # Lock only delivery state, never the append-only event or a nullable join.
    notification = owned(user_id).select_for_update(of=("self",)).get(event_id=event_id)
    if notification.read_at:
        return {"read": True, "event_id": event_id}
    if not visible(owned(user_id)).filter(pk=notification.pk).exists():
        raise AchievementNotification.DoesNotExist
    now = timezone.now()
    if (notification.claim_token != claim_token and notification.claim_expires_at
            and notification.claim_expires_at > now):
        raise NotificationConflict("claimed")
    notification.claim_token = claim_token
    notification.claim_expires_at = now + timedelta(seconds=LEASE_SECONDS)
    notification.save(update_fields=["claim_token", "claim_expires_at"])
    return {"notification": item(related(owned(user_id)).get(pk=notification.pk)),
        "claim_token": str(claim_token), "lease_seconds": LEASE_SECONDS, "read": False}


@transaction.atomic
def acknowledge(user_id, event_id, claim_token):
    notification = owned(user_id).select_for_update(of=("self",)).get(event_id=event_id)
    if notification.read_at is None:
        # A retry after lease expiry is safe until somebody else has claimed this row.
        if notification.claim_token != claim_token:
            raise NotificationConflict("claim_required")
        notification.read_at = timezone.now()
        notification.claim_expires_at = None
        notification.save(update_fields=["read_at", "claim_expires_at"])
    return {"event_id": event_id, "read": True, "read_at": notification.read_at.isoformat()}
