from celery import shared_task
from django.conf import settings
from celery.signals import task_prerun, task_postrun
import json
import os
from pathlib import Path
import signal

_factory = None


def fault_record(kind, operation_id, **fields):
    path = Path('/lab') / ('faults-' + settings.TB2_MODE + '.jsonl')
    fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
    try:
        os.write(fd, (json.dumps(dict(kind=kind, operation=operation_id, **fields)) + '\n').encode())
        os.fsync(fd)
    finally:
        os.close(fd)


@task_prerun.connect
def inject_lite_worker_loss(task=None, args=None, kwargs=None, **extra):
    """Test-only: call the real factory, then kill the worker before publication."""
    global _factory
    if not settings.TB2_FULLSTACK_TEST or task.name not in ('sandbox.start_environment', 'sandbox.restart_environment'):
        return
    operation = str((kwargs or {}).get('operation_id') or args[1])
    marker = Path('/lab') / ('duplicate-' + settings.TB2_MODE + '-' + operation)
    try:
        fd = os.open(marker, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        pass
    else:
        os.close(fd)
        task.apply_async(args=args, kwargs=kwargs)
        fault_record('duplicate-delivery', operation)
    from sandbox.services import docker_service as ds
    _factory = ds.create_task_container
    original = _factory
    def create_then_crash(*values, **options):
        target = original(*values, **options)
        marker = Path('/lab') / ('killed-' + settings.TB2_MODE + '-' + task.name)
        try:
            fd = os.open(marker, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            return target
        os.fsync(fd)
        os.close(fd)
        fault_record('worker-SIGKILL-after-create', operation, target=target.id)
        os.kill(os.getpid(), signal.SIGKILL)
    ds.create_task_container = create_then_crash


@task_postrun.connect
def restore_factory(**kwargs):
    global _factory
    if _factory is not None:
        from sandbox.services import docker_service as ds
        ds.create_task_container = _factory
        _factory = None


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
def inspect_boundaries(attempt_id, escaped_pid=None, interactive_pid=None):
    if not getattr(settings, 'TB2_FULLSTACK_TEST', False):
        raise RuntimeError('Test-only task disabled')
    from experiments.terminal_broker.fullstack_security import inspect_boundaries as inspect
    return inspect(attempt_id, escaped_pid, interactive_pid)


@shared_task(name='tb2.lab.broker_cycle', ignore_result=True)
def broker_cycle(attempt_id):
    assert settings.TB2_FULLSTACK_TEST
    import docker
    import time
    from sandbox.models import TaskAttempt
    attempt = TaskAttempt.objects.get(pk=attempt_id)
    broker = docker.from_env().containers.get(attempt.terminal_container_name + '-broker')
    code, old = broker.exec_run(['python', '-c',
        'import hashlib;print(hashlib.sha256(open("/run/terminal/client.json","rb").read()).hexdigest())'])
    assert code == 0
    broker.update(restart_policy={'Name': 'no'})
    broker.kill(signal='SIGKILL')
    broker.start()
    for _ in range(120):
        code, new = broker.exec_run(['python', '-c',
            'import hashlib,pathlib;print(hashlib.sha256(open("/run/terminal/client.json","rb").read()).hexdigest());'
            'assert not list(pathlib.Path("/var/lib/terminal").glob("*.json"))'])
        if code == 0 and new != old:
            break
        time.sleep(.2)
    else:
        raise RuntimeError('Broker SIGKILL recovery did not complete')
    assert b'ERROR:terminal.broker' not in broker.logs()
    (Path('/lab') / ('cycle-' + settings.TB2_MODE + '.json')).write_text(json.dumps({'recovered':True}))
