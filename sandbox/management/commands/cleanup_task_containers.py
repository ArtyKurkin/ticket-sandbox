from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from sandbox.models import TaskAttempt
from sandbox.services.docker_service import (
    remove_task_container,
    remove_terminal_container,
)


class Command(BaseCommand):
    help = "Cleanup old task containers"

    def handle(self, *args, **options):
        expired_time = timezone.now() - timedelta(hours=72)

        attempts = TaskAttempt.objects.filter(
            finished_at__isnull=True,
            started_at__lt=expired_time,
            technical_passed_at__isnull=True,
        )

        for attempt in attempts:
            self.stdout.write(
                f"Cleanup attempt #{attempt.id}"
            )

            if attempt.container_name:
                remove_task_container(
                    attempt.container_name
                )

            if attempt.terminal_container_name:
                remove_terminal_container(
                    attempt.terminal_container_name
                )

            attempt.container_id = ""
            attempt.container_name = ""
            attempt.shell_command = ""

            attempt.terminal_container_name = ""
            attempt.terminal_url = ""
            attempt.terminal_port = None

            attempt.status = TaskAttempt.Status.NEW

            attempt.save()

        self.stdout.write(
            self.style.SUCCESS(
                "Cleanup completed"
            )
        )
