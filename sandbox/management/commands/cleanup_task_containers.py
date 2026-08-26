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

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show attempts that would be cleaned up without removing containers.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        expired_time = timezone.now() - timedelta(hours=72)

        unfinished_attempts = TaskAttempt.objects.filter(
            finished_at__isnull=True,
            started_at__lt=expired_time,
            technical_passed_at__isnull=True,
        )

        passed_attempts = (
            TaskAttempt.objects.filter(
                finished_at__isnull=True,
                status=TaskAttempt.Status.IN_PROGRESS,
                technical_passed_at__lt=expired_time,
                task__requires_manual_review=True,
                attempt_number=1,
                is_current=True,
            )
            .exclude(
                container_name="",
                terminal_container_name="",
            )
        )

        cleaned_count = 0

        for attempt in unfinished_attempts:
            if dry_run:
                self.stdout.write(
                    (
                        f"WOULD CLEANUP attempt #{attempt.id}: "
                        f"{attempt.task.queue.slug}/{attempt.task.slug}"
                    )
                )
                cleaned_count += 1
                continue

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

            attempt.environment_status = TaskAttempt.EnvironmentStatus.IDLE
            attempt.environment_started_at = None
            attempt.environment_finished_at = None

            attempt.check_status = TaskAttempt.CheckStatus.IDLE
            attempt.check_started_at = None
            attempt.check_finished_at = None

            attempt.stuck_reason = TaskAttempt.StuckReason.NONE

            attempt.save(
                update_fields=[
                    "container_id",
                    "container_name",
                    "shell_command",
                    "terminal_container_name",
                    "terminal_url",
                    "terminal_port",
                    "status",
                    "environment_status",
                    "environment_started_at",
                    "environment_finished_at",
                    "check_status",
                    "check_started_at",
                    "check_finished_at",
                    "stuck_reason",
                ]
            )

            cleaned_count += 1

        preserved_technical_count = 0

        for attempt in passed_attempts:
            if dry_run:
                self.stdout.write(
                    (
                        f"WOULD CLEANUP PASSED attempt #{attempt.id}: "
                        f"{attempt.task.queue.slug}/{attempt.task.slug}"
                    )
                )
                cleaned_count += 1
                preserved_technical_count += 1
                continue

            self.stdout.write(
                f"Cleanup passed attempt #{attempt.id}"
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

            attempt.environment_status = (
                TaskAttempt.EnvironmentStatus.IDLE
            )
            attempt.environment_started_at = None
            attempt.environment_finished_at = None

            attempt.stuck_reason = (
                TaskAttempt.StuckReason.NONE
            )

            attempt.save(
                update_fields=[
                    "container_id",
                    "container_name",
                    "shell_command",
                    "terminal_container_name",
                    "terminal_url",
                    "terminal_port",
                    "environment_status",
                    "environment_started_at",
                    "environment_finished_at",
                    "stuck_reason",
                ]
            )

            cleaned_count += 1
            preserved_technical_count += 1

        if dry_run:
            self.stdout.write(
                self.style.SUCCESS
                (
                    f"Dry run completed. would_cleanup={cleaned_count} "
                    f"would_preserve_technical={preserved_technical_count}"
                )
            )
        else:
            self.stdout.write(
                self.style.SUCCESS
                (
                    f"Cleanup completed. cleaned={cleaned_count} "
                    f"preserved_technical={preserved_technical_count}"
                )
            )
