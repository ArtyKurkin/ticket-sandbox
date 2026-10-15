from django.conf import settings
from django.db import models


class AuditQuerySet(models.QuerySet):
    def update(self, **kwargs):
        raise ValueError("Confirmation events are immutable")

    def delete(self):
        raise ValueError("Confirmation events are immutable")

    def bulk_create(self, objs, *args, **kwargs):
        raise ValueError("Use the confirmation service to append events")

    def bulk_update(self, objs, fields, batch_size=None):
        raise ValueError("Confirmation events are immutable")


class TrainingConfirmationEvent(models.Model):
    """Append-only audit; status is derived from the last event, never duplicated."""

    objects = AuditQuerySet.as_manager()

    class Action(models.TextChoices):
        CONFIRMED = "confirmed", "Подтверждение"
        REVOKED = "revoked", "Отмена"

    journey = models.ForeignKey(
        "traineediary.TraineeJourney", on_delete=models.PROTECT,
        related_name="roadmap_confirmation_events",
    )
    stage_code = models.CharField(max_length=32, default="training", editable=False)
    action = models.CharField(max_length=16, choices=Action.choices)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)
    comment = models.TextField(blank=True)

    class Meta:
        ordering = ["id"]
        indexes = [models.Index(fields=["journey", "stage_code", "id"])]
        constraints = [
            models.CheckConstraint(condition=models.Q(stage_code="training"), name="roadmap_training_only"),
            models.CheckConstraint(condition=models.Q(action__in=["confirmed", "revoked"]), name="roadmap_valid_action"),
        ]

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValueError("Confirmation events are immutable")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError("Confirmation events are immutable")
