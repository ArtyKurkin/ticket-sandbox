import hashlib
import json
import uuid
from contextlib import contextmanager
from contextvars import ContextVar
from functools import wraps
from pathlib import Path
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import connection, transaction
from django.db.models import Max
from django.utils import timezone
from sandbox.ledger_models import (
    SandboxLedgerBoundary,
    SandboxProgramManifest,
    SandboxAttemptCoverage,
    SandboxEvidenceGap,
    TechnicalCheckExecution,
    TechnicalCheckExecutionEvent,
    SandboxEnvironmentEvent,
    SandboxAnswerSubmission,
    SandboxAnswerReviewEvent,
)

_writing = ContextVar("sandbox_ledger_writer", default=False)
PROTECTED = {
    "status",
    "attempts_count",
    "restart_count",
    "started_at",
    "finished_at",
    "technical_passed_at",
    "check_status",
    "check_started_at",
    "check_finished_at",
    "environment_status",
    "environment_started_at",
    "environment_finished_at",
    "mentor_decision",
    "mentor_reviewed_by_id",
    "mentor_reviewed_by",
    "mentor_reviewed_at",
    "user_id",
    "task_id",
    "attempt_number",
    "container_id",
    "container_name",
    "terminal_container_name",
}


def digest(value):
    return hashlib.sha256(
        json.dumps(
            value, sort_keys=True, ensure_ascii=False, separators=(",", ":")
        ).encode()
    ).hexdigest()


def operation_id(value=None):
    try:
        return uuid.UUID(str(value)) if value else uuid.uuid4()
    except (ValueError, TypeError, AttributeError):
        raise ValidationError("Invalid operation ID.")


@contextmanager
def writer():
    token = _writing.set(True)
    try:
        yield
    finally:
        _writing.reset(token)


def trusted(function):

    @wraps(function)
    def wrapped(*args, **kwargs):
        with writer():
            return function(*args, **kwargs)

    return wrapped


@contextmanager
def database_write():
    with transaction.atomic():
        previous = None
        if connection.vendor == "postgresql" and _writing.get():
            with connection.cursor() as cursor:
                cursor.execute("SELECT current_setting('sandbox.ledger_writer',true)")
                previous = cursor.fetchone()[0] or ""
                cursor.execute("SELECT set_config('sandbox.ledger_writer','on',true)")
        try:
            yield
        finally:
            if previous is not None and (not connection.needs_rollback):
                with connection.cursor() as cursor:
                    cursor.execute(
                        "SELECT set_config('sandbox.ledger_writer',%s,true)", [previous]
                    )


def gap(attempt_id, reason, source="service"):
    if SandboxAttemptCoverage.objects.filter(attempt_id=attempt_id).exists():
        SandboxEvidenceGap.objects.create(
            attempt_id=attempt_id, reason=reason, source=source
        )


def unsupported_updates(queryset, fields):
    fields = {
        f.attname
        for f in queryset.model._meta.fields
        if f.name in fields or f.attname in fields
    }
    if (
        connection.vendor != "postgresql"
        and (not _writing.get())
        and PROTECTED.intersection(fields)
    ):
        for pk in queryset.filter(
            pk__in=SandboxAttemptCoverage.objects.values("attempt_id")
        ).values_list("pk", flat=True):
            gap(pk, "unsupported_update", "orm")


def checker_identity(task):
    alternative = task.queue.slug == "l1" and task.slug == "wordpress-500-after-move"
    path = Path(settings.BASE_DIR) / (
        "sandbox/task_checks/wordpress_runtime.php"
        if alternative
        else f"training_tasks/{task.queue.slug}/{task.slug}/files/check.sh"
    )
    return (
        "server_php" if alternative else "task_checker",
        hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None,
    )


