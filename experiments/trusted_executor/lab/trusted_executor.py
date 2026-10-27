"""Socket-free Celery forwarding application."""

import os
from pathlib import Path
from urllib.request import Request, urlopen

os.environ.setdefault(
    "DJANGO_SETTINGS_MODULE",
    "config.e2e_settings",
)

import django
django.setup()

from celery import Celery
from django.conf import settings

from executor_protocol import make_request


app = Celery(
    "trusted_checker_executor",
    broker=settings.CELERY_BROKER_URL,
)

app.conf.update(
    task_default_queue="tc_observation",
    task_create_missing_queues=False,
    task_ignore_result=True,
    task_serializer="json",
    accept_content=["json"],
    worker_enable_remote_control=False,
    worker_send_task_events=False,
)


@app.task(
    name="sandbox.observe_task_http",
    ignore_result=True,
    soft_time_limit=25,
    time_limit=30,
)
def observe_task_http(run_id):
    secret = Path("/run/secrets/executor-key").read_bytes().strip()

    body, signature = make_request(run_id, secret)

    request = Request(
        "http://tc-e2e-gateway:8765/observe",
        data=body,
        headers={
            "Content-Type": "application/json",
            "X-Executor-Signature": signature,
        },
        method="POST",
    )

    try:
        with urlopen(request, timeout=23) as response:
            if response.status != 200:
                raise RuntimeError("executor_unavailable")
    except Exception:
        # Gateway may have accepted the request before the connection failed.
        # Finalize ONLY queued: never overwrite running or finished.
        from django.utils import timezone
        from sandbox.models import HTTPObservationRun

        HTTPObservationRun.objects.filter(
            run_id=run_id,
            status="queued",
        ).update(
            status="finished",
            http="unknown",
            reason="dispatch_unavailable",
            finished_at=timezone.now(),
        )
        raise


def verify_registry():
    app.finalize()
    registered = {
        name for name in app.tasks
        if not name.startswith("celery.")
    }
    if registered != {"sandbox.observe_task_http"}:
        raise RuntimeError("unexpected_executor_tasks")
    return sorted(registered)


verify_registry()
