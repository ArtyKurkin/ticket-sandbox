import logging
import threading

from django.db import close_old_connections
from django.utils import timezone

from sandbox.models import TaskAttempt
from sandbox.services.docker_service import (
    create_task_container,
    create_terminal_container,
    get_free_port,
    remove_task_container,
    remove_terminal_container,
)
from sandbox.services.terminal_gateway import (
    build_terminal_base_path,
    build_terminal_url,
    terminal_gateway_enabled,
)

environment_logger = logging.getLogger("sandbox.terminal")


ENVIRONMENT_STARTING_OUTPUT = (
    "Окружение запускается. Это может занять несколько секунд..."
)

ENVIRONMENT_RESTARTING_OUTPUT = (
    "Окружение перезапускается. Это может занять несколько секунд..."
)


def mark_environment_starting(attempt):
    now = timezone.now()

    attempt.environment_status = TaskAttempt.EnvironmentStatus.STARTING
    attempt.environment_started_at = now
    attempt.environment_finished_at = None
    attempt.last_check_output = ENVIRONMENT_STARTING_OUTPUT

    attempt.save(
        update_fields=[
            "environment_status",
            "environment_started_at",
            "environment_finished_at",
            "last_check_output",
        ]
    )


def try_mark_environment_starting(attempt):
    now = timezone.now()

    updated_count = (
        TaskAttempt.objects
        .filter(id=attempt.id)
        .exclude(
            environment_status__in=[
                TaskAttempt.EnvironmentStatus.STARTING,
                TaskAttempt.EnvironmentStatus.RESTARTING,
            ]
        )
        .update(
            environment_status=TaskAttempt.EnvironmentStatus.STARTING,
            environment_started_at=now,
            environment_finished_at=None,
            last_check_output=ENVIRONMENT_STARTING_OUTPUT,
        )
    )

    if updated_count == 0:
        return False

    attempt.environment_status = TaskAttempt.EnvironmentStatus.STARTING
    attempt.environment_started_at = now
    attempt.environment_finished_at = None
    attempt.last_check_output = ENVIRONMENT_STARTING_OUTPUT

    return True


def mark_environment_restarting(attempt):
    now = timezone.now()

    attempt.environment_status = TaskAttempt.EnvironmentStatus.RESTARTING
    attempt.environment_started_at = now
    attempt.environment_finished_at = None
    attempt.finished_at = None
    attempt.last_check_output = ENVIRONMENT_RESTARTING_OUTPUT

    attempt.check_status = TaskAttempt.CheckStatus.IDLE
    attempt.check_started_at = None
    attempt.check_finished_at = None

    attempt.save(
        update_fields=[
            "environment_status",
            "environment_started_at",
            "environment_finished_at",
            "last_check_output",
            "check_status",
            "check_started_at",
            "check_finished_at",
            "finished_at",
        ]
    )


def try_mark_environment_restarting(attempt):
    now = timezone.now()

    updated_count = (
        TaskAttempt.objects
        .filter(id=attempt.id)
        .exclude(
            environment_status__in=[
                TaskAttempt.EnvironmentStatus.STARTING,
                TaskAttempt.EnvironmentStatus.RESTARTING,
            ]
        )
        .update(
            environment_status=TaskAttempt.EnvironmentStatus.RESTARTING,
            environment_started_at=now,
            environment_finished_at=None,
            finished_at=None,
            last_check_output=ENVIRONMENT_RESTARTING_OUTPUT,
            check_status=TaskAttempt.CheckStatus.IDLE,
            check_started_at=None,
            check_finished_at=None,
        )
    )

    if updated_count == 0:
        return False

    attempt.environment_status = TaskAttempt.EnvironmentStatus.RESTARTING
    attempt.environment_started_at = now
    attempt.environment_finished_at = None
    attempt.finished_at = None
    attempt.last_check_output = ENVIRONMENT_RESTARTING_OUTPUT

    attempt.check_status = TaskAttempt.CheckStatus.IDLE
    attempt.check_started_at = None
    attempt.check_finished_at = None

    return True


