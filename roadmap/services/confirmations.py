from django.core.exceptions import PermissionDenied
from django.db import transaction
from traineediary.models import EntryType, TraineeJourney
from roadmap.models import TrainingConfirmationEvent


class ConfirmationConflict(Exception):
    pass


def change_training_confirmation(*, journey_id, actor, confirmed, comment=""):
    if not actor.is_authenticated or not actor.is_staff:
        raise PermissionDenied
    with transaction.atomic():
        # Serialize even the first event by locking the existing parent row.
        journey = TraineeJourney.objects.select_for_update().get(pk=journey_id)
        if journey.entry_type != EntryType.NEW_HIRE:
            raise ConfirmationConflict("Обучение не требуется для внутреннего перевода.")
        latest = journey.roadmap_confirmation_events.order_by("-id").first()
        was_confirmed = latest is not None and latest.action == TrainingConfirmationEvent.Action.CONFIRMED
        if was_confirmed == confirmed:
            return latest, False
        event = TrainingConfirmationEvent.objects.create(
            journey=journey, actor=actor, comment=comment,
            action=(TrainingConfirmationEvent.Action.CONFIRMED if confirmed else TrainingConfirmationEvent.Action.REVOKED),
        )
        from achievements.services.events import publish
        publish(provider="roadmap_confirmation", external_id=event.pk, user_id=journey.user_id,
                context={"journey_id": journey.pk}, payload={"confirmation_id": event.pk, "action": event.action})
        return event, True
