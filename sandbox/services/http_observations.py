"""Observation-only request/worker/read source; no legacy checker or Ledger writes."""
from contextlib import contextmanager
from dataclasses import asdict
import json
from uuid import uuid4

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import connection, transaction
from django.db.models import Max
from django.utils import timezone

from sandbox.models import HTTPObservationRun, SandboxEnvironmentEvent, TaskAttempt, TechnicalCheckExecution
from .observation_config import enabled_for, load_config


@contextmanager
def short_read():
    with transaction.atomic():
        previous = None
        if connection.vendor == "postgresql":
            with connection.cursor() as cursor:
                cursor.execute("SELECT current_setting('statement_timeout')")
                previous = cursor.fetchone()[0]
                cursor.execute("SELECT set_config('statement_timeout', '1000', true)")
        try:
            yield
        finally:
            if previous is not None and not connection.needs_rollback:
                with connection.cursor() as cursor:
                    cursor.execute("SELECT set_config('statement_timeout', %s, true)", [previous])


def _context(attempt, user_id):
    if attempt.user_id != user_id:
        raise PermissionDenied
    if not enabled_for(attempt) or not attempt.is_current or not attempt.is_available:
        raise ValidationError("stale_or_unavailable_attempt")
    if (attempt.environment_status != TaskAttempt.EnvironmentStatus.READY
            or attempt.status not in (TaskAttempt.Status.IN_PROGRESS, TaskAttempt.Status.FAILED)
            or attempt.technical_passed or attempt.check_status == TaskAttempt.CheckStatus.RUNNING):
        raise ValidationError("attempt_not_ready_for_observation")
    from experiments.trusted_checker_mvp.docker_pilot.worker import full_id
    if not full_id(attempt.container_id):
        raise ValidationError("container_identity_missing")
    event = SandboxEnvironmentEvent.objects.filter(attempt_id=attempt.pk, phase="requested").order_by("-pk").first()
    if event is None or event.kind not in ("start", "reset") or (event.user_id, event.task_id, event.attempt_number) != (user_id, attempt.task_id, attempt.attempt_number):
        raise ValidationError("environment_generation_missing")
    if not SandboxEnvironmentEvent.objects.filter(operation_id=event.operation_id, phase="finished", outcome="success").exists():
        raise ValidationError("environment_not_completed")
    mapping = attempt.http_observation_runtime
    if (type(mapping) is not dict or mapping.get("environment_uuid") != str(event.operation_id)
            or mapping.get("container_id") != attempt.container_id):
        raise ValidationError("runtime_not_pinned_at_environment_creation")
    tech = TechnicalCheckExecution.objects.filter(attempt_id=attempt.pk).order_by("-ordinal").first()
    if tech and (tech.user_id, tech.task_id, tech.attempt_number) != (user_id, attempt.task_id, attempt.attempt_number):
        raise ValidationError("technical_identity_mismatch")
    last_event = tech.events.order_by("-pk").first() if tech else None
    identity = {
        "user_id": user_id, "task_id": attempt.task_id, "attempt_number": attempt.attempt_number,
        "container_id": attempt.container_id, "environment_uuid": str(event.operation_id),
        "environment_started_at": attempt.environment_started_at.isoformat() if attempt.environment_started_at else None,
        "environment_finished_at": attempt.environment_finished_at.isoformat() if attempt.environment_finished_at else None,
        "restart_count": attempt.restart_count,
        "runtime": mapping,
    }
    return identity, tech, last_event.pk if last_event else None


@transaction.atomic
def request_observation(*, attempt_id, user_id):
    attempt = TaskAttempt.objects.select_for_update(of=("self",)).select_related("task__queue").get(pk=attempt_id)
    identity, tech, event_id = _context(attempt, user_id)
    config, _ = load_config()
    active = HTTPObservationRun.objects.filter(attempt=attempt, status__in=["queued", "running"]).first()
    if active:
        return active, False
    ordinal = (HTTPObservationRun.objects.filter(attempt=attempt).aggregate(n=Max("ordinal"))["n"] or 0) + 1
    run_id, origin = uuid4(), "observation"
    # Reuse only a not-started, not-consumed real technical identity. Never create
    # or finish Ledger records here. Otherwise use the explicitly separate run.
    if tech and event_id is None and not HTTPObservationRun.objects.filter(run_id=tech.run_id).exists() and not HTTPObservationRun.objects.filter(attempt=attempt, ordinal=tech.ordinal).exists():
        run_id, ordinal, origin = tech.run_id, tech.ordinal, "technical_execution"
    run = HTTPObservationRun.objects.create(
        attempt=attempt, requested_by_id=user_id, run_id=run_id, ordinal=ordinal,
        technical_execution=tech, technical_event_id=event_id, execution_origin=origin,
        environment_uuid=identity["environment_uuid"], identity=identity, policy=config,
    )
    transaction.on_commit(lambda: _dispatch(run.run_id))
    return run, True


