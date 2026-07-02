from django.db import IntegrityError
from django.db.models import Q

from sandbox.models import TaskAttempt


def get_current_attempt(user, task):
    attempt = (
        TaskAttempt.objects
        .filter(
            user=user,
            task=task,
            is_current=True,
        )
        .order_by("-attempt_number", "-id")
        .first()
    )

    if attempt:
        return attempt

    latest_attempt = (
        TaskAttempt.objects
        .filter(
            user=user,
            task=task,
        )
        .order_by("-attempt_number", "-id")
        .first()
    )

    if latest_attempt:
        latest_attempt.is_current = True
        latest_attempt.save(update_fields=["is_current"])
        return latest_attempt

    try:
        return TaskAttempt.objects.create(
            user=user,
            task=task,
            attempt_number=1,
            is_current=True,
        )
    except IntegrityError:
        return (
            TaskAttempt.objects
            .filter(
                user=user,
                task=task,
                is_current=True,
            )
            .order_by("-attempt_number", "-id")
            .get()
        )


def get_next_attempt_number(user, task):
    latest_attempt = (
        TaskAttempt.objects
        .select_for_update()
        .filter(
            user=user,
            task=task,
        )
        .order_by("-attempt_number", "-id")
        .first()
    )

    if not latest_attempt:
        return 1

    return latest_attempt.attempt_number + 1


def task_was_technically_completed(user, task):
    return (
        TaskAttempt.objects
        .filter(
            user=user,
            task=task,
        )
        .filter(
            Q(status=TaskAttempt.Status.PASSED)
            | Q(technical_passed_at__isnull=False)
        )
        .exists()
    )
