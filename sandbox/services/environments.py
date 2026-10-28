import logging
from django.conf import settings

from sentry_sdk import capture_exception

from django.db import close_old_connections, transaction
from sandbox.services import ledger
from sandbox.services.ledger_execution import environment
from django.utils import timezone

from sandbox.models import TaskAttempt
from sandbox.services.docker_service import (
    create_task_container,
    create_terminal_container,
    get_free_port,
    remove_task_container,
    remove_terminal_container,
    wait_for_terminal_ready,
    task_resource_name,
)
from sandbox.services.terminal_gateway import (
    build_terminal_base_path,
    build_terminal_url,
    terminal_gateway_enabled,
    terminal_uses_docker_network,
)

environment_logger = logging.getLogger("sandbox.terminal")


ENVIRONMENT_STARTING_OUTPUT = (
    "Окружение запускается. Это может занять несколько секунд..."
)

ENVIRONMENT_RESTARTING_OUTPUT = (
    "Окружение перезапускается. Это может занять несколько секунд..."
)


def _pin_broker_environment(attempt, container):
    if not settings.TERMINAL_BROKER_ENABLED:
        return
    # Persist ownership before the broker/ttyd launch can fail. Error cleanup
    # can then find the exact generation, even after a worker crash.
    attempt.environment_generation = container.labels["ticket-sandbox.generation"]
    attempt.container_id = container.id
    attempt.container_name = container.name
    attempt.terminal_container_name = task_resource_name(
        attempt.task.queue.slug, attempt.task.slug, attempt.pk, terminal=True)
    attempt.save(update_fields=["environment_generation", "container_id", "container_name", "terminal_container_name"])


def cleanup_attempt_environment(attempt):
    """
    Best-effort cleanup Docker-окружения попытки.

    Ошибка Docker API не должна мешать отправке текстового ответа наставнику.
    Поля конкретного контейнера очищаются только после успешного удаления
    или если Docker сообщил, что контейнер уже отсутствует.
    """
    if attempt.environment_generation:
        from .terminal_lite import cleanup
        from .terminal_teardown import IdentityError, TeardownPending
        import docker
        from .terminal_lite import OperationBusy
        try:
            return cleanup(attempt)
        except IdentityError:
            environment_logger.exception('broker_cleanup_identity_error attempt_id=%s', attempt.pk)
            return False
        except (docker.errors.DockerException, OSError, OperationBusy, TeardownPending):
            environment_logger.exception('broker_cleanup_pending attempt_id=%s', attempt.pk)
            from sandbox.tasks import cleanup_broker_environment_task
            def retry_cleanup():
                try:
                    cleanup_broker_environment_task.delay(attempt.pk)
                except Exception:
                    environment_logger.exception('broker_cleanup_dispatch_failed attempt_id=%s', attempt.pk)
            transaction.on_commit(retry_cleanup)
            return False
    update_fields = []

    if attempt.terminal_container_name:
        try:
            remove_terminal_container(
                attempt.terminal_container_name
            )
        except Exception as error:
            capture_exception(error)

            environment_logger.exception(
                "task_terminal_cleanup_error "
                "attempt_id=%s terminal_container_name=%s",
                attempt.id,
                attempt.terminal_container_name,
            )
        else:
            attempt.terminal_container_name = ""
            attempt.terminal_url = ""
            attempt.terminal_port = None

            update_fields.extend([
                "terminal_container_name",
                "terminal_url",
                "terminal_port",
            ])

    elif attempt.terminal_url or attempt.terminal_port is not None:
        attempt.terminal_url = ""
        attempt.terminal_port = None

        update_fields.extend([
            "terminal_url",
            "terminal_port",
        ])

    if attempt.container_name:
        try:
            remove_task_container(
                attempt.container_name
            )
        except Exception as error:
            capture_exception(error)

            environment_logger.exception(
                "task_container_cleanup_error "
                "attempt_id=%s container_name=%s",
                attempt.id,
                attempt.container_name,
            )
        else:
            attempt.container_id = ""
            attempt.container_name = ""
            attempt.shell_command = ""

            update_fields.extend([
                "container_id",
                "container_name",
                "shell_command",
            ])

    elif attempt.container_id or attempt.shell_command:
        attempt.container_id = ""
        attempt.shell_command = ""

        update_fields.extend([
            "container_id",
            "shell_command",
        ])

    cleanup_complete = (
        not attempt.container_name
        and not attempt.terminal_container_name
    )

    if cleanup_complete:
        attempt.environment_status = (
            TaskAttempt.EnvironmentStatus.IDLE
        )
        attempt.environment_started_at = None
        attempt.environment_finished_at = None

        update_fields.extend([
            "environment_status",
            "environment_started_at",
            "environment_finished_at",
        ])

    if update_fields:
        attempt.save(
            update_fields=list(dict.fromkeys(update_fields))
        )

    return cleanup_complete