def ensure_manifest(user_id, task):
    from sandbox.models import Queue, Task, TaskAttempt, SandboxProgramCompletion

    if task.queue.slug != "l1":
        return None
    owner = get_user_model().objects.select_for_update(no_key=True).get(pk=user_id)
    existing = SandboxProgramManifest.objects.filter(
        user_id=user_id, program_key="l1"
    ).first()
    if existing:
        return existing
    queue = Queue.objects.select_for_update().get(pk=task.queue_id)
    tasks = list(
        Task.objects.select_for_update()
        .filter(queue=queue)
        .select_related("queue")
        .order_by("order", "pk")
    )
    completion = SandboxProgramCompletion.objects.filter(
        user_id=user_id, program_key="l1"
    ).first()
    if completion:
        entries = [
            {
                "task_id": e["task_id"],
                "task_slug": e.get("task_slug"),
                "order": e.get("order"),
                "requires_review": None,
                "criteria_version": None,
                "criteria_digest": None,
            }
            for e in completion.snapshot["tasks"]
        ]
        source = "legacy_completion"
    else:
        entries = [
            {
                "task_id": t.pk,
                "task_slug": t.slug,
                "order": t.order,
                "requires_review": t.requires_manual_review,
                "criteria_version": "technical-v1",
                "criteria_digest": checker_identity(t)[1],
            }
            for t in tasks
            if t.is_active and queue.is_active
        ]
        boundary = SandboxLedgerBoundary.objects.get(pk=1)
        source = (
            "existing_program"
            if TaskAttempt.objects.filter(
                user_id=user_id, attempt_number=1, task__queue=queue
            ).exists()
            else (
                "from_start"
                if owner.pk > boundary.initial_user_id_ceiling
                and owner.date_joined >= boundary.enabled_at
                else "existing_account"
            )
        )
    snapshot = {
        "schema_version": 1,
        "program_key": "l1",
        "requirements_version": 1,
        "tasks": entries,
    }
    return SandboxProgramManifest.objects.create(
        user_id=user_id,
        program_key="l1",
        source=source,
        snapshot=snapshot,
        digest=digest(snapshot),
    )


def created_attempt(attempt, manifest):
    pristine = (
        attempt.status == "new"
        and (not attempt.started_at)
        and (not attempt.technical_passed_at)
        and (not attempt.container_name)
        and (not attempt.attempts_count)
        and (not attempt.restart_count)
        and (not attempt.client_answer)
        and (not attempt.trainee_report)
        and (attempt.check_status == "idle")
        and (attempt.environment_status == "idle")
        and (attempt.mentor_decision == "not_reviewed")
    )
    pristine = pristine and not any(
        getattr(attempt, field)
        for field in [
            "finished_at",
            "check_started_at",
            "check_finished_at",
            "environment_started_at",
            "environment_finished_at",
            "mentor_reviewed_at",
            "mentor_reviewed_by_id",
            "mentor_feedback",
            "container_id",
            "terminal_container_name",
            "terminal_url",
            "terminal_port",
            "shell_command",
        ]
    )
    SandboxAttemptCoverage.objects.create(
        attempt_id=attempt.pk,
        user_id=attempt.user_id,
        task_id=attempt.task_id,
        attempt_number=attempt.attempt_number,
        origin="creation" if pristine else "imported_state",
        initial_counts={
            "checks": attempt.attempts_count,
            "resets": attempt.restart_count,
        },
        manifest=manifest,
    )


def observe(attempt):
    coverage = SandboxAttemptCoverage.objects.filter(attempt_id=attempt.pk).first()
    if not coverage:
        coverage = SandboxAttemptCoverage.objects.create(
            attempt_id=attempt.pk,
            user_id=attempt.user_id,
            task_id=attempt.task_id,
            attempt_number=attempt.attempt_number,
            origin="legacy_observed",
            initial_counts={
                "checks": attempt.attempts_count,
                "resets": attempt.restart_count,
            },
            manifest=None,
        )
    return coverage


@transaction.atomic
def request_check(attempt, source="service", run_id=None):
    from sandbox.models import TaskAttempt

    TaskAttempt.objects.select_for_update().get(pk=attempt.pk)
    observe(attempt)
    ordinal = (
        TechnicalCheckExecution.objects.filter(attempt_id=attempt.pk).aggregate(
            n=Max("ordinal")
        )["n"]
        or 0
    ) + 1
    kind, version = checker_identity(attempt.task)
    execution = TechnicalCheckExecution.objects.create(
        run_id=operation_id(run_id),
        attempt_id=attempt.pk,
        user_id=attempt.user_id,
        task_id=attempt.task_id,
        attempt_number=attempt.attempt_number,
        ordinal=ordinal,
        requested_at=timezone.now(),
        checker_kind=kind,
        criteria_digest=version,
        source=source,
    )
    attempt._ledger_check_id = str(execution.run_id)
    if source != "service":
        gap(attempt.pk, "unregistered_check_request")
    return execution


@transaction.atomic
def begin_check(attempt, run_id):
    from sandbox.models import TaskAttempt

    TaskAttempt.objects.select_for_update().get(pk=attempt.pk)
    execution = TechnicalCheckExecution.objects.get(
        run_id=run_id,
        attempt_id=attempt.pk,
        user_id=attempt.user_id,
        task_id=attempt.task_id,
    )
    if execution.events.exists():
        TechnicalCheckExecutionEvent.objects.get_or_create(
            execution=execution,
            phase="duplicate",
            defaults={"occurred_at": timezone.now(), "reason": "duplicate_delivery"},
        )
        return (execution, False)
    TechnicalCheckExecutionEvent.objects.create(
        execution=execution, phase="started", occurred_at=timezone.now()
    )
    return (execution, True)


