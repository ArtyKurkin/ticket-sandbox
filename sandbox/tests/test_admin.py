from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management.base import CommandError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from sandbox.models import CheckRun, Queue, Task, TaskAttempt


class SandboxAdminTests(TestCase):
    def setUp(self):
        User = get_user_model()

        self.admin_user = User.objects.create_superuser(
            username="admin",
            email="admin@example.com",
            password="test-password",
        )

        self.trainee = User.objects.create_user(
            username="trainee",
            email="trainee@example.com",
            password="test-password",
        )

        self.queue, _ = Queue.objects.update_or_create(
            slug="l1",
            defaults={
                "name": "L1",
                "required_level": "l1",
                "order": 1,
                "is_active": True,
            },
        )

        self.task = Task.objects.create(
            queue=self.queue,
            title="Тестовое задание",
            slug="admin-test-task",
            order=1,
            priority="medium",
            ticket_title="Тестовый тикет",
            description="Описание тестового тикета.",
            client_name="Иван",
            client_email="ivan@example.com",
            requires_manual_review=True,
            is_active=True,
        )

        self.attempt = TaskAttempt.objects.create(
            user=self.trainee,
            task=self.task,
            status=TaskAttempt.Status.IN_PROGRESS,
            attempt_number=1,
            is_current=True,
        )

        self.check_run = CheckRun.objects.create(
            attempt=self.attempt,
            result=CheckRun.Result.PASSED,
            output="ok",
            exit_code=0,
        )

        self.client.login(
            username="admin",
            password="test-password",
        )

    def test_admin_changelists_are_available_for_superuser(self):
        urls = (
            reverse("admin:sandbox_queue_changelist"),
            reverse("admin:sandbox_task_changelist"),
            reverse("admin:sandbox_taskattempt_changelist"),
            reverse("admin:sandbox_checkrun_changelist"),
            reverse("admin:sandbox_traineeprofile_changelist"),
        )

        for url in urls:
            with self.subTest(url=url):
                response = self.client.get(url)

                self.assertEqual(response.status_code, 200)

    def test_admin_change_pages_are_available_for_superuser(self):
        urls = (
            reverse("admin:sandbox_queue_change", args=[self.queue.id]),
            reverse("admin:sandbox_task_change", args=[self.task.id]),
            reverse("admin:sandbox_taskattempt_change", args=[self.attempt.id]),
            reverse("admin:sandbox_checkrun_change", args=[self.check_run.id]),
        )

        for url in urls:
            with self.subTest(url=url):
                response = self.client.get(url)

                self.assertEqual(response.status_code, 200)

    def test_task_admin_can_deactivate_selected_tasks(self):
        response = self.client.post(
            reverse("admin:sandbox_task_changelist"),
            data={
                "action": "deactivate_tasks",
                "_selected_action": [self.task.id],
            },
            follow=True,
        )

        self.assertEqual(response.status_code, 200)

        self.task.refresh_from_db()

        self.assertFalse(self.task.is_active)

    def test_task_admin_can_disable_manual_review_for_selected_tasks(self):
        response = self.client.post(
            reverse("admin:sandbox_task_changelist"),
            data={
                "action": "disable_manual_review",
                "_selected_action": [self.task.id],
            },
            follow=True,
        )

        self.assertEqual(response.status_code, 200)

        self.task.refresh_from_db()

        self.assertFalse(self.task.requires_manual_review)

    def test_task_attempt_admin_can_reset_environment_status(self):
        self.attempt.environment_status = TaskAttempt.EnvironmentStatus.ERROR
        self.attempt.environment_started_at = timezone.now()
        self.attempt.environment_finished_at = timezone.now()
        self.attempt.save(
            update_fields=[
                "environment_status",
                "environment_started_at",
                "environment_finished_at",
            ]
        )

        response = self.client.post(
            reverse("admin:sandbox_taskattempt_changelist"),
            data={
                "action": "reset_environment_status",
                "_selected_action": [self.attempt.id],
            },
            follow=True,
        )

        self.assertEqual(response.status_code, 200)

        self.attempt.refresh_from_db()

        self.assertEqual(
            self.attempt.environment_status,
            TaskAttempt.EnvironmentStatus.IDLE,
        )
        self.assertIsNone(self.attempt.environment_started_at)
        self.assertIsNone(self.attempt.environment_finished_at)

    def test_task_attempt_admin_can_reset_check_status(self):
        self.attempt.check_status = TaskAttempt.CheckStatus.ERROR
        self.attempt.check_started_at = timezone.now()
        self.attempt.check_finished_at = timezone.now()
        self.attempt.save(
            update_fields=[
                "check_status",
                "check_started_at",
                "check_finished_at",
            ]
        )

        response = self.client.post(
            reverse("admin:sandbox_taskattempt_changelist"),
            data={
                "action": "reset_check_status",
                "_selected_action": [self.attempt.id],
            },
            follow=True,
        )

        self.assertEqual(response.status_code, 200)

        self.attempt.refresh_from_db()

        self.assertEqual(
            self.attempt.check_status,
            TaskAttempt.CheckStatus.IDLE,
        )
        self.assertIsNone(self.attempt.check_started_at)
        self.assertIsNone(self.attempt.check_finished_at)

    @patch("sandbox.admin.call_command")
    def test_task_admin_sync_training_tasks_page_runs_dry_run_for_superuser(
        self,
        mocked_call_command,
    ):
        response = self.client.get(
            reverse("admin:sandbox_task_sync_training_tasks"),
        )

        self.assertEqual(response.status_code, 200)

        mocked_call_command.assert_called_once()
        args, kwargs = mocked_call_command.call_args

        self.assertEqual(args, ("sync_training_tasks", "--dry-run", "--strict"))
        self.assertIn("stdout", kwargs)

    @patch("sandbox.admin.call_command")
    def test_task_admin_sync_training_tasks_post_runs_sync_for_superuser(
        self,
        mocked_call_command,
    ):
        response = self.client.post(
            reverse("admin:sandbox_task_sync_training_tasks"),
        )

        self.assertEqual(response.status_code, 200)

        mocked_call_command.assert_called_once()
        args, kwargs = mocked_call_command.call_args

        self.assertEqual(args, ("sync_training_tasks", "--strict"))
        self.assertIn("stdout", kwargs)

    def test_task_admin_sync_training_tasks_forbidden_for_staff_not_superuser(self):
        User = get_user_model()

        staff_user = User.objects.create_user(
            username="staff-user",
            email="staff-user@example.com",
            password="test-password",
            is_staff=True,
            is_superuser=False,
        )

        self.client.force_login(staff_user)

        response = self.client.get(
            reverse("admin:sandbox_task_sync_training_tasks"),
        )

        self.assertEqual(response.status_code, 403)

    @patch("sandbox.admin.call_command")
    def test_task_admin_sync_training_tasks_dry_run_error_hides_apply_button(
        self,
        mocked_call_command,
    ):
        mocked_call_command.side_effect = CommandError(
            "sync_training_tasks skipped 1 task(s) in strict mode."
        )

        response = self.client.get(
            reverse("admin:sandbox_task_sync_training_tasks"),
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "sync_training_tasks skipped 1 task(s) in strict mode.",
        )
        self.assertContains(
            response,
            "sync_training_tasks --dry-run --strict",
        )
        self.assertNotContains(
            response,
            "Применить sync_training_tasks",
        )
