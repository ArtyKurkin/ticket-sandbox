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


@shared_task(name="sandbox.run_attempt_check")
def run_attempt_check_task(attempt_id, user_id):
    from sandbox.services.checks import (
        _run_attempt_check_background,
    )

    _run_attempt_check_background(
        attempt_id=attempt_id,
        user_id=user_id,
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
