import os

from celery import Celery


os.environ.setdefault(
    "DJANGO_SETTINGS_MODULE",
    "config.settings",
)

app = Celery("training_platform")

app.config_from_object(
    "django.conf:settings",
    namespace="CELERY",
)

app.autodiscover_tasks()


from celery.signals import worker_ready


@worker_ready.connect
def reconcile_terminal_operations(sender=None, **kwargs):
    # Covers death between a committed HTTP request and its on_commit publish.
    from sandbox.tasks import reconcile_broker_environments
    from django.conf import settings
    if settings.TERMINAL_BROKER_ENABLED:
        reconcile_broker_environments.delay()
