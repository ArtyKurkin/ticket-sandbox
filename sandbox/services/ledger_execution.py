"""Lifecycle wrappers fence duplicates before external side effects, and late writes afterward."""

from functools import wraps
from django.core.exceptions import PermissionDenied
from django.db import transaction
from sandbox.models import TaskAttempt
from sandbox.services import ledger
from sandbox.services.technical_evidence import get_technical_evidence


def checked(function):

    @wraps(function)
    def wrapped(*, attempt, user_id, mark_as_running=True, run_id=None):
        attempt.refresh_from_db()
        if attempt.user_id != user_id:
            raise PermissionDenied
        if get_technical_evidence(attempt, use_cached=False).is_completed:
            if run_id:
                with transaction.atomic():
                    execution = ledger.TechnicalCheckExecution.objects.filter(
                        run_id=run_id, attempt_id=attempt.pk, user_id=user_id
                    ).first()
                    if execution:
                        ledger.TechnicalCheckExecutionEvent.objects.get_or_create(
                            execution=execution,
                            phase="duplicate",
                            defaults={
                                "occurred_at": ledger.timezone.now(),
                                "reason": "duplicate_delivery",
                            },
                        )
            with ledger.writer():
                return function(attempt=attempt, user_id=user_id, mark_as_running=False)
        if mark_as_running and run_id is None:
            from sandbox.services.checks import (
                try_mark_attempt_check_running,
                AttemptCheckResult,
            )

            if not try_mark_attempt_check_running(attempt=attempt):
                return AttemptCheckResult(
                    attempt.technical_passed, "Проверка уже выполняется или засчитана."
                )
            run_id = attempt._ledger_check_id
        if run_id is None:
            run_id = str(ledger.request_check(attempt, source="legacy_delivery").run_id)
        execution, started = ledger.begin_check(attempt, run_id)
        attempt._ledger_execution = execution
        if not started:
            from sandbox.services.checks import AttemptCheckResult

            result = execution.events.filter(phase="finished").first()
            return AttemptCheckResult(
                bool(result and result.result == "passed"),
                "Проверка уже обработана или выполняется.",
            )
        try:
            with ledger.writer():
                return function(attempt=attempt, user_id=user_id, mark_as_running=False)
        except Exception:
            with transaction.atomic():
                TaskAttempt.objects.select_for_update().get(pk=attempt.pk)
                ledger.finish_check(attempt, reason="background_error")
            raise

    return wrapped


def environment(kind):

    def decorate(function):

        @wraps(function)
        def wrapped(attempt, *, operation_id=None, actor=None, origin="unknown"):
            attempt.refresh_from_db()
            op = operation_id or getattr(attempt, "_ledger_environment_id", None)
            request, started = ledger.begin_environment(
                attempt, kind, op, actor, origin
            )
            attempt._ledger_environment_request = request
            if not started:
                attempt.refresh_from_db()
                return attempt
            try:
                with ledger.writer():
                    return function(attempt)
            except Exception:
                with transaction.atomic():
                    TaskAttempt.objects.select_for_update().get(pk=attempt.pk)
                    ledger.environment_phase(
                        request, "finished", reason="environment_error"
                    )
                raise

        return wrapped

    return decorate
