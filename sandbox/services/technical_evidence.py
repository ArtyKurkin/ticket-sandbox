"""Read-only technical evidence shared by attempts, queue progress and UI."""

from dataclasses import dataclass
from datetime import datetime

from django.db.models import Exists, OuterRef, Q, Subquery

from sandbox.models import CheckRun, TaskAttempt


@dataclass(frozen=True)
class TechnicalEvidence:
    source: str
    passed_at: datetime | None = None
    check_run_id: int | None = None

    @property
    def is_completed(self):
        return self.source != "missing"


def with_technical_evidence(attempts):
    successful = CheckRun.objects.filter(
        attempt_id=OuterRef("pk"),
        result=CheckRun.Result.PASSED,
        exit_code=0,
    ).order_by("created_at", "pk")
    conflicting = CheckRun.objects.filter(attempt_id=OuterRef("pk")).filter(
        Q(result=CheckRun.Result.PASSED) & ~Q(exit_code=0)
        | Q(result=CheckRun.Result.FAILED, exit_code=0)
    )
    return attempts.annotate(
        technical_check_id=Subquery(successful.values("pk")[:1]),
        technical_check_at=Subquery(successful.values("created_at")[:1]),
        conflicting_check_evidence=Exists(conflicting),
    )


def get_technical_evidence(attempt, *, use_cached=True):
    if attempt.technical_passed_at is not None:
        return TechnicalEvidence("technical_passed_at", attempt.technical_passed_at)
    if use_cached and "technical_check_id" in attempt.__dict__:
        if attempt.technical_check_id is not None:
            return TechnicalEvidence(
                "check_run", attempt.technical_check_at, attempt.technical_check_id
            )
        return TechnicalEvidence("missing")
    if attempt.pk is None:
        return TechnicalEvidence("missing")
    prefetched = None
    if use_cached:
        prefetched = getattr(attempt, "_prefetched_objects_cache", {}).get("check_runs")
        if prefetched is None:
            prefetched = getattr(attempt, "recent_check_runs", None)
    if prefetched is not None:
        check_run = min(
            (
                run
                for run in prefetched
                if run.result == CheckRun.Result.PASSED and run.exit_code == 0
            ),
            key=lambda run: (run.created_at, run.pk),
            default=None,
        )
    else:
        check_run = (
            attempt.check_runs.filter(
                result=CheckRun.Result.PASSED,
                exit_code=0,
            )
            .order_by("created_at", "pk")
            .first()
        )
    if check_run is None:
        return TechnicalEvidence("missing")
    return TechnicalEvidence("check_run", check_run.created_at, check_run.pk)


def credit_task_completed(*, user, task):
    attempt = with_technical_evidence(
        TaskAttempt.objects.filter(
            user=user,
            task=task,
            attempt_number=1,
        )
    ).first()
    return attempt is not None and get_technical_evidence(attempt).is_completed


@dataclass(frozen=True)
class ProgressDiagnostic:
    attempt_id: int
    user_id: int
    task_id: int
    code: str


def diagnose_technical_evidence(attempt):
    """Does not infer a pass from mutable workflow/mentor statuses."""
    diagnostics = []
    if not get_technical_evidence(attempt).is_completed:
        if attempt.status == TaskAttempt.Status.PASSED:
            diagnostics.append(
                ProgressDiagnostic(
                    attempt.pk,
                    attempt.user_id,
                    attempt.task_id,
                    "passed_without_technical_evidence",
                )
            )
        if attempt.check_status == TaskAttempt.CheckStatus.PASSED:
            diagnostics.append(
                ProgressDiagnostic(
                    attempt.pk,
                    attempt.user_id,
                    attempt.task_id,
                    "check_status_without_technical_evidence",
                )
            )
    if getattr(attempt, "conflicting_check_evidence", False):
        diagnostics.append(
            ProgressDiagnostic(
                attempt.pk, attempt.user_id, attempt.task_id, "conflicting_check_run"
            )
        )
    return tuple(diagnostics)