def run_environment_start(attempt):
    container = create_task_container(
        queue_slug=attempt.task.queue.slug,
        task_slug=attempt.task.slug,
        attempt_id=attempt.id,
    )

    terminal_port = get_free_port()

    terminal_container = create_terminal_container(
        queue_slug=attempt.task.queue.slug,
        task_slug=attempt.task.slug,
        attempt_id=attempt.id,
        target_container_name=container.name,
        port=terminal_port,
        base_path=build_terminal_base_path(
            attempt_id=attempt.id,
            port=terminal_port,
        ),
    )

    attempt.status = TaskAttempt.Status.IN_PROGRESS
    attempt.started_at = timezone.now()

    attempt.container_id = container.id
    attempt.container_name = container.name

    attempt.terminal_container_name = terminal_container.name
    attempt.terminal_port = terminal_port

    attempt.terminal_url = build_terminal_url(
        attempt_id=attempt.id,
        port=terminal_port,
    )

    attempt.shell_command = f"docker exec -it {container.name} bash"

    attempt.last_check_output = (
        f"Контейнер {container.name} успешно создан."
    )

    attempt.environment_status = TaskAttempt.EnvironmentStatus.READY
    attempt.environment_finished_at = timezone.now()

    attempt.save(
        update_fields=[
            "status",
            "started_at",
            "container_id",
            "container_name",
            "terminal_container_name",
            "terminal_port",
            "terminal_url",
            "shell_command",
            "last_check_output",
            "environment_status",
            "environment_finished_at",
        ]
    )

    environment_logger.info(
        "task_environment_started user_id=%s attempt_id=%s task_slug=%s queue_slug=%s container_name=%s terminal_container_name=%s terminal_port=%s terminal_gateway_enabled=%s",
        attempt.user_id,
        attempt.id,
        attempt.task.slug,
        attempt.task.queue.slug,
        attempt.container_name,
        attempt.terminal_container_name,
        attempt.terminal_port,
        terminal_gateway_enabled(),
    )

    return attempt


def run_environment_restart(attempt):
    old_terminal_container_name = attempt.terminal_container_name
    old_container_name = attempt.container_name

    if old_terminal_container_name:
        remove_terminal_container(old_terminal_container_name)

    if old_container_name:
        remove_task_container(old_container_name)

    container = create_task_container(
        queue_slug=attempt.task.queue.slug,
        task_slug=attempt.task.slug,
        attempt_id=attempt.id,
    )

    terminal_port = get_free_port()

    terminal_container = create_terminal_container(
        queue_slug=attempt.task.queue.slug,
        task_slug=attempt.task.slug,
        attempt_id=attempt.id,
        target_container_name=container.name,
        port=terminal_port,
        base_path=build_terminal_base_path(
            attempt_id=attempt.id,
            port=terminal_port,
        ),
    )

    attempt.status = TaskAttempt.Status.IN_PROGRESS
    attempt.restart_count = (attempt.restart_count or 0) + 1
    attempt.started_at = timezone.now()
    attempt.finished_at = None

    attempt.container_id = container.id
    attempt.container_name = container.name

    attempt.terminal_container_name = terminal_container.name
    attempt.terminal_port = terminal_port

    attempt.terminal_url = build_terminal_url(
        attempt_id=attempt.id,
        port=terminal_port,
    )

    attempt.shell_command = f"docker exec -it {container.name} bash"

    attempt.last_check_output = (
        f"Контейнер {container.name} перезапущен. "
        f"Окружение задания возвращено в начальное состояние."
    )

    attempt.check_status = TaskAttempt.CheckStatus.IDLE
    attempt.check_started_at = None
    attempt.check_finished_at = None

    attempt.environment_status = TaskAttempt.EnvironmentStatus.READY
    attempt.environment_finished_at = timezone.now()

    attempt.save(
        update_fields=[
            "status",
            "restart_count",
            "started_at",
            "finished_at",
            "container_id",
            "container_name",
            "terminal_container_name",
            "terminal_port",
            "terminal_url",
            "shell_command",
            "last_check_output",
            "check_status",
            "check_started_at",
            "check_finished_at",
            "environment_status",
            "environment_finished_at",
        ]
    )

    environment_logger.info(
        "task_environment_restarted user_id=%s attempt_id=%s task_slug=%s queue_slug=%s restart_count=%s container_name=%s terminal_container_name=%s terminal_port=%s terminal_gateway_enabled=%s",
        attempt.user_id,
        attempt.id,
        attempt.task.slug,
        attempt.task.queue.slug,
        attempt.restart_count,
        attempt.container_name,
        attempt.terminal_container_name,
        attempt.terminal_port,
        terminal_gateway_enabled(),
    )

    return attempt


