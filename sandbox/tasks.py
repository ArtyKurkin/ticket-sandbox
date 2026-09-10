from celery import shared_task


@shared_task(name="sandbox.celery_ping")
def celery_ping():
    return "pong"


@shared_task(name="sandbox.start_environment")
def start_environment_task(attempt_id):
    from sandbox.services.environments import (
        _run_environment_start_background,
    )

    _run_environment_start_background(attempt_id)


@shared_task(name="sandbox.restart_environment")
def restart_environment_task(attempt_id):
    from sandbox.services.environments import (
        _run_environment_restart_background,
    )

    _run_environment_restart_background(attempt_id)
