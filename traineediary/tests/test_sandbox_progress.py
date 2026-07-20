from django.contrib.auth.models import User
from django.test import TestCase

from sandbox.models import (
    Queue,
    Task,
    TaskAttempt,
)
from traineediary.services.sandbox_progress import (
    build_sandbox_queue_progress,
)


class SandboxQueueProgressTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="l1-progress-user",
            password="test",
        )

        self.queue, _ = (
            Queue.objects.update_or_create(
                slug="l1",
                defaults={
                    "name": "ОТП Cloud L1",
                    "description": "",
                    "order": 2,
                    "is_active": True,
                },
            )
        )

        # В тестовой базе очередь l1 может быть
        # создана миграцией вместе с заданиями.
        # Для каждого теста формируем свой набор.
        Task.objects.filter(
            queue=self.queue,
        ).delete()

        self.first_task = Task.objects.create(
            queue=self.queue,
            title="Первое L1-задание",
            slug="diary-l1-first",
            order=1,
            description="Тестовое задание.",
            is_active=True,
        )

        self.second_task = Task.objects.create(
            queue=self.queue,
            title="Второе L1-задание",
            slug="diary-l1-second",
            order=2,
            description="Тестовое задание.",
            is_active=True,
        )

    def test_returns_empty_progress_for_missing_queue(self):
        progress = build_sandbox_queue_progress(
            user=self.user,
            queue_slug="missing-queue",
        )

        self.assertFalse(
            progress.queue_exists,
        )
        self.assertFalse(
            progress.is_ready,
        )
        self.assertEqual(
            progress.total_count,
            0,
        )

    def test_missing_attempts_are_not_completed(self):
        progress = build_sandbox_queue_progress(
            user=self.user,
        )

        self.assertTrue(
            progress.queue_exists,
        )
        self.assertEqual(
            progress.total_count,
            2,
        )
        self.assertEqual(
            progress.passed_count,
            0,
        )
        self.assertEqual(
            progress.remaining_count,
            2,
        )
        self.assertEqual(
            progress.progress_percent,
            0,
        )
        self.assertFalse(
            progress.is_ready,
        )

    def test_counts_only_passed_credit_attempts(self):
        TaskAttempt.objects.create(
            user=self.user,
            task=self.first_task,
            attempt_number=1,
            is_current=True,
            status=TaskAttempt.Status.PASSED,
        )

        TaskAttempt.objects.create(
            user=self.user,
            task=self.second_task,
            attempt_number=1,
            is_current=True,
            status=TaskAttempt.Status.ON_REVIEW,
        )

        progress = build_sandbox_queue_progress(
            user=self.user,
        )

        self.assertEqual(
            progress.total_count,
            2,
        )
        self.assertEqual(
            progress.passed_count,
            1,
        )
        self.assertEqual(
            progress.on_review_count,
            1,
        )
        self.assertEqual(
            progress.remaining_count,
            1,
        )
        self.assertEqual(
            progress.progress_percent,
            50,
        )
        self.assertFalse(
            progress.is_ready,
        )

    def test_all_active_tasks_passed_means_ready(self):
        for task in (
            self.first_task,
            self.second_task,
        ):
            TaskAttempt.objects.create(
                user=self.user,
                task=task,
                attempt_number=1,
                is_current=True,
                status=TaskAttempt.Status.PASSED,
            )

        progress = build_sandbox_queue_progress(
            user=self.user,
        )

        self.assertEqual(
            progress.passed_count,
            2,
        )
        self.assertEqual(
            progress.remaining_count,
            0,
        )
        self.assertEqual(
            progress.progress_percent,
            100,
        )
        self.assertTrue(
            progress.is_ready,
        )

    def test_extra_attempt_does_not_replace_credit_result(self):
        TaskAttempt.objects.create(
            user=self.user,
            task=self.first_task,
            attempt_number=1,
            is_current=False,
            status=TaskAttempt.Status.FAILED,
        )

        TaskAttempt.objects.create(
            user=self.user,
            task=self.first_task,
            attempt_number=2,
            is_current=True,
            status=TaskAttempt.Status.PASSED,
        )

        progress = build_sandbox_queue_progress(
            user=self.user,
        )

        self.assertEqual(
            progress.passed_count,
            0,
        )
        self.assertFalse(
            progress.is_ready,
        )

    def test_inactive_task_is_not_required(self):
        self.second_task.is_active = False
        self.second_task.save(
            update_fields=["is_active"],
        )

        TaskAttempt.objects.create(
            user=self.user,
            task=self.first_task,
            attempt_number=1,
            is_current=True,
            status=TaskAttempt.Status.PASSED,
        )

        progress = build_sandbox_queue_progress(
            user=self.user,
        )

        self.assertEqual(
            progress.total_count,
            1,
        )
        self.assertEqual(
            progress.passed_count,
            1,
        )
        self.assertTrue(
            progress.is_ready,
        )
