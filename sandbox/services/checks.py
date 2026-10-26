import logging
from dataclasses import dataclass

from sentry_sdk import capture_exception

from django.db import close_old_connections, transaction
from django.core.exceptions import PermissionDenied
from django.db.models import F
from sandbox.services import ledger
from sandbox.services.ledger_execution import checked
from django.utils import timezone

from sandbox.models import CheckRun, TaskAttempt
from .technical_evidence import get_technical_evidence, with_technical_evidence
from sandbox.services.docker_service import (
    check_task_container,
    remove_task_container,
    remove_terminal_container,
)
from sandbox.services.notifications import notify_user_completed_all_tasks
from sandbox.services.completions import record_completion_after_success

terminal_logger = logging.getLogger("sandbox.terminal")

CHECK_STARTED_OUTPUT = "Проверка запущена. Ждем результат..."


@dataclass(frozen=True)
class AttemptCheckResult:
    is_success: bool
    message: str


@transaction.atomic
@ledger.trusted
def mark_attempt_check_running(*, attempt: TaskAttempt) -> None:
    if attempt.technical_passed:
        return
    TaskAttempt.objects.select_for_update().get(pk=attempt.pk)
    ledger.request_check(attempt)
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


@transaction.atomic
@ledger.trusted
def try_mark_attempt_check_running(*, attempt: TaskAttempt, operation_id=None) -> bool:
    """
    Атомарно переводит попытку в running.

    Нужна защита от двойного клика / двух одновременных POST:
    только один запрос должен реально увеличить attempts_count
    и поставить фоновую задачу в очередь.
    """
    if operation_id:
        old=ledger.TechnicalCheckExecution.objects.filter(run_id=ledger.operation_id(operation_id)).first()
        if old:
            if old.attempt_id != attempt.pk: raise PermissionDenied
            return False
    now = timezone.now()

    updated_count = (
        with_technical_evidence(TaskAttempt.objects.filter(id=attempt.id))
        .filter(technical_passed_at__isnull=True, technical_check_id__isnull=True)
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
    if updated_count == 1:
        ledger.request_check(attempt, run_id=operation_id)

    return updated_count == 1


@checked
def run_attempt_check(
    *,
    attempt: TaskAttempt,
    user_id: int,
    mark_as_running: bool = True,
) -> AttemptCheckResult:
    """
    Запускает техническую автопроверку попытки.

    Функция содержит основную синхронную логику проверки
    и может выполняться из Celery worker.
    """
    # Also guard worker/direct calls: an old queued job must not rerun a success.
    attempt.refresh_from_db()
    if get_technical_evidence(attempt, use_cached=False).is_completed:
        return AttemptCheckResult(
            is_success=True,
            message="Техническая часть уже засчитана. Повторная проверка не требуется.",
        )

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

        with transaction.atomic():
            TaskAttempt.objects.select_for_update().get(pk=attempt.pk)
            ledger.check_live(attempt)
            attempt.save(update_fields=["status", "last_check_output", "check_status", "check_finished_at"])
            ledger.finish_check(attempt, failure_class="infrastructure", reason="docker_error", checker_started=getattr(error, "_sandbox_checker_started", None))

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

    if exit_code is None:
        # CheckRun requires a real integer exit code; do not invent one.
        with transaction.atomic():
            TaskAttempt.objects.select_for_update().get(pk=attempt.pk)
            ledger.check_live(attempt)
            attempt.status = TaskAttempt.Status.FAILED
            attempt.check_status = TaskAttempt.CheckStatus.ERROR
            attempt.last_check_output = output
            attempt.check_finished_at = timezone.now()
            attempt.save(update_fields=[
                "status", "check_status", "last_check_output", "check_finished_at",
            ])
            ledger.finish_check(attempt, reason="exit_code_missing")
        return AttemptCheckResult(False, "Результат проверки неизвестен. Обратись к наставнику.")

    if exit_code == 0:
        check_finished_at = timezone.now()

        attempt.technical_passed_at = check_finished_at
        attempt.check_status = TaskAttempt.CheckStatus.PASSED
        attempt.check_finished_at = check_finished_at

        attempt.last_check_output = output

        if attempt.task.requires_manual_review and attempt.is_credit_attempt:
            # Для зачетной попытки оставляем окружение доступным,
            # пока стажер готовит текст ответа наставнику.
            attempt.status = TaskAttempt.Status.IN_PROGRESS
            attempt.finished_at = None

            success_message = (
                "Техническая проверка пройдена. "
                "Теперь подготовь ответ клиенту и внутренний комментарий. "
                "Терминал останется доступен до отправки ответа наставнику."
            )

        else:
            terminal_removed = ""

            if attempt.terminal_container_name:
                _, terminal_removed = remove_terminal_container(
                    attempt.terminal_container_name,
                )

            _, remove_output = remove_task_container(
                container_name=attempt.container_name,
            )

            terminal_logger.info(
                "task_check_cleanup_done "
                "user_id=%s attempt_id=%s task_slug=%s queue_slug=%s "
                "terminal_removed=%s remove_output=%s",
                user_id,
                attempt.id,
                attempt.task.slug,
                attempt.task.queue.slug,
                terminal_removed,
                remove_output,
            )

            attempt.container_id = ""
            attempt.container_name = ""
            attempt.shell_command = ""

            attempt.terminal_container_name = ""
            attempt.terminal_url = ""
            attempt.terminal_port = None

            attempt.status = TaskAttempt.Status.PASSED
            attempt.finished_at = check_finished_at

            if attempt.is_extra_attempt:
                success_message = (
                    "Дополнительная попытка технически пройдена. "
                    "Она не влияет на зачет и не отправляется наставнику "
                    "на ручную проверку."
                )
            else:
                success_message = (
                    "Задание принято. "
                    "Техническая проверка пройдена успешно."
                )

        with transaction.atomic():
            TaskAttempt.objects.select_for_update().get(pk=attempt.pk)
            ledger.check_live(attempt)
            check_run = CheckRun.objects.create(
                attempt=attempt, result=CheckRun.Result.PASSED,
                output=output, exit_code=0,
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

            ledger.finish_check(attempt, result="passed", failure_class="none", exit_code=0, check_run_id=check_run.pk, checker_started=True)
            record_completion_after_success(
                attempt_id=attempt.pk, check_run_id=check_run.pk,
            )
            if attempt.is_credit_attempt and attempt.task.queue.slug == "l1":
                from achievements.services.events import publish
                publish(provider="sandbox_technical", external_id=check_run.pk, user_id=attempt.user_id,
                        context={"program_key": "l1"}, payload={"attempt_id": attempt.pk, "check_run_id": check_run.pk})

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

    with transaction.atomic():
        TaskAttempt.objects.select_for_update().get(pk=attempt.pk)
        ledger.check_live(attempt)
        check_run = CheckRun.objects.create(
            attempt=attempt, result=CheckRun.Result.FAILED,
            output=output, exit_code=exit_code,
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

        # Reserved timeout/launcher codes can also originate inside a checker.
        # Only a confirmed pre-exec exception proves that it never started.
        # Repository checkers declare their binary result with exit 0/1.
        # Other codes may be shell/PHP runtime failures, not task failures.
        ambiguous = exit_code != 1
        if exit_code in (124, 137):
            failure_class, reason = "timeout", "checker_timeout"
        elif exit_code in (125, 126, 127):
            failure_class, reason = "infrastructure", "checker_launch_error"
        elif exit_code == 1:
            failure_class, reason = "technical", ""
        else:
            failure_class, reason = "unknown", "checker_exit_unclassified"
        ledger.finish_check(
            attempt, result="unknown" if ambiguous else "failed",
            failure_class=failure_class, reason=reason, exit_code=exit_code,
            check_run_id=check_run.pk,
            checker_started=True if exit_code == 124 or not ambiguous else None,
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
    operation_id=None,
):
    """
    Атомарно помечает попытку как running
    и ставит автопроверку в очередь Celery.
    """
    from .observation_config import enabled_for
    if enabled_for(attempt):
        return None
    was_marked_running = try_mark_attempt_check_running(
        attempt=attempt,
        operation_id=operation_id,
    )

    if not was_marked_running:
        terminal_logger.info(
            "attempt_check_already_running user_id=%s attempt_id=%s",
            user_id,
            attempt.id,
        )
        return None

    from sandbox.tasks import run_attempt_check_task

    run_id=attempt._ledger_check_id
    def dispatch():
        try:run_attempt_check_task.delay(attempt.id, user_id, run_id=run_id)
        except Exception as error:
            _mark_background_check_error(attempt_id=attempt.pk,user_id=user_id,error=error,run_id=run_id)
            raise
    transaction.on_commit(dispatch)
    return run_id



def _run_attempt_check_background(
    *,
    attempt_id: int,
    user_id: int,
    run_id=None,
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
            run_id=run_id,
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
            run_id=run_id,
        )

    finally:
        close_old_connections()


@transaction.atomic
@ledger.trusted
def _mark_background_check_error(
    *,
    attempt_id: int,
    user_id: int,
    error: Exception,
    run_id=None,
) -> None:
    attempt = TaskAttempt.objects.select_for_update().filter(pk=attempt_id, user_id=user_id).first()
    if attempt is None or get_technical_evidence(attempt, use_cached=False).is_completed or attempt.check_status != TaskAttempt.CheckStatus.RUNNING:
        return
    if run_id:
        execution = ledger.TechnicalCheckExecution.objects.filter(run_id=run_id, attempt_id=attempt_id).first()
        latest = ledger.TechnicalCheckExecution.objects.filter(attempt_id=attempt_id).order_by('-ordinal').first()
        if not execution or execution != latest: return
        attempt._ledger_execution = execution
        ledger.finish_check(attempt, reason='background_error')
    else:
        ledger.interrupt(attempt, 'background_error')
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
