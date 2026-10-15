"""Immutable facts use numeric identity snapshots so deleting a task never erases evidence."""

import uuid
from django.db import models
from django.db.models import Q
from django.core.exceptions import ValidationError


class LedgerQuerySet(models.QuerySet):

    def update(self, **kwargs):
        raise ValidationError("Sandbox ledger is append-only.")

    def delete(self):
        raise ValidationError("Sandbox ledger is append-only.")

    def bulk_update(self, *args, **kwargs):
        raise ValidationError("Sandbox ledger is append-only.")

    def bulk_create(self, *args, **kwargs):
        raise ValidationError("Use the ledger service.")


class LedgerFact(models.Model):
    recorded_at = models.DateTimeField(auto_now_add=True)
    objects = LedgerQuerySet.as_manager()

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValidationError("Sandbox ledger is append-only.")
        kwargs["force_insert"] = True
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Sandbox ledger is append-only.")


class SandboxLedgerBoundary(LedgerFact):
    enabled_at = models.DateTimeField()
    initial_user_id_ceiling = models.PositiveBigIntegerField(default=0)
    version = models.PositiveSmallIntegerField(default=1)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(id=1), name="sandbox_ledger_boundary_singleton"
            )
        ]


class SandboxProgramManifest(LedgerFact):
    user_id = models.PositiveBigIntegerField()
    program_key = models.SlugField()
    requirements_version = models.PositiveSmallIntegerField(default=1)
    source = models.CharField(max_length=30)
    snapshot = models.JSONField()
    digest = models.CharField(max_length=64)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user_id", "program_key"], name="sandbox_manifest_user_program"
            )
        ]


class SandboxAttemptCoverage(LedgerFact):
    attempt_id = models.PositiveBigIntegerField(unique=True)
    user_id = models.PositiveBigIntegerField()
    task_id = models.PositiveBigIntegerField()
    attempt_number = models.PositiveIntegerField()
    ledger_version = models.PositiveSmallIntegerField(default=1)
    origin = models.CharField(max_length=30)
    initial_counts = models.JSONField()
    manifest = models.ForeignKey(
        SandboxProgramManifest, null=True, on_delete=models.PROTECT
    )


class SandboxEvidenceGap(LedgerFact):
    attempt_id = models.PositiveBigIntegerField(db_index=True)
    reason = models.CharField(max_length=60)
    source = models.CharField(max_length=30, default="service")


class TechnicalCheckExecution(LedgerFact):
    run_id = models.UUIDField(default=uuid.uuid4, unique=True)
    attempt_id = models.PositiveBigIntegerField(db_index=True)
    user_id = models.PositiveBigIntegerField()
    task_id = models.PositiveBigIntegerField()
    attempt_number = models.PositiveIntegerField()
    ordinal = models.PositiveIntegerField()
    requested_at = models.DateTimeField()
    checker_kind = models.CharField(max_length=30)
    criteria_digest = models.CharField(max_length=64, null=True)
    source = models.CharField(max_length=30, default="service")

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["attempt_id", "ordinal"], name="sandbox_check_ordinal_unique"
            )
        ]


class TechnicalCheckExecutionEvent(LedgerFact):
    execution = models.ForeignKey(
        TechnicalCheckExecution, on_delete=models.PROTECT, related_name="events"
    )
    phase = models.CharField(
        max_length=10,
        choices=[
            ("started", "Started"),
            ("finished", "Finished"),
            ("duplicate", "Duplicate"),
        ],
    )
    occurred_at = models.DateTimeField()
    result = models.CharField(
        max_length=15,
        default="unknown",
        choices=[("passed", "Passed"), ("failed", "Failed"), ("unknown", "Unknown")],
    )
    failure_class = models.CharField(max_length=20, default="unknown")
    reason = models.CharField(max_length=60, blank=True)
    checker_started = models.BooleanField(null=True)
    exit_code = models.IntegerField(null=True)
    check_run_id = models.PositiveBigIntegerField(null=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["execution", "phase"], name="sandbox_check_phase_unique"
            )
        ]