def _dispatch(run_id):
    try:
        from sandbox.tasks import run_http_observation_task
        run_http_observation_task.delay(str(run_id))
    except Exception:
        _finish(run_id, "unknown", "dispatch_unavailable")


def _current(run):
    attempt = TaskAttempt.objects.select_related("task__queue").get(pk=run.attempt_id)
    identity, tech, event_id = _context(attempt, run.requested_by_id)
    config, _ = load_config()
    if (identity != run.identity or config != run.policy
            or (tech.pk if tech else None) != run.technical_execution_id or event_id != run.technical_event_id
            or run.status != "running"):
        raise ValidationError("stale_execution")
    return attempt


class DjangoObservationSource:
    """Fresh DB read on every adapter fence; no model writes in this source."""
    def __init__(self, run_id):
        self.run_id = run_id

    def __call__(self, attempt_id):
        from experiments.trusted_checker_mvp.docker_pilot.adapter import Execution
        with short_read():
            run = HTTPObservationRun.objects.get(run_id=self.run_id)
            _current(run)
            if run.attempt_id != attempt_id or not run.runtime:
                raise ValidationError("runtime_not_pinned")
            runtime = Execution(**run.runtime)
            if (runtime.attempt_id, runtime.user_id, runtime.run_id, runtime.ordinal,
                runtime.environment_uuid, runtime.container_id) != (
                run.attempt_id, run.requested_by_id, str(run.run_id), run.ordinal,
                str(run.environment_uuid), run.identity["container_id"]):
                raise ValidationError("runtime_identity_mismatch")
            return runtime


def make_api(config):
    import docker
    return docker.APIClient(base_url="unix://" + config["api_socket"], version="1.45", timeout=1)


def _finish(run_id, http, reason, result=None):
    HTTPObservationRun.objects.filter(run_id=run_id, status__in=["queued", "running"]).update(
        status="finished", http=http, reason=reason, result=result or {}, finished_at=timezone.now())


def run_observation(run_id):
    from experiments.trusted_checker_mvp.docker_pilot.adapter import DockerPilot, Execution
    if not HTTPObservationRun.objects.filter(run_id=run_id, status="queued").update(status="running", started_at=timezone.now()):
        return  # Duplicate Celery delivery never re-dispatches Docker.
    api = None
    try:
        with short_read():
            run = HTTPObservationRun.objects.get(run_id=run_id)
            _current(run)
            config, policy = load_config()
        api = make_api(config)
        runtime = Execution(attempt_id=run.attempt_id, user_id=run.requested_by_id,
                            run_id=str(run.run_id), ordinal=run.ordinal, **run.identity["runtime"])
        with transaction.atomic():
            run = HTTPObservationRun.objects.select_for_update().get(run_id=run_id)
            _current(run)
            run.runtime = asdict(runtime)
            run.save(update_fields=["runtime"])
        source = DjangoObservationSource(run_id)
        observation = DockerPilot(api, policy, source, config["artifact_dir"], enabled=True).observe(run.attempt_id)
        payload = asdict(observation)
        if len(json.dumps(payload).encode()) > 8192:
            raise ValidationError("observation_bounds")
        with transaction.atomic():
            # Same lock order as request/reset: attempt, then diagnostic run.
            # No network wait while holding the attempt lock.
            TaskAttempt.objects.select_for_update().get(pk=run.attempt_id)
            run = HTTPObservationRun.objects.select_for_update().get(run_id=run_id)
            _current(run)
            _finish(run_id, observation.http, observation.reason, payload)
    except Exception:
        _finish(run_id, "unknown", "observation_unavailable_or_stale")
    finally:
        if api is not None:
            api.close()
