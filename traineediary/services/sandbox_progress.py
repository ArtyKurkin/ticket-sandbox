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


def build_sandbox_queue_progress(
    user,
    queue_slug=L1_QUEUE_SLUG,
):
    """
    Возвращает зачётный прогресс пользователя
    по активным заданиям указанной очереди.

    Учитываются только попытки attempt_number=1.
    Дополнительные тренировочные попытки
    не влияют на готовность.
    """
    queue = (
        Queue.objects
        .filter(
            slug=queue_slug,
            is_active=True,
        )
        .first()
    )

    if queue is None:
        return SandboxQueueProgress(
            queue_exists=False,
            queue_slug=queue_slug,
            queue_name="",
            total_count=0,
            passed_count=0,
            remaining_count=0,
            on_review_count=0,
            progress_percent=0,
            is_ready=False,
        )

    tasks = list(
        Task.objects
        .filter(
            queue=queue,
            is_active=True,
        )
        .order_by("order", "id")
    )

    task_ids = [
        task.id
        for task in tasks
    ]

    credit_attempts = (
        TaskAttempt.objects
        .filter(
            user=user,
            task_id__in=task_ids,
            attempt_number=1,
        )
        .order_by("task_id", "-id")
    )

    attempt_by_task_id = {}

    for attempt in credit_attempts:
        attempt_by_task_id.setdefault(
            attempt.task_id,
            attempt,
        )

    passed_count = 0
    on_review_count = 0

    for task in tasks:
        attempt = attempt_by_task_id.get(
            task.id,
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

    total_count = len(tasks)
    remaining_count = max(
        total_count - passed_count,
        0,
    )

    progress_percent = (
        round(
            passed_count
            / total_count
            * 100,
        )
        if total_count
        else 0
    )

    is_ready = (
        total_count > 0
        and passed_count == total_count
    )

    return SandboxQueueProgress(
        queue_exists=True,
        queue_slug=queue.slug,
        queue_name=queue.name,
        total_count=total_count,
        passed_count=passed_count,
        remaining_count=remaining_count,
        on_review_count=on_review_count,
        progress_percent=progress_percent,
        is_ready=is_ready,
    )
