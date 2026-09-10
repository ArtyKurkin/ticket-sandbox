from celery import shared_task


@shared_task(name="sandbox.celery_ping")
def celery_ping():
    return "pong"
