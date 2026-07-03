import logging
import threading
from dataclasses import dataclass

from sentry_sdk import capture_exception

from django.db import close_old_connections, transaction
from django.db.models import F
from django.utils import timezone

from sandbox.models import CheckRun, TaskAttempt
from sandbox.services.docker_service import (
    check_task_container,
    remove_task_container,
    remove_terminal_container,
)
from sandbox.services.notifications import notify_user_completed_all_tasks

terminal_logger = logging.getLogger("sandbox.terminal")

CHECK_STARTED_OUTPUT = "Проверка запущена. Ждем результат..."


@dataclass(frozen=True)
class AttemptCheckResult:
    is_success: bool
    message: str


def mark_attempt_check_running(*, attempt: TaskAttempt) -> None:
    attempt.attempts_count += 1
    attempt.status = TaskAttempt.Status.IN_PROGRESS
    attempt.check_status = TaskAttempt.CheckStatus.RUNNING
    attempt.check_started_at = timezone.now()
    attempt.check_finished_at = None
    attempt.last_check_output = CHECK_STARTED_OUTPUT

    attempt.save(
        update_fields=[
            "attempts_count",
            "status",
            "check_status",
            "check_started_at",
            "check_finished_at",
            "last_check_output",
        ]
    )


def try_mark_attempt_check_running(*, attempt: TaskAttempt) -> bool:
    """
    Атомарно переводит попытку в running.

    Нужна защита от двойного клика / двух одновременных POST:
    только один запрос должен реально увеличить attempts_count и запустить thread.
    """
    now = timezone.now()

    updated_count = (
        TaskAttempt.objects
        .filter(id=attempt.id)
        .exclude(check_status=TaskAttempt.CheckStatus.RUNNING)
        .update(
            attempts_count=F("attempts_count") + 1,
            status=TaskAttempt.Status.IN_PROGRESS,
            check_status=TaskAttempt.CheckStatus.RUNNING,
            check_started_at=now,
            check_finished_at=None,
            last_check_output=CHECK_STARTED_OUTPUT,
        )
    )

    attempt.refresh_from_db()

    return updated_count == 1


def run_attempt_check(
    *,
    attempt: TaskAttempt,
    user_id: int,
    mark_as_running: bool = True,
) -> AttemptCheckResult:
    """
    Запускает техническую автопроверку попытки.

    Пока выполняется синхронно, но логика уже вынесена из view,
    чтобы следующим шагом запускать её в background thread.
    """
    if mark_as_running:
        mark_attempt_check_running(attempt=attempt)

    try:
        exit_code, output = check_task_container(
            container_name=attempt.container_name,
        )

    except Exception as error:
        output = (
            "Не удалось запустить автопроверку из-за ошибки Docker API.\n\n"
            f"{error}"
        )

        attempt.status = TaskAttempt.Status.FAILED
        attempt.last_check_output = output
        attempt.check_status = TaskAttempt.CheckStatus.ERROR
        attempt.check_finished_at = timezone.now()

        attempt.save(
            update_fields=[
                "status",
                "last_check_output",
                "check_status",
                "check_finished_at",
            ]
        )

        terminal_logger.exception(
            "task_check_docker_error user_id=%s attempt_id=%s task_slug=%s queue_slug=%s container_name=%s",
            user_id,
            attempt.id,
            attempt.task.slug,
            attempt.task.queue.slug,
            attempt.container_name,
        )

        return AttemptCheckResult(
            is_success=False,
            message=(
                "Не удалось запустить автопроверку. "
                "Попробуй перезапустить окружение или обратись к наставнику."
            ),
        )

    CheckRun.objects.create(
        attempt=attempt,
        result=CheckRun.Result.PASSED
        if exit_code == 0
        else CheckRun.Result.FAILED,
        output=output,
        exit_code=exit_code,
    )

    if exit_code == 0:
        check_finished_at = timezone.now()

        attempt.technical_passed_at = check_finished_at
        attempt.check_status = TaskAttempt.CheckStatus.PASSED
        attempt.check_finished_at = check_finished_at

        terminal_removed = ""

        if attempt.terminal_container_name:
            _, terminal_removed = remove_terminal_container(
                attempt.terminal_container_name,
            )

        _, remove_output = remove_task_container(
            container_name=attempt.container_name,
        )

        attempt.last_check_output = (
            f"{output}\n\n"
            f"---\n"
            f"{terminal_removed}\n"
            f"{remove_output}"
        )

        attempt.container_id = ""
        attempt.container_name = ""
        attempt.shell_command = ""

        attempt.terminal_container_name = ""
        attempt.terminal_url = ""
        attempt.terminal_port = None

        if attempt.task.requires_manual_review and attempt.is_credit_attempt:
            attempt.status = TaskAttempt.Status.IN_PROGRESS
            attempt.finished_at = None
            success_message = (
                "Техническая проверка пройдена. "
                "Теперь подготовь ответ клиенту и внутренний комментарий."
            )
        else:
            attempt.status = TaskAttempt.Status.PASSED
            attempt.finished_at = check_finished_at

            if attempt.is_extra_attempt:
                success_message = (
                    "Дополнительная попытка технически пройдена. "
                    "Она не влияет на зачет и не отправляется наставнику на ручную проверку."
                )
            else:
                success_message = (
                    "Задание принято. Техническая проверка пройдена успешно."
                )

        attempt.save(
            update_fields=[
                "status",
                "finished_at",
                "technical_passed_at",
                "last_check_output",
                "container_id",
                "container_name",
                "shell_command",
                "terminal_container_name",
                "terminal_url",
                "terminal_port",
                "check_status",
                "check_finished_at",
            ]
        )

        transaction.on_commit(
            lambda: notify_user_completed_all_tasks(attempt)
        )

        terminal_logger.info(
            "task_check_passed user_id=%s attempt_id=%s task_slug=%s queue_slug=%s exit_code=%s requires_manual_review=%s is_credit_attempt=%s status=%s",
            user_id,
            attempt.id,
            attempt.task.slug,
            attempt.task.queue.slug,
            exit_code,
            attempt.task.requires_manual_review,
            attempt.is_credit_attempt,
            attempt.status,
        )

        return AttemptCheckResult(
            is_success=True,
            message=success_message,
        )

    attempt.status = TaskAttempt.Status.FAILED
    attempt.last_check_output = output
    attempt.check_status = TaskAttempt.CheckStatus.FAILED
    attempt.check_finished_at = timezone.now()

    attempt.save(
        update_fields=[
            "status",
            "last_check_output",
            "check_status",
            "check_finished_at",
        ]
    )

    terminal_logger.info(
        "task_check_failed user_id=%s attempt_id=%s task_slug=%s queue_slug=%s exit_code=%s",
        user_id,
        attempt.id,
        attempt.task.slug,
        attempt.task.queue.slug,
        exit_code,
    )

    return AttemptCheckResult(
        is_success=False,
        message="Автопроверка не пройдена. Посмотри результат проверки и доработай тикет.",
    )


