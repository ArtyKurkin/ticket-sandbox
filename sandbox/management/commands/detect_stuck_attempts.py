from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from sandbox.models import TaskAttempt
from sandbox.services.notifications import notify_stuck_attempt_detected


DEFAULT_STUCK_THRESHOLD_MINUTES = 10

ENVIRONMENT_STUCK_MESSAGE = (
    "Запуск окружения был прерван. "
    "Возможная причина — перезапуск сервиса или ошибка фонового процесса. "
    "Попробуй запустить окружение заново."
)

CHECK_STUCK_MESSAGE = (
    "Автопроверка была прервана. "
    "Возможная причина — перезапуск сервиса или ошибка фонового процесса. "
    "Попробуй запустить проверку заново."
)


class Command(BaseCommand):
    help = "Detect and mark stuck background attempt states"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show stuck attempts without changing them.",
        )
        parser.add_argument(
            "--minutes",
            type=int,
            default=DEFAULT_STUCK_THRESHOLD_MINUTES,
            help="How old a background state should be to be considered stuck.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        minutes = options["minutes"]

        now = timezone.now()
        stuck_deadline = now - timedelta(minutes=minutes)

        stuck_environment_attempts = (
            TaskAttempt.objects
            .select_related("task", "task__queue")
            .filter(
                environment_status__in=[
                    TaskAttempt.EnvironmentStatus.STARTING,
                    TaskAttempt.EnvironmentStatus.RESTARTING,
                ],
                environment_started_at__isnull=False,
                environment_started_at__lt=stuck_deadline,
                technical_passed_at__isnull=True,
            )
            .exclude(status=TaskAttempt.Status.PASSED)
        )

        stuck_check_attempts = (
            TaskAttempt.objects
            .select_related("task", "task__queue")
            .filter(
                check_status=TaskAttempt.CheckStatus.RUNNING,
                check_started_at__isnull=False,
                check_started_at__lt=stuck_deadline,
                technical_passed_at__isnull=True,
            )
            .exclude(status=TaskAttempt.Status.PASSED)
            .exclude(
                environment_status__in=[
                    TaskAttempt.EnvironmentStatus.STARTING,
                    TaskAttempt.EnvironmentStatus.RESTARTING,
                    TaskAttempt.EnvironmentStatus.ERROR,
                ]
            )
        )

        environment_count = self.mark_stuck_environment_attempts(
            attempts=stuck_environment_attempts,
            dry_run=dry_run,
            now=now,
        )

        check_count = self.mark_stuck_check_attempts(
            attempts=stuck_check_attempts,
            dry_run=dry_run,
            now=now,
        )

        if dry_run:
            self.stdout.write(
                self.style.SUCCESS(
                    (
                        "Dry run completed. "
                        f"would_mark_environment={environment_count}, "
                        f"would_mark_check={check_count}"
                    )
                )
            )
            return

        self.stdout.write(
            self.style.SUCCESS(
                (
                    "Stuck attempts detection completed. "
                    f"marked_environment={environment_count}, "
                    f"marked_check={check_count}"
                )
            )
        )

    def mark_stuck_environment_attempts(self, attempts, dry_run, now):
        marked_count = 0

        for attempt in attempts:
            self.stdout.write(
                (
                    f"{'WOULD MARK' if dry_run else 'MARK'} "
                    f"stuck environment attempt #{attempt.id}: "
                    f"{attempt.task.queue.slug}/{attempt.task.slug}"
                )
            )

            if dry_run:
                marked_count += 1
                continue

            attempt.environment_status = TaskAttempt.EnvironmentStatus.ERROR
            attempt.environment_finished_at = now
            attempt.status = TaskAttempt.Status.FAILED
            attempt.last_check_output = ENVIRONMENT_STUCK_MESSAGE

            update_fields = [
                "environment_status",
                "environment_finished_at",
                "status",
                "last_check_output",
            ]

            if attempt.check_status == TaskAttempt.CheckStatus.RUNNING:
                attempt.check_status = TaskAttempt.CheckStatus.ERROR
                attempt.check_finished_at = now
                update_fields.extend(
                    [
                        "check_status",
                        "check_finished_at",
                    ]
                )

            attempt.save(update_fields=update_fields)

            notify_stuck_attempt_detected(
                attempt=attempt,
                reason="завис запуск или перезапуск окружения",
            )

            marked_count += 1

        return marked_count

    def mark_stuck_check_attempts(self, attempts, dry_run, now):
        marked_count = 0

        for attempt in attempts:
            self.stdout.write(
                (
                    f"{'WOULD MARK' if dry_run else 'MARK'} "
                    f"stuck check attempt #{attempt.id}: "
                    f"{attempt.task.queue.slug}/{attempt.task.slug}"
                )
            )

            if dry_run:
                marked_count += 1
                continue

            attempt.check_status = TaskAttempt.CheckStatus.ERROR
            attempt.check_finished_at = now
            attempt.status = TaskAttempt.Status.FAILED
            attempt.last_check_output = CHECK_STUCK_MESSAGE

            attempt.save(
                update_fields=[
                    "check_status",
                    "check_finished_at",
                    "status",
                    "last_check_output",
                ]
            )

            notify_stuck_attempt_detected(
                attempt=attempt,
                reason="зависла автопроверка",
            )

            marked_count += 1

        return marked_count
