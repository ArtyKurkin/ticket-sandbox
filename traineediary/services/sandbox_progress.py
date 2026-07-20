from dataclasses import dataclass

from sandbox.models import (
    Queue,
    Task,
    TaskAttempt,
)


L1_QUEUE_SLUG = "l1"


@dataclass(frozen=True)
class SandboxQueueProgress:
    queue_exists: bool
    queue_slug: str
    queue_name: str
    total_count: int
    passed_count: int
    remaining_count: int
    on_review_count: int
    progress_percent: int
    is_ready: bool


def _empty_progress(
    queue_slug,
    *,
    queue_exists=False,
    queue_name="",
):
    return SandboxQueueProgress(
        queue_exists=queue_exists,
        queue_slug=queue_slug,
        queue_name=queue_name,
        total_count=0,
        passed_count=0,
        remaining_count=0,
        on_review_count=0,
        progress_percent=0,
        is_ready=False,
    )


def build_sandbox_queue_progress_map(
    users,
    queue_slug=L1_QUEUE_SLUG,
):
    """
    Возвращает прогресс по очереди сразу для нескольких
    пользователей.

    Результат имеет формат:

        {
            user_id: SandboxQueueProgress(...),
        }

    Учитываются только зачётные попытки
    с attempt_number=1.
    """
    users = [
        user
        for user in users
        if user.pk is not None
    ]

    if not users:
        return {}

    queue = (
        Queue.objects
        .filter(
            slug=queue_slug,
            is_active=True,
        )
        .first()
    )

    if queue is None:
        return {
            user.pk: _empty_progress(
                queue_slug,
            )
            for user in users
        }

    tasks = list(
        Task.objects
        .filter(
            queue=queue,
            is_active=True,
        )
        .order_by("order", "id")
    )

    if not tasks:
        return {
            user.pk: _empty_progress(
                queue_slug,
                queue_exists=True,
                queue_name=queue.name,
            )
            for user in users
        }

    user_ids = [
        user.pk
        for user in users
    ]
    task_ids = [
        task.pk
        for task in tasks
    ]

    credit_attempts = (
        TaskAttempt.objects
        .filter(
            user_id__in=user_ids,
            task_id__in=task_ids,
            attempt_number=1,
        )
        .order_by(
            "user_id",
            "task_id",
            "-id",
        )
    )

    attempt_by_user_and_task = {}

    for attempt in credit_attempts:
        attempt_by_user_and_task.setdefault(
            (
                attempt.user_id,
                attempt.task_id,
            ),
            attempt,
        )

    total_count = len(tasks)
    progress_by_user_id = {}

    for user in users:
        passed_count = 0
        on_review_count = 0

        for task in tasks:
            attempt = (
                attempt_by_user_and_task.get(
                    (
                        user.pk,
                        task.pk,
                    ),
                )
            )

            if attempt is None:
                continue

            if (
                attempt.status
                == TaskAttempt.Status.PASSED
            ):
                passed_count += 1

            elif (
                attempt.status
                == TaskAttempt.Status.ON_REVIEW
            ):
                on_review_count += 1

        remaining_count = max(
            total_count - passed_count,
            0,
        )

        progress_percent = round(
            passed_count
            / total_count
            * 100,
        )

        progress_by_user_id[user.pk] = (
            SandboxQueueProgress(
                queue_exists=True,
                queue_slug=queue.slug,
                queue_name=queue.name,
                total_count=total_count,
                passed_count=passed_count,
                remaining_count=remaining_count,
                on_review_count=on_review_count,
                progress_percent=progress_percent,
                is_ready=(
                    passed_count == total_count
                ),
            )
        )

    return progress_by_user_id


def build_sandbox_queue_progress(
    user,
    queue_slug=L1_QUEUE_SLUG,
):
    progress_by_user_id = (
        build_sandbox_queue_progress_map(
            users=[user],
            queue_slug=queue_slug,
        )
    )

    return progress_by_user_id.get(
        user.pk,
        _empty_progress(queue_slug),
    )
