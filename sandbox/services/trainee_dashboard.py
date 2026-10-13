from sandbox.models import Task, TaskAttempt
from sandbox.services.attempt_display import enrich_attempts_display_state
from sandbox.services.attempts import (
    get_current_attempt,
)

from .progress import build_sandbox_queue_progress


def build_trainee_dashboard_context(user):
    profile = user.trainee_profile

    tasks = (
        Task.objects
        .filter(
            is_active=True,
            queue__is_active=True,
            queue__required_level=profile.level,
        )
        .select_related("queue")
        .order_by("queue__order", "order")
    )

    queue_sections = {}
    for task in tasks:
        attempt = get_current_attempt(
            user=user,
            task=task,
        )

        queue = attempt.task.queue

        if queue.id not in queue_sections:
            queue_sections[queue.id] = {
                "queue": queue,
                "attempts": [],
                "total_count": 0,
                "completed_count": 0,
            }

        section = queue_sections[queue.id]
        section["attempts"].append(attempt)
        section["total_count"] += 1

    for section in queue_sections.values():
        progress = build_sandbox_queue_progress(user, section["queue"].slug)
        section["progress"] = progress
        section["completed_count"] = progress.technical_completed_count
        section["total_count"] = progress.total_count
        section["attempts"] = enrich_attempts_display_state(
            section["attempts"]
        )

    credit_attempts = TaskAttempt.objects.filter(
        user=user, attempt_number=1, task__in=tasks,
    ).select_related("task", "task__queue")
    unread_feedback_attempts = [
        attempt for attempt in credit_attempts if attempt.has_unread_mentor_feedback
    ]

    return {
        "queue_sections": queue_sections.values(),
        "unread_feedback_attempts": unread_feedback_attempts,
    }
