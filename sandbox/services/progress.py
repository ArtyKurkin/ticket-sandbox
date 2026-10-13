"""Technical queue progress. All builders only read the database."""

from dataclasses import dataclass

from sandbox.models import Queue, Task, TaskAttempt
from sandbox.services.technical_evidence import (
    ProgressDiagnostic,
    diagnose_technical_evidence,
    get_technical_evidence,
    with_technical_evidence,
)

L1_QUEUE_SLUG = "l1"


@dataclass(frozen=True)
class SandboxQueueProgress:
    # Original names retained for existing Django callers and typed assessment fixtures.
    queue_exists: bool
    queue_slug: str
    queue_name: str
    total_count: int
    passed_count: int
    remaining_count: int
    on_review_count: int
    progress_percent: int
    is_ready: bool
    needs_revision_count: int = 0
    unsubmitted_count: int = 0
    unread_feedback_count: int = 0
    approved_answer_count: int = 0
    feedback_read_state_unknown_count: int = 0
    required_task_ids: tuple[int, ...] = ()
    technically_completed_task_ids: tuple[int, ...] = ()
    diagnostics: tuple[ProgressDiagnostic, ...] = ()

    @property
    def technical_completed_count(self):
        return self.passed_count

    @property
    def is_technically_completed(self):
        return self.is_ready


def _empty_progress(queue_slug, *, queue_exists=False, queue_name=""):
    return SandboxQueueProgress(
        queue_exists,
        queue_slug,
        queue_name,
        0,
        0,
        0,
        0,
        0,
        False,
    )


def build_sandbox_queue_progress_map(users, queue_slug=L1_QUEUE_SLUG):
    user_ids = {user.pk for user in users if user.pk is not None}
    if not user_ids:
        return {}
    queue = Queue.objects.filter(slug=queue_slug, is_active=True).first()
    if queue is None:
        return {user_id: _empty_progress(queue_slug) for user_id in user_ids}
    tasks = list(
        Task.objects.filter(queue=queue, is_active=True).order_by("order", "pk")
    )
    if not tasks:
        return {
            user_id: _empty_progress(
                queue_slug, queue_exists=True, queue_name=queue.name
            )
            for user_id in user_ids
        }
    task_ids = tuple(task.pk for task in tasks)
    attempts = with_technical_evidence(
        TaskAttempt.objects.filter(
            user_id__in=user_ids,
            task_id__in=task_ids,
            attempt_number=1,
        )
        .select_related("task")
        .order_by("user_id", "task_id")
    )
    attempts_by_user = {user_id: [] for user_id in user_ids}
    for attempt in attempts:
        attempts_by_user[attempt.user_id].append(attempt)
    progress = {}
    for user_id, credit_attempts in attempts_by_user.items():
        completed_ids = set()
        on_review = needs_revision = unsubmitted = 0
        unread = approved = unknown_feedback = 0
        diagnostics = []
        for attempt in credit_attempts:
            technical_success = get_technical_evidence(attempt).is_completed
            if technical_success:
                completed_ids.add(attempt.task_id)
            diagnostics.extend(diagnose_technical_evidence(attempt))
            # Answer work is orthogonal to technical evidence. Invalid historical
            # results can still have mentor feedback/revision requests to resolve.
            if attempt.task.requires_manual_review:
                if attempt.mentor_decision == TaskAttempt.MentorDecision.NEEDS_REVISION:
                    needs_revision += 1
                elif attempt.mentor_decision == TaskAttempt.MentorDecision.APPROVED:
                    approved += 1
                elif attempt.status == TaskAttempt.Status.ON_REVIEW:
                    on_review += 1
                elif technical_success:
                    unsubmitted += 1
                if attempt.has_unread_mentor_feedback:
                    unread += 1
                elif attempt.mentor_feedback_read_state == "unknown":
                    unknown_feedback += 1
        completed_count = len(completed_ids)
        progress[user_id] = SandboxQueueProgress(
            queue_exists=True,
            queue_slug=queue.slug,
            queue_name=queue.name,
            total_count=len(task_ids),
            passed_count=completed_count,
            remaining_count=len(task_ids) - completed_count,
            on_review_count=on_review,
            progress_percent=round(completed_count / len(task_ids) * 100),
            is_ready=completed_count == len(task_ids),
            needs_revision_count=needs_revision,
            unsubmitted_count=unsubmitted,
            unread_feedback_count=unread,
            approved_answer_count=approved,
            feedback_read_state_unknown_count=unknown_feedback,
            required_task_ids=task_ids,
            technically_completed_task_ids=tuple(
                pk for pk in task_ids if pk in completed_ids
            ),
            diagnostics=tuple(diagnostics),
        )
    return progress


def build_sandbox_queue_progress(user, queue_slug=L1_QUEUE_SLUG):
    return build_sandbox_queue_progress_map([user], queue_slug).get(
        user.pk,
        _empty_progress(queue_slug),
    )
