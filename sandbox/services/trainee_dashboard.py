from sandbox.models import Task, TraineeProfile
from sandbox.services.attempt_display import enrich_attempts_display_state
from sandbox.services.attempts import (
    get_current_attempt,
    task_was_technically_completed,
)


LEVEL_ACCESS = {
    TraineeProfile.Level.CANDIDATE: ["candidate"],
    TraineeProfile.Level.L1: ["l1"],
    TraineeProfile.Level.L2: ["l1", "l2"],
    TraineeProfile.Level.ADMIN: ["candidate", "l1", "l2", "admin"],
}


def build_trainee_dashboard_context(user):
    profile = user.trainee_profile

    available_queue_slugs = LEVEL_ACCESS.get(
        profile.level,
        ["candidate"],
    )

    tasks = (
        Task.objects
        .filter(
            is_active=True,
            queue__is_active=True,
            queue__slug__in=available_queue_slugs,
        )
        .select_related("queue")
        .order_by("queue__order", "order")
    )

    queue_sections = {}
    unread_feedback_attempts = []

    for task in tasks:
        attempt = get_current_attempt(
            user=user,
            task=task,
        )

        if attempt.has_unread_mentor_feedback:
            unread_feedback_attempts.append(attempt)

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

        if task_was_technically_completed(
            user=user,
            task=task,
        ):
            section["completed_count"] += 1

    for section in queue_sections.values():
        section["attempts"] = enrich_attempts_display_state(
            section["attempts"]
        )

    return {
        "queue_sections": queue_sections.values(),
        "unread_feedback_attempts": unread_feedback_attempts,
    }
