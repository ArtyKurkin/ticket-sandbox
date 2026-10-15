"""Pure analysis and explicit write paths for one immutable L1 completion."""

import hashlib
import json
import time
from functools import wraps
from dataclasses import dataclass
from datetime import datetime

from django.core.exceptions import ValidationError
from django.db import OperationalError, connection, transaction
from django.utils import timezone

from sandbox.models import CheckRun, Queue, SandboxProgramCompletion, Task, TaskAttempt
from sandbox.services.technical_evidence import (
    get_technical_evidence,
    with_technical_evidence,
)

PROGRAM_KEY = "l1"
SNAPSHOT_VERSION = 1


def _retry_sqlite_contention(function):
    """SQLite has no row locks; retry a whole standalone transaction on BUSY/LOCKED.

    Never retry a savepoint inside a caller transaction. PostgreSQL uses the
    row locks and unique constraint, without this SQLite-specific fallback.
    """

    @wraps(function)
    def wrapped(*args, **kwargs):
        nested = connection.in_atomic_block
        for retry in range(6):
            try:
                return function(*args, **kwargs)
            except OperationalError as error:
                code = getattr(error.__cause__, "sqlite_errorcode", 0) & 0xFF
                if (
                    nested
                    or connection.vendor != "sqlite"
                    or code not in (5, 6)
                    or retry == 5
                ):
                    raise
                time.sleep(0.01 * 2**retry)

    return wrapped


