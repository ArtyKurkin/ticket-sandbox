from celery import shared_task
from django.conf import settings


@shared_task(name='tb2.lab.cleanup_environment', ignore_result=True)
def cleanup_environment(attempt_id):
    if not getattr(settings, 'TB2_FULLSTACK_TEST', False):
        raise RuntimeError('Test-only task disabled')
    from sandbox.models import TaskAttempt
    from sandbox.services import ledger
    from sandbox.services.environments import cleanup_attempt_environment
    with ledger.writer():
        attempt = TaskAttempt.objects.select_related('task', 'task__queue').get(pk=attempt_id)
        attempt.status = TaskAttempt.Status.ON_REVIEW
        attempt.save(update_fields=['status'])
        if not cleanup_attempt_environment(attempt):
            raise RuntimeError('Environment cleanup incomplete')


@shared_task(name='tb2.lab.inspect_boundaries', ignore_result=True)
def inspect_boundaries(attempt_id, escaped_pid=None):
    if not getattr(settings, 'TB2_FULLSTACK_TEST', False):
        raise RuntimeError('Test-only task disabled')
    from experiments.terminal_broker.fullstack_security import inspect_boundaries as inspect
    return inspect(attempt_id, escaped_pid)