def start_attempt_check_in_background(
    *,
    attempt: TaskAttempt,
    user_id: int,
) -> threading.Thread | None:
    """
    Атомарно помечает попытку как running и запускает автопроверку в отдельном thread.

    Это промежуточное решение до Celery/Redis.
    """
    was_marked_running = try_mark_attempt_check_running(attempt=attempt)

    if not was_marked_running:
        terminal_logger.info(
            "attempt_check_already_running user_id=%s attempt_id=%s",
            user_id,
            attempt.id,
        )
        return None

    thread = threading.Thread(
        target=_run_attempt_check_background,
        kwargs={
            "attempt_id": attempt.id,
            "user_id": user_id,
        },
        name=f"attempt-check-{attempt.id}",
        daemon=True,
    )
    thread.start()

    return thread


def _run_attempt_check_background(
    *,
    attempt_id: int,
    user_id: int,
) -> None:
    close_old_connections()

    try:
        attempt = (
            TaskAttempt.objects
            .select_related("task", "task__queue")
            .get(id=attempt_id)
        )

        run_attempt_check(
            attempt=attempt,
            user_id=user_id,
            mark_as_running=False,
        )

    except TaskAttempt.DoesNotExist:
        terminal_logger.warning(
            "attempt_check_background_missing attempt_id=%s user_id=%s",
            attempt_id,
            user_id,
        )

    except Exception as error:
        capture_exception(error)

        _mark_background_check_error(
            attempt_id=attempt_id,
            user_id=user_id,
            error=error,
        )

    finally:
        close_old_connections()


def _mark_background_check_error(
    *,
    attempt_id: int,
    user_id: int,
    error: Exception,
) -> None:
    output = (
        "Неожиданная ошибка фоновой автопроверки.\n\n"
        f"{error}"
    )

    updated_count = TaskAttempt.objects.filter(
        id=attempt_id,
    ).update(
        status=TaskAttempt.Status.FAILED,
        last_check_output=output,
        check_status=TaskAttempt.CheckStatus.ERROR,
        check_finished_at=timezone.now(),
    )

    terminal_logger.exception(
        "attempt_check_background_error user_id=%s attempt_id=%s updated=%s",
        user_id,
        attempt_id,
        updated_count,
    )