def check_live(attempt):
    execution = getattr(attempt, "_ledger_execution", None)
    if execution:
        TechnicalCheckExecution.objects.select_for_update().get(pk=execution.pk)
        if execution.events.filter(phase="finished").exists():
            raise ValidationError("Execution already closed; late result rejected.")
    return execution


def finish_check(
    attempt,
    *,
    result="unknown",
    failure_class="unknown",
    reason="",
    exit_code=None,
    check_run_id=None,
    checker_started=None,
):
    execution = getattr(attempt, "_ledger_execution", None)
    if execution and (not execution.events.filter(phase="finished").exists()):
        TechnicalCheckExecutionEvent.objects.create(
            execution=execution,
            phase="finished",
            occurred_at=timezone.now(),
            result=result,
            failure_class=failure_class,
            reason=reason,
            exit_code=exit_code,
            check_run_id=check_run_id,
            checker_started=checker_started,
        )


@transaction.atomic
def request_environment(attempt, kind, actor=None, origin="unknown", op_id=None):
    from sandbox.models import TaskAttempt

    TaskAttempt.objects.select_for_update().get(pk=attempt.pk)
    if origin not in ["trainee", "maintenance", "unknown"]:
        raise ValidationError("Invalid environment origin.")
    if origin == "trainee" and (actor is None or actor.pk != attempt.user_id):
        raise PermissionDenied
    if origin == "maintenance" and actor is not None and (not actor.is_staff):
        raise PermissionDenied
    op = operation_id(op_id)
    old = SandboxEnvironmentEvent.objects.filter(
        operation_id=op, phase="requested"
    ).first()
    if old:
        if (old.attempt_id, old.kind, old.origin, old.actor_id) != (
            attempt.pk,
            kind,
            origin,
            getattr(actor, "pk", None),
        ):
            raise ValidationError("Operation ID conflict.")
        attempt._ledger_environment_id = str(op)
        return (old, False)
    observe(attempt)
    now = timezone.now()
    event = SandboxEnvironmentEvent.objects.create(
        operation_id=op,
        attempt_id=attempt.pk,
        user_id=attempt.user_id,
        task_id=attempt.task_id,
        attempt_number=attempt.attempt_number,
        kind=kind,
        phase="requested",
        actor_id=getattr(actor, "pk", None),
        origin=origin,
        requested_at=now,
        occurred_at=now,
    )
    attempt._ledger_environment_id = str(op)
    return (event, True)


def environment_phase(request, phase, outcome="unknown", reason=""):
    values = {
        name: getattr(request, name)
        for name in [
            "operation_id",
            "attempt_id",
            "user_id",
            "task_id",
            "attempt_number",
            "kind",
            "actor_id",
            "origin",
            "requested_at",
        ]
    }
    return SandboxEnvironmentEvent.objects.get_or_create(
        operation_id=request.operation_id,
        phase=phase,
        defaults={
            **values,
            "occurred_at": timezone.now(),
            "outcome": outcome,
            "reason": reason,
        },
    )


@transaction.atomic
def begin_environment(attempt, kind, op_id=None, actor=None, origin="unknown"):
    from sandbox.models import TaskAttempt

    TaskAttempt.objects.select_for_update().get(pk=attempt.pk)
    request = (
        SandboxEnvironmentEvent.objects.filter(
            operation_id=op_id, phase="requested", attempt_id=attempt.pk, kind=kind
        ).first()
        if op_id
        else None
    )
    if not request:
        if not op_id and origin == "unknown":
            observe(attempt)
            gap(attempt.pk, "unregistered_environment_request")
        if kind == "start" and origin == "trainee" and attempt.container_name:
            raise ValidationError(
                "An existing environment must use the reset operation."
            )
        request, _ = request_environment(attempt, kind, actor, origin, op_id)
    if SandboxEnvironmentEvent.objects.filter(
        operation_id=request.operation_id, phase__in=["started", "finished"]
    ).exists():
        environment_phase(request, "duplicate", reason="duplicate_delivery")
        return (request, False)
    active = SandboxEnvironmentEvent.objects.filter(
        attempt_id=attempt.pk, phase="requested"
    ).exclude(operation_id=request.operation_id)
    if any(
        (
            not SandboxEnvironmentEvent.objects.filter(
                operation_id=e.operation_id, phase="finished"
            ).exists()
            for e in active
        )
    ):
        environment_phase(
            request, "finished", outcome="not_started", reason="already_running"
        )
        return (request, False)
    environment_phase(request, "started")
    attempt.refresh_from_db()
    return (request, True)


