from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

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