def composition_fingerprint(program_key, task_ids):
    payload = {
        "schema_version": SNAPSHOT_VERSION,
        "program_key": program_key,
        "task_ids": sorted(task_ids),
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def validate_completion_snapshot(completion):
    snapshot = completion.snapshot
    errors = []
    if (
        not isinstance(snapshot, dict)
        or snapshot.get("schema_version") != SNAPSHOT_VERSION
    ):
        raise ValidationError({"snapshot": "Неизвестный формат снимка."})
    entries = snapshot.get("tasks")
    if not isinstance(entries, list) or not entries:
        raise ValidationError(
            {"snapshot": "Снимок должен содержать непустую программу."}
        )
    ids = []
    for entry in entries:
        if not isinstance(entry, dict):
            errors.append("Некорректное задание снимка.")
            continue
        if any(
            type(entry.get(key)) is not int or entry[key] <= 0
            for key in ("task_id", "attempt_id")
        ):
            errors.append("Нужны идентификаторы задания и зачётной попытки.")
            continue
        ids.append(entry["task_id"])
        source = entry.get("evidence_source")
        if source not in ("technical_passed_at", "check_run"):
            errors.append("Неизвестное техническое доказательство.")
        check_id = entry.get("check_run_id")
        if check_id is not None and (type(check_id) is not int or check_id <= 0):
            errors.append("Некорректный идентификатор CheckRun.")
        if source == "check_run" and check_id is None:
            errors.append("Историческому доказательству нужен CheckRun.")
        try:
            passed_at = datetime.fromisoformat(entry["passed_at"])
            if timezone.is_naive(passed_at) or passed_at > completion.completed_at:
                errors.append("Некорректное время технического доказательства.")
        except (KeyError, ValueError, TypeError):
            errors.append("Нужна дата технического доказательства.")
    if len(ids) != len(set(ids)):
        errors.append("Задания снимка должны быть уникальны.")
    if errors:
        raise ValidationError({"snapshot": errors})
    if completion.composition_fingerprint != composition_fingerprint(
        completion.program_key, ids
    ):
        raise ValidationError(
            {"composition_fingerprint": "Fingerprint не соответствует составу снимка."}
        )


@dataclass(frozen=True)
class CompletionCandidate:
    user_id: int
    eligible: bool
    reason: str
    fingerprint: str = ""
    snapshot: dict | None = None
    completed_at: datetime | None = None


def _candidate(user_id, tasks):
    fingerprint = composition_fingerprint(PROGRAM_KEY, [task.pk for task in tasks])
    if not tasks:
        return CompletionCandidate(user_id, False, "empty_program", fingerprint)
    attempts = with_technical_evidence(
        TaskAttempt.objects.filter(
            user_id=user_id,
            task_id__in=[task.pk for task in tasks],
            attempt_number=1,
        ).order_by("task_id")
    )
    by_task = {attempt.task_id: attempt for attempt in attempts}
    entries = []
    for task in tasks:
        attempt = by_task.get(task.pk)
        evidence = get_technical_evidence(attempt) if attempt is not None else None
        if evidence is None or not evidence.is_completed:
            return CompletionCandidate(
                user_id, False, "missing_technical_evidence", fingerprint
            )
        if evidence.passed_at is None or evidence.passed_at > timezone.now():
            return CompletionCandidate(
                user_id, False, "invalid_evidence_time", fingerprint
            )
        entries.append(
            {
                "task_id": task.pk,
                "task_slug": task.slug,
                "order": task.order,
                "attempt_id": attempt.pk,
                "evidence_source": evidence.source,
                "passed_at": evidence.passed_at.isoformat(),
                # Keep the successful run ID alongside a timestamp when available.
                "check_run_id": evidence.check_run_id or attempt.technical_check_id,
            }
        )
    return CompletionCandidate(
        user_id,
        True,
        "eligible",
        fingerprint,
        {"schema_version": SNAPSHOT_VERSION, "tasks": entries},
        max(datetime.fromisoformat(entry["passed_at"]) for entry in entries),
    )


def analyze_program_completion(user_id):
    """Read-only assessment of CURRENT composition, not a historical reconstruction."""
    queue = Queue.objects.filter(slug=PROGRAM_KEY, is_active=True).first()
    if queue is None:
        return CompletionCandidate(user_id, False, "active_queue_missing")
    return _candidate(
        user_id,
        list(Task.objects.filter(queue=queue, is_active=True).order_by("order", "pk")),
    )


def _locked_candidate(user_id):
    queue = (
        Queue.objects.select_for_update()
        .filter(slug=PROGRAM_KEY, is_active=True)
        .first()
    )
    if queue is None:
        return CompletionCandidate(user_id, False, "active_queue_missing")
    # Lock inactive tasks too, so concurrent activation cannot change this
    # composition. On PostgreSQL the queue lock also excludes new FK inserts.
    tasks = list(Task.objects.select_for_update().filter(queue=queue).order_by("pk"))
    tasks = sorted(
        (task for task in tasks if task.is_active),
        key=lambda task: (task.order, task.pk),
    )
    return _candidate(user_id, tasks)


def _store(candidate, source):
    completion, created = SandboxProgramCompletion.objects.get_or_create(
        user_id=candidate.user_id,
        program_key=PROGRAM_KEY,
        defaults={
            "completed_at": candidate.completed_at,
            "source": source,
            "composition_fingerprint": candidate.fingerprint,
            "snapshot": candidate.snapshot,
        },
    )
    if created:
        from achievements.services.events import publish
        publish(provider="sandbox_completion", external_id=completion.pk, user_id=completion.user_id,
                context={"program_key": PROGRAM_KEY}, payload={"completion_id": completion.pk})
    return completion, created


@_retry_sqlite_contention
@transaction.atomic
def record_completion_after_success(*, attempt_id, check_run_id):
    """Called only from the successful technical write transaction; never from reads."""
    trigger = (
        TaskAttempt.objects.select_related("task", "task__queue")
        .filter(pk=attempt_id, attempt_number=1)
        .first()
    )
    if trigger is None or trigger.task.queue.slug != PROGRAM_KEY:
        return None, False
    valid_run = CheckRun.objects.filter(
        pk=check_run_id,
        attempt_id=trigger.pk,
        result=CheckRun.Result.PASSED,
        exit_code=0,
    ).exists()
    if not valid_run or trigger.technical_passed_at is None:
        raise ValidationError(
            "Фиксация требует подтверждённой успешной технической проверки."
        )
    existing = SandboxProgramCompletion.objects.filter(
        user_id=trigger.user_id, program_key=PROGRAM_KEY
    ).first()
    if existing is not None:
        return existing, False
    candidate = _locked_candidate(trigger.user_id)
    existing = SandboxProgramCompletion.objects.filter(
        user_id=trigger.user_id,
        program_key=PROGRAM_KEY,
    ).first()
    if existing is not None:
        return existing, False
    if not candidate.eligible or trigger.task_id not in {
        entry["task_id"] for entry in candidate.snapshot["tasks"]
    }:
        return None, False
    return _store(candidate, SandboxProgramCompletion.Source.TECHNICAL_CHECK)


@_retry_sqlite_contention
@transaction.atomic
def restore_program_completion(*, user_id, expected_fingerprint):
    """Explicit privileged maintenance write; callers must authorize the selected user/set."""
    existing = SandboxProgramCompletion.objects.filter(
        user_id=user_id, program_key=PROGRAM_KEY
    ).first()
    if existing is not None:
        return existing, False
    candidate = _locked_candidate(user_id)
    existing = SandboxProgramCompletion.objects.filter(
        user_id=user_id,
        program_key=PROGRAM_KEY,
    ).first()
    if existing is not None:
        return existing, False
    if candidate.fingerprint != expected_fingerprint:
        raise ValidationError(
            "Состав программы изменился после предварительного анализа."
        )
    if not candidate.eligible:
        raise ValidationError(f"Завершение не доказано: {candidate.reason}.")
    return _store(candidate, SandboxProgramCompletion.Source.LEGACY_RESTORE)
