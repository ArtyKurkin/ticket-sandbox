from celery import shared_task


@shared_task(name="sandbox.celery_ping")
def celery_ping():
    return "pong"


@shared_task(name="sandbox.start_environment", bind=True, acks_late=True, reject_on_worker_lost=True, max_retries=8)
def start_environment_task(self, attempt_id, operation_id=None):
    if _lite_delivery(self, attempt_id, 'start', operation_id):
        return
    from sandbox.services.environments import (
        _run_environment_start_background,
    )

    _run_environment_start_background(attempt_id, operation_id=operation_id)


@shared_task(name="sandbox.restart_environment", bind=True, acks_late=True, reject_on_worker_lost=True, max_retries=8)
def restart_environment_task(self, attempt_id, operation_id=None):
    if _lite_delivery(self, attempt_id, 'reset', operation_id):
        return
    from sandbox.services.environments import (
        _run_environment_restart_background,
    )

    _run_environment_restart_background(attempt_id, operation_id=operation_id)


def _lite_delivery(task, attempt_id, kind, operation_id):
    from django.conf import settings
    from sandbox.models import TaskAttempt
    from sandbox.services.terminal_lite import run, OperationBusy
    from sandbox.services.terminal_teardown import IdentityError, TeardownPending
    import docker
    if not settings.TERMINAL_BROKER_ENABLED:
        return False
    attempt = TaskAttempt.objects.select_related('task__queue', 'user').get(pk=attempt_id)
    try:
        run(attempt, kind, operation_id)
    except IdentityError:
        raise
    except (docker.errors.DockerException, OSError, OperationBusy, TeardownPending) as exc:
        raise task.retry(exc=exc, countdown=min(60, 2 ** task.request.retries))
    return True


@shared_task(name='sandbox.cleanup_broker_environment', bind=True, acks_late=True,
             reject_on_worker_lost=True, max_retries=8)
def cleanup_broker_environment_task(self, attempt_id):
    from sandbox.models import TaskAttempt
    from sandbox.services.terminal_lite import cleanup, OperationBusy
    from sandbox.services.terminal_teardown import TeardownPending
    import docker
    try:
        cleanup(TaskAttempt.objects.select_related('task__queue').get(pk=attempt_id))
    except (docker.errors.DockerException, OSError, OperationBusy, TeardownPending) as exc:
        raise self.retry(exc=exc, countdown=min(60, 2 ** self.request.retries))


@shared_task(name='sandbox.reconcile_broker_environments', ignore_result=True)
def reconcile_broker_environments():
    from django.conf import settings
    from django.db.models import Exists, OuterRef
    from sandbox.services import ledger
    from sandbox.models import TaskAttempt
    for pk in TaskAttempt.objects.filter(environment_cleanup_requested=True).exclude(environment_status='idle').values_list('pk', flat=True):
        cleanup_broker_environment_task.delay(pk)
    for attempt in TaskAttempt.objects.exclude(environment_generation=None).only('pk', 'environment_operation').iterator():
        if attempt.environment_operation.get('retired'):
            reap_retired_broker_resources.delay(attempt.pk)
    if not settings.TERMINAL_BROKER_ENABLED:
        return
    finished = ledger.SandboxEnvironmentEvent.objects.filter(operation_id=OuterRef('operation_id'), phase='finished')
    pending = ledger.SandboxEnvironmentEvent.objects.filter(phase='requested', kind__in=['start', 'reset']).annotate(done=Exists(finished)).filter(done=False)
    for event in pending:
        task = start_environment_task if event.kind == 'start' else restart_environment_task
        task.delay(event.attempt_id, str(event.operation_id))


@shared_task(name='sandbox.reap_retired_broker_resources', ignore_result=True)
def reap_retired_broker_resources(attempt_id):
    from sandbox.models import TaskAttempt
    from sandbox.services.terminal_lite import reap_retired, OperationBusy
    try:
        reap_retired(TaskAttempt.objects.select_related('task__queue').get(pk=attempt_id))
    except OperationBusy:
        return  # The next periodic pass will retry; no Docker action was authorized.


@shared_task(name="sandbox.run_attempt_check")
def run_attempt_check_task(attempt_id, user_id, run_id=None):
    from sandbox.services.checks import (
        _run_attempt_check_background,
    )

    _run_attempt_check_background(
        attempt_id=attempt_id,
        user_id=user_id,
        run_id=run_id,
    )

@shared_task(name="sandbox.run_ai_review")
def run_ai_review_task(ai_review_id):
    from sandbox.services.ai_reviewer import run_ai_review

    from sandbox.models import AIReview

    ai_review = (
        AIReview.objects
        .select_related("attempt__task")
        .get(id=ai_review_id)
    )

    run_ai_review(ai_review)


@shared_task(name="sandbox.observe_task_http", ignore_result=True, soft_time_limit=20, time_limit=25)
def run_http_observation_task(run_id):
    from sandbox.services.http_observations import run_observation
    run_observation(run_id)
