"""Diagnostic HTTP runs. Never used by technical_evidence or academic writers."""
import uuid

from django.db import models
from django.db.models import Q


class HTTPObservationRun(models.Model):
    attempt = models.ForeignKey("sandbox.TaskAttempt", on_delete=models.CASCADE, related_name="http_observations")
    requested_by_id = models.PositiveBigIntegerField()
    run_id = models.UUIDField(default=uuid.uuid4, unique=True)
    ordinal = models.PositiveIntegerField()
    technical_execution = models.ForeignKey("sandbox.TechnicalCheckExecution", null=True, on_delete=models.PROTECT)
    technical_event_id = models.PositiveBigIntegerField(null=True)
    execution_origin = models.CharField(max_length=24, default="observation")
    environment_uuid = models.UUIDField()
    identity = models.JSONField()
    policy = models.JSONField()
    runtime = models.JSONField(default=dict)
    status = models.CharField(max_length=10, default="queued")
    http = models.CharField(max_length=10, default="unknown")
    reason = models.CharField(max_length=48, default="queued")
    result = models.JSONField(default=dict)
    requested_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True)
    finished_at = models.DateTimeField(null=True)

    @property
    def academic_pass(self):
        return False

    @property
    def task_verdict(self):
        return "failed" if self.http == "mismatch" else "unknown"

    @property
    def status_label(self):
        return {"queued": "в очереди", "running": "проверяется", "finished": "завершено"}[self.status]

    @property
    def http_label(self):
        return {"matched": "ответ соответствует", "mismatch": "ответ не соответствует", "unknown": "не удалось проверить"}[self.http]

    class Meta:
        ordering = ["-pk"]
        constraints = [
            models.UniqueConstraint(fields=["attempt", "ordinal"], name="http_observation_ordinal_unique"),
            models.UniqueConstraint(fields=["attempt"], condition=Q(status__in=["queued", "running"]), name="http_observation_one_active"),
            models.CheckConstraint(condition=Q(http__in=["matched", "mismatch", "unknown"]), name="http_observation_http_values"),
            models.CheckConstraint(condition=Q(status__in=["queued", "running", "finished"]), name="http_observation_status_values"),
        ]