@transaction.atomic
@ledger.trusted
def mark_environment_starting(attempt, *, actor=None, origin="unknown", operation_id=None):
    ledger.request_environment(attempt,"start",actor,origin,operation_id)
    now = timezone.now()

    attempt.environment_status = TaskAttempt.EnvironmentStatus.STARTING
    attempt.environment_started_at = now
    attempt.environment_finished_at = None
    attempt.last_check_output = ENVIRONMENT_STARTING_OUTPUT
    attempt.stuck_reason = TaskAttempt.StuckReason.NONE

    attempt.save(
        update_fields=[
            "environment_status",
            "environment_started_at",
            "environment_finished_at",
            "last_check_output",
            "stuck_reason",
        ]
    )


@transaction.atomic
@ledger.trusted
def try_mark_environment_starting(attempt, *, actor=None, origin="unknown", operation_id=None):
    if settings.TERMINAL_BROKER_ENABLED:
        current = TaskAttempt.objects.select_for_update().get(pk=attempt.pk)
        if current.environment_operation.get('stage') in ('teardown', 'create', 'terminal'):
            return False
    event,created=ledger.request_environment(attempt,"start",actor,origin,operation_id)
    if not created:return False
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
            stuck_reason=TaskAttempt.StuckReason.NONE,
        )
    )

    if updated_count == 0:
        ledger.environment_phase(event,"finished",outcome="not_started",reason="already_running")
        return False

    attempt.environment_status = TaskAttempt.EnvironmentStatus.STARTING
    attempt.environment_started_at = now
    attempt.environment_finished_at = None
    attempt.stuck_reason = TaskAttempt.StuckReason.NONE
    attempt.last_check_output = ENVIRONMENT_STARTING_OUTPUT

    return True


@transaction.atomic
@ledger.trusted
def mark_environment_restarting(attempt, *, actor=None, origin="unknown", operation_id=None):
    ledger.request_environment(attempt,"reset",actor,origin,operation_id)
    now = timezone.now()

    attempt.environment_status = TaskAttempt.EnvironmentStatus.RESTARTING
    attempt.environment_started_at = now
    attempt.environment_finished_at = None
    attempt.finished_at = None
    attempt.last_check_output = ENVIRONMENT_RESTARTING_OUTPUT
    attempt.stuck_reason = TaskAttempt.StuckReason.NONE

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
            "stuck_reason",
        ]
    )


@transaction.atomic
@ledger.trusted
def try_mark_environment_restarting(attempt, *, actor=None, origin="unknown", operation_id=None):
    if settings.TERMINAL_BROKER_ENABLED:
        current = TaskAttempt.objects.select_for_update().get(pk=attempt.pk)
        if current.environment_operation.get('stage') in ('teardown', 'create', 'terminal'):
            return False
    event,created=ledger.request_environment(attempt,"reset",actor,origin,operation_id)
    if not created:return False
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
            stuck_reason=TaskAttempt.StuckReason.NONE,
        )
    )

    if updated_count == 0:
        ledger.environment_phase(event,"finished",outcome="not_started",reason="already_running")
        return False

    attempt.environment_status = TaskAttempt.EnvironmentStatus.RESTARTING
    attempt.environment_started_at = now
    attempt.environment_finished_at = None
    attempt.finished_at = None
    attempt.stuck_reason = TaskAttempt.StuckReason.NONE
    attempt.last_check_output = ENVIRONMENT_RESTARTING_OUTPUT

    attempt.check_status = TaskAttempt.CheckStatus.IDLE
    attempt.check_started_at = None
    attempt.check_finished_at = None

    return True


@environment("start")
def run_environment_start(attempt):
    container = create_task_container(
        queue_slug=attempt.task.queue.slug,
        task_slug=attempt.task.slug,
        attempt_id=attempt.id,
    )
    _pin_broker_environment(attempt, container)
    from .observation_config import capture_runtime
    observation_runtime = capture_runtime(attempt, container)
    if observation_runtime is not None:
        attempt.http_observation_runtime = observation_runtime

    terminal_port = (
        None
        if terminal_uses_docker_network()
        else get_free_port()
    )

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

    wait_for_terminal_ready(
        terminal_container_name=terminal_container.name,
        port=terminal_port,
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

    with transaction.atomic():
        TaskAttempt.objects.select_for_update().get(pk=attempt.pk)
        request=ledger.environment_live(attempt)
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
                *(["http_observation_runtime"] if observation_runtime is not None else []),
            ]
        )
        if request:ledger.environment_phase(request,"finished",outcome="success")

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


@environment("reset")
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
    _pin_broker_environment(attempt, container)
    from .observation_config import capture_runtime
    observation_runtime = capture_runtime(attempt, container)
    if observation_runtime is not None:
        attempt.http_observation_runtime = observation_runtime

    terminal_port = (
        None
        if terminal_uses_docker_network()
        else get_free_port()
    )

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

    wait_for_terminal_ready(
        terminal_container_name=terminal_container.name,
        port=terminal_port,
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

    with transaction.atomic():
        TaskAttempt.objects.select_for_update().get(pk=attempt.pk)
        request=ledger.environment_live(attempt)
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
                *(["http_observation_runtime"] if observation_runtime is not None else []),
            ]
        )
        if request:ledger.environment_phase(request,"finished",outcome="success")

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


