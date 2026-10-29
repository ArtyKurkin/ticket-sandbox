"""Resumable Lite lifecycle. Docker side effects are fenced by a per-attempt lock.

PostgreSQL uses a session advisory lock, not a transaction held across Docker.
SQLite/file locking is for the local single-host fixtures, not distributed use.
"""
from contextlib import contextmanager
import fcntl
import hashlib
import os
from pathlib import Path
import uuid

from django.db import connection, transaction
from django.conf import settings
from django.utils import timezone

from sandbox.models import TaskAttempt
from sandbox.services import ledger
from terminal.broker_v2 import Identity
from . import docker_service as ds
from .terminal_gateway import build_terminal_base_path, build_terminal_url, terminal_uses_docker_network
from .terminal_teardown import (
    teardown, verify, get, stop_remove, IdentityError, TeardownPending, LegacyIdentity,
)


class OperationBusy(RuntimeError):
    pass


WORKING_STATUSES = ('new', 'in_progress', 'failed')


@contextmanager
def execution_lock(attempt_id):
    if connection.vendor == 'postgresql':
        with connection.cursor() as cursor:
            cursor.execute('SELECT pg_try_advisory_lock(%s, %s)', [1413624370, attempt_id])
            if not cursor.fetchone()[0]:
                raise OperationBusy('Another environment executor is active')
            cursor.execute('SELECT pg_backend_pid()')
            owner = cursor.fetchone()[0]

        def check():
            with connection.cursor() as cursor:
                cursor.execute('SELECT pg_backend_pid()')
                if cursor.fetchone()[0] != owner:
                    raise OperationBusy('Executor database session changed')
        try:
            yield check
        finally:
            with connection.cursor() as cursor:
                cursor.execute('SELECT pg_backend_pid()')
                if cursor.fetchone()[0] == owner:
                    cursor.execute('SELECT pg_advisory_unlock(%s, %s)', [1413624370, attempt_id])
    else:
        db = hashlib.sha256(str(connection.settings_dict['NAME']).encode()).hexdigest()[:16]
        path = Path('/tmp') / f'terminal-lite-{os.getuid()}-{db}-{attempt_id}.lock'
        fd = os.open(path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        try:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise OperationBusy('Another environment executor is active') from exc
            yield lambda: None
        finally:
            os.close(fd)


def snapshot(attempt):
    if not attempt.container_id:
        if attempt.container_name or attempt.terminal_container_name:
            raise IdentityError('Environment names without a pinned Docker ID')
        return None
    result = dict(container_id=attempt.container_id, attempt=attempt.pk,
        queue=attempt.task.queue.slug, task=attempt.task.slug,
        generation=str(attempt.environment_generation) if attempt.environment_generation else None,
        terminal=attempt.terminal_container_name,
        task_name=attempt.container_name)
    if attempt.environment_generation is None:
        # Legacy ttyd has no target-ID label. Pin its own immutable ID before
        # rotating generation, so a retried migration cannot delete a replacement.
        terminal = (get(ds.get_docker_client(), attempt.terminal_container_name)
                    if attempt.terminal_container_name else None)
        result['terminal_id'] = terminal.id if terminal is not None else None
    return result


def destroy(client, old, attempt):
    if old:
        if (old['attempt'] != attempt.pk or old['queue'] != attempt.task.queue.slug
                or old['task'] != attempt.task.slug):
            raise IdentityError('Checkpoint belongs to another attempt or task')
        values = dict(old)
        name = values.pop('terminal')
        task_name = values.pop('task_name', None)
        if values['container_id'] is None:
            target = get(client, task_name)
            if target is None:
                return
            values['container_id'] = target.id
        if values['generation'] is None:
            identity = LegacyIdentity(**values)
        else:
            identity = Identity(**values)
        teardown(client, identity, name)


def retire(state, spec):
    # Legacy containers predate this operation; they cannot be late creates of
    # its generation. Never retain their reusable terminal names for the reaper.
    if spec and spec['generation'] is not None and not any(old['generation'] == spec['generation'] for old in state.setdefault('retired', [])):
        state['retired'].append(spec)


def replacement_spec(attempt, state):
    generation = state['generation']
    queue, task = attempt.task.queue.slug, attempt.task.slug
    return dict(container_id=state.get('target_id'), generation=generation, attempt=attempt.pk,
        queue=queue, task=task,
        task_name=ds.task_resource_name(queue, task, f'{attempt.pk}-{generation}'),
        terminal=ds.task_resource_name(queue, task, f'{attempt.pk}-{generation}', terminal=True))


def save(attempt, **fields):
    for key, value in fields.items():
        setattr(attempt, key, value)
    attempt.save(update_fields=list(fields))


@ledger.trusted
def run(attempt, kind, operation_id=None, *, actor=None, origin='unknown'):
    if not settings.TERMINAL_BROKER_ENABLED:
        raise RuntimeError('Broker disabled; only cleanup is allowed for broker environments')
    with execution_lock(attempt.pk) as fence:
        attempt.refresh_from_db()
        if operation_id:
            request = ledger.SandboxEnvironmentEvent.objects.filter(
                operation_id=operation_id, attempt_id=attempt.pk, kind=kind, phase='requested').first()
        else:
            request = None
        if request is None:
            request, _ = ledger.request_environment(attempt, kind, actor, origin, operation_id)
        if ledger.SandboxEnvironmentEvent.objects.filter(operation_id=request.operation_id, phase='finished').exists():
            return attempt
        if attempt.environment_cleanup_requested and attempt.environment_operation.get('stage') == 'done':
            save(attempt, environment_cleanup_requested=False)
        if attempt.environment_cleanup_requested or not attempt.is_current or attempt.status not in WORKING_STATUSES:
            ledger.environment_phase(request, 'finished', outcome='not_started', reason='access_revoked')
            return attempt
        state = attempt.environment_operation
        op = str(request.operation_id)
        if state.get('id') != op:
            if state and state.get('stage') not in ('ready', 'done'):
                raise OperationBusy('Previous environment operation needs reconciliation')
            state = dict(id=op, kind=kind, stage='teardown', old=snapshot(attempt),
                         generation=str(uuid.uuid4()), retired=state.get('retired', []))
            # Persist revocation and ownership before any Docker side effect.
            save(attempt, environment_operation=state, environment_generation=state['generation'],
                 environment_status='restarting' if kind == 'reset' else 'starting')
        ledger.environment_phase(request, 'started')
        client = ds.get_docker_client()

        def checkpoint(**values):
            fence()
            with transaction.atomic():
                current = TaskAttempt.objects.select_for_update().get(pk=attempt.pk)
                if (current.environment_cleanup_requested or current.status not in WORKING_STATUSES
                        or current.environment_operation.get('id') != op):
                    raise OperationBusy('Environment operation revoked')
                state.update(values)
                save(attempt, environment_operation=state)

        try:
            if state['stage'] == 'teardown':
                fence()
                destroy(client, state['old'], attempt)
                retire(state, state['old'])
                checkpoint(stage='create')
                save(attempt, container_id='', container_name='', terminal_container_name='',
                     terminal_url='', terminal_port=None)
            generation = state['generation']
            target_name = ds.task_resource_name(attempt.task.queue.slug, attempt.task.slug,
                                               f'{attempt.pk}-{generation}')
            fence()
            target = get(client, target_name)
            if state.get('target_id') and (target is None or target.id != state['target_id']):
                raise IdentityError('Pinned replacement task disappeared or changed')
            if target is None:
                target = ds.create_task_container(attempt.task.queue.slug, attempt.task.slug,
                                                  attempt.pk, generation=generation)
            target.reload()  # SDK run() can retain the pre-start inspection.
            identity = Identity(target.id, attempt.pk, attempt.task.queue.slug, attempt.task.slug, generation)
            verify(target, identity, 'task')
            if target.attrs['State'].get('Status') == 'created':
                fence()
                target.start()  # Worker may have died between Docker create and start.
                target.reload()
            if not target.attrs['State']['Running']:
                raise RuntimeError('Replacement task is not running')
            checkpoint(stage='terminal', target_id=target.id)
            if 'observation' not in state:
                from .observation_config import capture_runtime
                checkpoint(observation=capture_runtime(attempt, target))
            if state['observation'] is not None:
                save(attempt, http_observation_runtime=state['observation'])
            terminal_name = ds.task_resource_name(identity.queue, identity.task,
                f'{attempt.pk}-{generation}', terminal=True)
            if 'port' not in state:
                checkpoint(port=None if terminal_uses_docker_network() else ds.get_free_port())
            save(attempt, container_id=target.id, container_name=target.name,
                 terminal_container_name=terminal_name)
            fence()
            terminal = get(client, terminal_name)
            broker = get(client, terminal_name + '-broker')
            for obj, resource_type in ((terminal, 'terminal'), (broker, 'terminal-broker')):
                if obj is not None:
                    verify(obj, identity, resource_type)
            if terminal is None or broker is None:
                for obj in (terminal, broker):
                    if obj is not None:
                        stop_remove(obj)
                terminal = ds.create_terminal_container(identity.queue, identity.task, attempt.pk,
                    target.id, state['port'], build_terminal_base_path(attempt_id=attempt.pk, port=state['port']),
                    terminal_name=terminal_name)
            try:
                ds.wait_for_terminal_ready(terminal_container_name=terminal.name, port=state['port'])
            except RuntimeError as exc:
                raise TeardownPending('Terminal readiness not confirmed') from exc
            fence()
            with transaction.atomic():
                current = TaskAttempt.objects.select_for_update().get(pk=attempt.pk)
                if (current.environment_cleanup_requested or current.status not in WORKING_STATUSES
                        or current.environment_operation.get('id') != op):
                    raise OperationBusy('Environment operation revoked before publication')
                state['stage'] = 'ready'
                save(attempt, status='in_progress', environment_operation=state, environment_status='ready',
                     environment_finished_at=timezone.now(), terminal_port=state['port'],
                     terminal_url=build_terminal_url(attempt_id=attempt.pk, port=state['port']),
                     restart_count=attempt.restart_count + (kind == 'reset'),
                     started_at=timezone.now(), finished_at=None,
                     check_status='idle', check_started_at=None, check_finished_at=None,
                     last_check_output='Окружение готово.',
                     shell_command=f'docker exec -it {target.name} bash')
                ledger.environment_phase(request, 'finished', outcome='success')
            return attempt
        except Exception as exc:
            # Leave the durable operation unfinished for redelivery/reconciliation.
            fence()
            import docker
            retryable = isinstance(exc, (docker.errors.DockerException, OSError, OperationBusy, TeardownPending))
            status = ('restarting' if kind == 'reset' else 'starting') if retryable else 'error'
            save(attempt, environment_status=status, last_check_output=f'Environment operation pending: {type(exc).__name__}')
            raise


@ledger.trusted
def cleanup(attempt):
    # Durable intent revokes gateway/lease even if another worker owns the lock.
    save(attempt, environment_cleanup_requested=True)
    with execution_lock(attempt.pk) as fence:
        attempt.refresh_from_db()
        state = attempt.environment_operation
        if (state.get('stage') == 'done' and not attempt.container_id
                and not attempt.container_name and not attempt.terminal_container_name):
            return True
        old = (state['old'] if state.get('old') and
               attempt.container_id == state['old']['container_id'] else snapshot(attempt))
        retire(state, old)
        retire(state, state.get('old'))
        if state.get('generation'):
            retire(state, replacement_spec(attempt, state))
        save(attempt, environment_operation=state)
        client = ds.get_docker_client()
        fence()
        destroy(client, old, attempt)
        if state.get('old') and state['old'] != old:
            destroy(client, state['old'], attempt)
        # Cover death between Docker create and the DB publication of its ID.
        if state.get('generation') and state.get('stage') != 'done':
            name = ds.task_resource_name(attempt.task.queue.slug, attempt.task.slug,
                                         f"{attempt.pk}-{state['generation']}")
            target = get(client, name)
            if target is not None:
                identity = Identity(target.id, attempt.pk, attempt.task.queue.slug, attempt.task.slug, state['generation'])
                verify(target, identity, 'task')
                teardown(client, identity, ds.task_resource_name(identity.queue, identity.task,
                    f"{attempt.pk}-{identity.generation}", terminal=True))
        fence()
        with transaction.atomic():
            ledger.interrupt(attempt, 'environment_cleanup')
            save(attempt, environment_operation={**state, 'stage': 'done'},
                 environment_status='idle', container_id='', container_name='',
                 terminal_container_name='', terminal_port=None, terminal_url='', shell_command='',
                 environment_started_at=None, environment_finished_at=None)
        return True


@ledger.trusted
def reap_retired(attempt):
    """Reconcile late daemon responses after worker death; never reap active generation."""
    with execution_lock(attempt.pk) as fence:
        attempt.refresh_from_db()
        state = attempt.environment_operation
        client = ds.get_docker_client()
        for spec in state.get('retired', []):
            if (spec['generation'] == str(attempt.environment_generation) and state.get('stage') != 'done'
                    and not attempt.environment_cleanup_requested):
                raise IdentityError('Active generation in retirement history')
            fence()
            destroy(client, spec, attempt)
