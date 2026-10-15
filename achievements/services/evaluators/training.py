from django.utils import timezone
from .base import Evaluation, eligible, unknown


def training(journey, tiers):
    event = journey.roadmap_confirmation_events.select_related("actor").order_by("-id").first()
    if event is None or event.action != "confirmed":
        return Evaluation("not_met", reason="no_active_confirmation")
    if not event.actor.is_staff or event.created_at > timezone.now():
        return unknown("untrusted_confirmation", "trusted confirmation actor/time")
    return eligible(tiers[0], {"confirmation_id": event.pk, "source": "manual", "completion": True},
                    {"journey_id": journey.pk}, event.created_at)