@transaction.atomic
@ledger.trusted
def mark_environment_start_error(attempt, error):
    fresh=TaskAttempt.objects.select_for_update().get(pk=attempt.pk)
    if fresh.environment_status not in (TaskAttempt.EnvironmentStatus.STARTING, TaskAttempt.EnvironmentStatus.RESTARTING):
        if fresh.technical_passed or ledger.SandboxEnvironmentEvent.objects.filter(attempt_id=attempt.pk).exists():return
        ledger.gap(attempt.pk,'legacy_environment_delivery')
        ledger.request_environment(attempt,"start",origin='unknown')
    ledger.interrupt(attempt,"environment_error")
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


@transaction.atomic
@ledger.trusted
def mark_environment_restart_error(attempt, error):
    fresh=TaskAttempt.objects.select_for_update().get(pk=attempt.pk)
    if fresh.environment_status not in (TaskAttempt.EnvironmentStatus.STARTING, TaskAttempt.EnvironmentStatus.RESTARTING):
        if fresh.technical_passed or ledger.SandboxEnvironmentEvent.objects.filter(attempt_id=attempt.pk).exists():return
        ledger.gap(attempt.pk,'legacy_environment_delivery')
        ledger.request_environment(attempt,"reset",origin='unknown')
    ledger.interrupt(attempt,"environment_error")
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


def start_environment_in_background(attempt_id, operation_id=None):
    if operation_id is None:
        attempt=TaskAttempt.objects.select_related('task','task__queue').get(pk=attempt_id)
        request,_=ledger.request_environment(attempt,"start",origin='unknown')
        operation_id=str(request.operation_id)
    from sandbox.tasks import start_environment_task

    def dispatch():
        try:
            start_environment_task.delay(attempt_id, operation_id=operation_id)
        except Exception as error:
            attempt=TaskAttempt.objects.get(pk=attempt_id)
            with transaction.atomic():
                request=ledger.SandboxEnvironmentEvent.objects.filter(operation_id=operation_id,phase='requested').first()
                if request:ledger.environment_phase(request,'finished',reason='dispatch_error')
                mark_environment_start_error(attempt,error)
            raise
    transaction.on_commit(dispatch)
    return operation_id


def _run_environment_start_background(attempt_id, operation_id=None):
    close_old_connections()

    try:
        attempt = (
            TaskAttempt.objects
            .select_related("task", "task__queue", "user")
            .get(id=attempt_id)
        )

        run_environment_start(attempt, operation_id=operation_id)

    except Exception as error:
        capture_exception(error)

        _mark_background_environment_start_error(
            attempt_id=attempt_id,
            error=error,
            operation_id=operation_id,
        )

    finally:
        close_old_connections()


def _mark_background_environment_start_error(attempt_id, error, operation_id=None):
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

    if operation_id:
        latest=ledger.SandboxEnvironmentEvent.objects.filter(attempt_id=attempt_id,phase='requested').order_by('-pk').first()
        if latest is None or str(latest.operation_id)!=str(operation_id):return
    try:
        mark_environment_start_error(attempt, error)

    finally:
        close_old_connections()


def start_environment_restart_in_background(attempt_id, operation_id=None):
    if operation_id is None:
        attempt=TaskAttempt.objects.select_related('task','task__queue').get(pk=attempt_id)
        request,_=ledger.request_environment(attempt,"reset",origin='unknown')
        operation_id=str(request.operation_id)
    from sandbox.tasks import restart_environment_task

    def dispatch():
        try:
            restart_environment_task.delay(attempt_id, operation_id=operation_id)
        except Exception as error:
            attempt=TaskAttempt.objects.get(pk=attempt_id)
            with transaction.atomic():
                request=ledger.SandboxEnvironmentEvent.objects.filter(operation_id=operation_id,phase='requested').first()
                if request:ledger.environment_phase(request,'finished',reason='dispatch_error')
                mark_environment_restart_error(attempt,error)
            raise
    transaction.on_commit(dispatch)
    return operation_id


def _run_environment_restart_background(attempt_id, operation_id=None):
    close_old_connections()

    try:
        attempt = (
            TaskAttempt.objects
            .select_related("task", "task__queue", "user")
            .get(id=attempt_id)
        )

        run_environment_restart(attempt, operation_id=operation_id)

    except Exception as error:
        capture_exception(error)

        _mark_background_environment_restart_error(
            attempt_id=attempt_id,
            error=error,
            operation_id=operation_id,
        )

    finally:
        close_old_connections()


def _mark_background_environment_restart_error(attempt_id, error, operation_id=None):
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

    if operation_id:
        latest=ledger.SandboxEnvironmentEvent.objects.filter(attempt_id=attempt_id,phase='requested').order_by('-pk').first()
        if latest is None or str(latest.operation_id)!=str(operation_id):return
    try:
        mark_environment_restart_error(attempt, error)

    finally:
        close_old_connections()