def mark_environment_start_error(attempt, error):
    attempt.status = TaskAttempt.Status.FAILED
    attempt.environment_status = TaskAttempt.EnvironmentStatus.ERROR
    attempt.environment_finished_at = timezone.now()
    attempt.last_check_output = (
        "Не удалось запустить окружение задания из-за ошибки Docker API.\n\n"
        f"{error}"
    )

    attempt.save(
        update_fields=[
            "status",
            "environment_status",
            "environment_finished_at",
            "last_check_output",
        ]
    )

    environment_logger.error(
        "task_environment_start_failed user_id=%s attempt_id=%s task_slug=%s queue_slug=%s error=%s",
        attempt.user_id,
        attempt.id,
        attempt.task.slug,
        attempt.task.queue.slug,
        error,
    )


def mark_environment_restart_error(attempt, error):
    attempt.status = TaskAttempt.Status.FAILED
    attempt.environment_status = TaskAttempt.EnvironmentStatus.ERROR
    attempt.environment_finished_at = timezone.now()
    attempt.last_check_output = (
        "Не удалось перезапустить окружение из-за ошибки Docker API.\n\n"
        f"{error}"
    )

    attempt.save(
        update_fields=[
            "status",
            "environment_status",
            "environment_finished_at",
            "last_check_output",
        ]
    )

    environment_logger.error(
        "task_environment_restart_failed user_id=%s attempt_id=%s task_slug=%s queue_slug=%s container_name=%s terminal_container_name=%s error=%s",
        attempt.user_id,
        attempt.id,
        attempt.task.slug,
        attempt.task.queue.slug,
        attempt.container_name,
        attempt.terminal_container_name,
        error,
    )


def start_environment_in_background(attempt_id):
    thread = threading.Thread(
        target=_run_environment_start_background,
        args=(attempt_id,),
        daemon=True,
    )
    thread.start()


def _run_environment_start_background(attempt_id):
    close_old_connections()

    try:
        attempt = (
            TaskAttempt.objects
            .select_related("task", "task__queue", "user")
            .get(id=attempt_id)
        )

        run_environment_start(attempt)

    except Exception as error:
        _mark_background_environment_start_error(
            attempt_id=attempt_id,
            error=error,
        )

    finally:
        close_old_connections()


def _mark_background_environment_start_error(attempt_id, error):
    close_old_connections()

    try:
        attempt = (
            TaskAttempt.objects
            .select_related("task", "task__queue", "user")
            .get(id=attempt_id)
        )

    except TaskAttempt.DoesNotExist:
        environment_logger.warning(
            "task_environment_start_error_attempt_missing attempt_id=%s error=%s",
            attempt_id,
            error,
        )
        return

    try:
        mark_environment_start_error(attempt, error)

    finally:
        close_old_connections()


def start_environment_restart_in_background(attempt_id):
    thread = threading.Thread(
        target=_run_environment_restart_background,
        args=(attempt_id,),
        daemon=True,
    )
    thread.start()


def _run_environment_restart_background(attempt_id):
    close_old_connections()

    try:
        attempt = (
            TaskAttempt.objects
            .select_related("task", "task__queue", "user")
            .get(id=attempt_id)
        )

        run_environment_restart(attempt)

    except Exception as error:
        _mark_background_environment_restart_error(
            attempt_id=attempt_id,
            error=error,
        )

    finally:
        close_old_connections()


def _mark_background_environment_restart_error(attempt_id, error):
    close_old_connections()

    try:
        attempt = (
            TaskAttempt.objects
            .select_related("task", "task__queue", "user")
            .get(id=attempt_id)
        )

    except TaskAttempt.DoesNotExist:
        environment_logger.warning(
            "task_environment_restart_error_attempt_missing attempt_id=%s error=%s",
            attempt_id,
            error,
        )
        return

    try:
        mark_environment_restart_error(attempt, error)

    finally:
        close_old_connections()