def environment_live(attempt):
    request = getattr(attempt, "_ledger_environment_request", None)
    if request:
        SandboxEnvironmentEvent.objects.select_for_update().get(pk=request.pk)
        if SandboxEnvironmentEvent.objects.filter(
            operation_id=request.operation_id, phase="finished"
        ).exists():
            raise ValidationError("Environment operation already closed.")
    return request


@transaction.atomic
def interrupt(attempt, reason):
    from sandbox.models import TaskAttempt

    TaskAttempt.objects.select_for_update().get(pk=attempt.pk)
    for execution in TechnicalCheckExecution.objects.filter(attempt_id=attempt.pk):
        if not execution.events.filter(phase="finished").exists():
            TechnicalCheckExecutionEvent.objects.create(
                execution=execution,
                phase="finished",
                occurred_at=timezone.now(),
                reason=reason,
                failure_class="unknown",
            )
    for request in SandboxEnvironmentEvent.objects.filter(
        attempt_id=attempt.pk, phase="requested"
    ):
        if not SandboxEnvironmentEvent.objects.filter(
            operation_id=request.operation_id, phase="finished"
        ).exists():
            environment_phase(request, "finished", reason=reason)


@transaction.atomic
def submit_answer(attempt, client_answer, trainee_report, op_id=None):
    from sandbox.models import TaskAttempt

    TaskAttempt.objects.select_for_update().get(pk=attempt.pk)
    fresh = TaskAttempt.objects.get(pk=attempt.pk)
    if (
        not fresh.is_credit_attempt
        or not fresh.task.requires_manual_review
        or (not fresh.technical_passed)
    ):
        raise ValidationError("This attempt is not submitting a reviewed answer.")
    observe(attempt)
    op = operation_id(op_id)
    body = digest([client_answer, trainee_report])
    old = SandboxAnswerSubmission.objects.filter(operation_id=op).first()
    if old:
        if old.attempt_id != attempt.pk or old.digest != body:
            raise ValidationError("Submission operation conflict.")
        return (old, False)
    ordinal = (
        SandboxAnswerSubmission.objects.filter(attempt_id=attempt.pk).aggregate(
            n=Max("ordinal")
        )["n"]
        or 0
    ) + 1
    submission = SandboxAnswerSubmission.objects.create(
        operation_id=op,
        attempt_id=attempt.pk,
        user_id=attempt.user_id,
        task_id=attempt.task_id,
        attempt_number=attempt.attempt_number,
        ordinal=ordinal,
        submitted_at=timezone.now(),
        client_answer=client_answer,
        trainee_report=trainee_report,
        digest=body,
    )
    return (submission, True)


@transaction.atomic
def review_answer(attempt, actor, decision, comment, submission_id=None, op_id=None):
    from sandbox.models import TaskAttempt

    if not actor.is_staff:
        raise PermissionDenied
    TaskAttempt.objects.select_for_update().get(pk=attempt.pk)
    observe(attempt)
    submission = (
        SandboxAnswerSubmission.objects.filter(
            attempt_id=attempt.pk, user_id=attempt.user_id, task_id=attempt.task_id
        )
        .order_by("-ordinal")
        .first()
    )
    if not submission:
        if submission_id:
            raise ValidationError("Submission does not belong to this attempt.")
        gap(attempt.pk, "review_without_submission")
        return None
    if submission_id is None:
        gap(attempt.pk, "review_version_unspecified")
    elif str(submission.pk) != str(submission_id):
        raise ValidationError("Stale or foreign submission version.")
    fresh = TaskAttempt.objects.get(pk=attempt.pk)
    if (fresh.client_answer.strip(), fresh.trainee_report.strip()) != (
        submission.client_answer.strip(),
        submission.trainee_report.strip(),
    ):
        raise ValidationError(
            "Current draft is not the submitted version; wait for a new submission."
        )
    op = operation_id(op_id)
    previous = SandboxAnswerReviewEvent.objects.filter(operation_id=op).first()
    if previous:
        if (
            previous.submission_id,
            previous.actor_id,
            previous.decision,
            previous.comment,
        ) != (submission.pk, actor.pk, decision, comment):
            raise ValidationError("Review operation conflict.")
        return previous
    last = submission.reviews.order_by("-pk").first()
    if last and (last.actor_id, last.decision, last.comment) == (
        actor.pk,
        decision,
        comment,
    ):
        return last
    return SandboxAnswerReviewEvent.objects.create(
        submission=submission,
        actor_id=actor.pk,
        reviewed_at=timezone.now(),
        decision=decision,
        comment=comment,
        operation_id=op,
        kind="correction" if last else "decision",
        supersedes=last,
    )
