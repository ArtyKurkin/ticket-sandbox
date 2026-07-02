from html import escape

from sandbox.models import Task, TaskAttempt
from sandbox.services.attempts import task_was_technically_completed
from sandbox.services.telegram import send_telegram
from sandbox.services.trainee_dashboard import LEVEL_ACCESS


def notify_manual_review_required(attempt: TaskAttempt) -> bool:
    """
    Уведомляет наставников, что попытка ждёт ручной проверки.

    Уведомление отправляется только для зачётной попытки,
    которая действительно находится в статусе ON_REVIEW.
    """
    if not attempt.is_credit_attempt:
        return False

    if not attempt.task.requires_manual_review:
        return False

    if attempt.status != TaskAttempt.Status.ON_REVIEW:
        return False

    text = (
        "🔍 <b>Требуется ручная проверка</b>\n\n"
        f"Стажёр: {escape(_get_user_display_name(attempt.user))}\n"
        f"Задача: {escape(attempt.task.title)}\n"
        f"Очередь: {escape(attempt.task.queue.name)}"
    )

    return send_telegram(text)


def notify_user_completed_all_tasks(attempt: TaskAttempt) -> bool:
    """
    Уведомляет наставников, что стажёр технически прошёл все доступные задания.

    Важно:
    - дополнительные тренировочные попытки не учитываем;
    - уведомление отправляем только после технически пройденной попытки;
    - если остались непройденные активные задания в доступных очередях,
      уведомление не отправляем.
    """
    if not attempt.is_credit_attempt:
        return False

    if not attempt.is_technically_completed:
        return False

    if not user_completed_all_available_tasks(attempt.user):
        return False

    text = (
        "🎉 <b>Стажёр прошёл все задания технически</b>\n\n"
        f"Стажёр: {escape(_get_user_display_name(attempt.user))}\n"
        "Все активные задания в доступных очередях завершены технически."
    )

    return send_telegram(text)


def notify_stuck_attempt_detected(
    attempt: TaskAttempt,
    reason: str,
) -> bool:
    """
    Уведомляет наставников, что watchdog нашёл зависшую попытку.

    Это инфраструктурное уведомление, поэтому отправляем его и для зачётных,
    и для тренировочных попыток.
    """
    text = (
        "⚠️ <b>Зависшая попытка переведена в ошибку</b>\n\n"
        f"Стажёр: {escape(_get_user_display_name(attempt.user))}\n"
        f"Задача: {escape(attempt.task.title)}\n"
        f"Очередь: {escape(attempt.task.queue.name)}\n"
        f"Причина: {escape(reason)}"
    )

    return send_telegram(text)


def user_completed_all_available_tasks(user) -> bool:
    """
    Проверяет, прошёл ли пользователь технически все активные задания
    в доступных ему очередях.
    """
    profile = getattr(user, "trainee_profile", None)

    if profile is None:
        return False

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

    if not tasks.exists():
        return False

    for task in tasks:
        if not task_was_technically_completed(
            user=user,
            task=task,
        ):
            return False

    return True


def _get_user_display_name(user) -> str:
    full_name = user.get_full_name().strip()

    if full_name:
        return full_name

    return user.username