class SandboxEnvironmentEvent(LedgerFact):
    operation_id = models.UUIDField()
    attempt_id = models.PositiveBigIntegerField(db_index=True)
    user_id = models.PositiveBigIntegerField()
    task_id = models.PositiveBigIntegerField()
    attempt_number = models.PositiveIntegerField()
    kind = models.CharField(
        max_length=10,
        choices=[("start", "Start"), ("reset", "Reset"), ("cleanup", "Cleanup")],
    )
    phase = models.CharField(
        max_length=10,
        choices=[
            ("requested", "Requested"),
            ("started", "Started"),
            ("finished", "Finished"),
            ("duplicate", "Duplicate"),
        ],
    )
    actor_id = models.PositiveBigIntegerField(null=True)
    origin = models.CharField(
        max_length=15,
        choices=[
            ("trainee", "Trainee"),
            ("maintenance", "Maintenance"),
            ("unknown", "Unknown"),
        ],
    )
    requested_at = models.DateTimeField()
    occurred_at = models.DateTimeField()
    outcome = models.CharField(max_length=15, default="unknown")
    reason = models.CharField(max_length=60, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["operation_id", "phase"],
                name="sandbox_environment_phase_unique",
            )
        ]


class SandboxAnswerSubmission(LedgerFact):
    operation_id = models.UUIDField(unique=True)
    attempt_id = models.PositiveBigIntegerField(db_index=True)
    user_id = models.PositiveBigIntegerField()
    task_id = models.PositiveBigIntegerField()
    attempt_number = models.PositiveIntegerField()
    ordinal = models.PositiveIntegerField()
    submitted_at = models.DateTimeField()
    client_answer = models.TextField()
    trainee_report = models.TextField()
    digest = models.CharField(max_length=64)
    state = models.CharField(max_length=15, default="submitted")

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["attempt_id", "ordinal"],
                name="sandbox_submission_ordinal_unique",
            )
        ]


class SandboxAnswerReviewEvent(LedgerFact):
    def save(self, *args, **kwargs):
        if not self._state.adding:
            return super().save(*args, **kwargs)
        from django.contrib.auth import get_user_model

        if (
            not get_user_model()
            .objects.filter(pk=self.actor_id, is_staff=True)
            .exists()
        ):
            raise ValidationError("Only an authorized staff actor records a review.")
        if self.decision not in ("approved", "needs_revision", "not_reviewed"):
            raise ValidationError("Invalid review decision.")
        from sandbox.models import TaskAttempt

        attempt = TaskAttempt.objects.get(pk=self.submission.attempt_id)
        if (attempt.user_id, attempt.task_id, attempt.attempt_number) != (
            self.submission.user_id,
            self.submission.task_id,
            self.submission.attempt_number,
        ):
            raise ValidationError("Submission identity mismatch.")
        if (attempt.client_answer.strip(), attempt.trainee_report.strip()) != (
            self.submission.client_answer.strip(),
            self.submission.trainee_report.strip(),
        ):
            raise ValidationError("Review must refer to the submitted text.")
        latest = (
            SandboxAnswerSubmission.objects.filter(
                attempt_id=self.submission.attempt_id
            )
            .order_by("-ordinal")
            .first()
        )
        previous = (
            type(self)
            .objects.filter(submission=self.submission)
            .order_by("-pk")
            .first()
        )
        if (
            latest.pk != self.submission_id
            or self.supersedes_id != (previous.pk if previous else None)
            or self.kind != ("correction" if previous else "decision")
        ):
            raise ValidationError(
                "Review requires the current submission and correction chain."
            )
        return super().save(*args, **kwargs)

    submission = models.ForeignKey(
        SandboxAnswerSubmission, on_delete=models.PROTECT, related_name="reviews"
    )
    actor_id = models.PositiveBigIntegerField()
    reviewed_at = models.DateTimeField()
    decision = models.CharField(max_length=20)
    comment = models.TextField(blank=True)
    operation_id = models.UUIDField(unique=True)
    kind = models.CharField(
        max_length=15, choices=[("decision", "Decision"), ("correction", "Correction")]
    )
    supersedes = models.ForeignKey("self", null=True, on_delete=models.PROTECT)
