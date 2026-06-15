from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from sandbox.models import Queue, Task, TaskAttempt, TraineeProfile


class TechnicalLockTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="trainee_lock",
            password="password",
        )

        profile, _ = TraineeProfile.objects.get_or_create(
            user=self.user,
        )
        profile.level = TraineeProfile.Level.L1
        profile.save(update_fields=["level"])

        self.queue = Queue.objects.create(
            name="Lock L1",
            slug="lock-l1",
            required_level=TraineeProfile.Level.L1,
            order=100,
        )

        self.task = Task.objects.create(
            queue=self.queue,
            title="Locked task",
            slug="locked-task",
            order=1,
            description="Учебное сообщение клиента",
            requires_manual_review=True,
        )

        self.attempt = TaskAttempt.objects.create(
            user=self.user,
            task=self.task,
            status=TaskAttempt.Status.FAILED,
            technical_passed_at=timezone.now(),
            client_answer="Старый ответ клиенту",
            trainee_report="Старая диагностика",
        )

        self.client.login(
            username="trainee_lock",
            password="password",
        )

    def test_start_task_is_blocked_after_technical_success(self):
        url = reverse(
            "sandbox:start_task",
            args=[self.attempt.id],
        )

        with patch("sandbox.views.create_task_container") as create_task_container:
            response = self.client.post(url)

        self.assertRedirects(
            response,
            reverse(
                "sandbox:task_detail",
                args=[self.attempt.id],
            ),
        )

        create_task_container.assert_not_called()

        self.attempt.refresh_from_db()

        self.assertEqual(
            self.attempt.status,
            TaskAttempt.Status.FAILED,
        )
        self.assertEqual(
            self.attempt.container_name,
            "",
        )
        self.assertIsNotNone(
            self.attempt.technical_passed_at,
        )

    def test_restart_task_is_blocked_after_technical_success(self):
        self.attempt.container_name = "old-task-container"
        self.attempt.terminal_container_name = "old-terminal-container"
        self.attempt.terminal_url = "http://localhost:7681"
        self.attempt.terminal_port = 7681
        self.attempt.restart_count = 2
        self.attempt.save(
            update_fields=[
                "container_name",
                "terminal_container_name",
                "terminal_url",
                "terminal_port",
                "restart_count",
            ]
        )

        url = reverse(
            "sandbox:restart_task",
            args=[self.attempt.id],
        )

        with patch("sandbox.views.remove_terminal_container") as remove_terminal_container, \
             patch("sandbox.views.remove_task_container") as remove_task_container, \
             patch("sandbox.views.create_task_container") as create_task_container, \
             patch("sandbox.views.create_terminal_container") as create_terminal_container:
            response = self.client.post(url)

        self.assertRedirects(
            response,
            reverse(
                "sandbox:task_detail",
                args=[self.attempt.id],
            ),
        )

        remove_terminal_container.assert_not_called()
        remove_task_container.assert_not_called()
        create_task_container.assert_not_called()
        create_terminal_container.assert_not_called()

        self.attempt.refresh_from_db()

        self.assertEqual(
            self.attempt.status,
            TaskAttempt.Status.FAILED,
        )
        self.assertEqual(
            self.attempt.restart_count,
            2,
        )
        self.assertEqual(
            self.attempt.container_name,
            "old-task-container",
        )
        self.assertIsNotNone(
            self.attempt.technical_passed_at,
        )

    def test_terminal_is_hidden_after_technical_success(self):
        self.attempt.terminal_url = "http://localhost:7681"
        self.attempt.terminal_port = 7681
        self.attempt.save(
            update_fields=[
                "terminal_url",
                "terminal_port",
            ]
        )

        response = self.client.get(
            reverse(
                "sandbox:task_detail",
                args=[self.attempt.id],
            )
        )

        self.assertEqual(response.status_code, 200)

        self.assertContains(
            response,
            "Техническая часть выполнена",
        )
        self.assertNotContains(
            response,
            "terminal-frame",
        )
        self.assertNotContains(
            response,
            'src="http://localhost:7681"',
        )

    def test_text_revision_does_not_run_check_sh_again(self):
        self.attempt.status = TaskAttempt.Status.FAILED
        self.attempt.mentor_decision = TaskAttempt.MentorDecision.NEEDS_REVISION
        self.attempt.attempts_count = 3
        self.attempt.save(
            update_fields=[
                "status",
                "mentor_decision",
                "attempts_count",
            ]
        )

        url = reverse(
            "sandbox:check_task",
            args=[self.attempt.id],
        )

        with patch("sandbox.views.check_task_container") as check_task_container:
            response = self.client.post(
                url,
                {
                    "client_answer": "Исправленный ответ клиенту",
                    "trainee_report": "Диагностика не менялась, исправлен только текст.",
                },
            )

        self.assertRedirects(
            response,
            reverse(
                "sandbox:task_detail",
                args=[self.attempt.id],
            ),
        )

        check_task_container.assert_not_called()

        self.attempt.refresh_from_db()

        self.assertEqual(
            self.attempt.status,
            TaskAttempt.Status.ON_REVIEW,
        )
        self.assertEqual(
            self.attempt.mentor_decision,
            TaskAttempt.MentorDecision.NOT_REVIEWED,
        )
        self.assertEqual(
            self.attempt.attempts_count,
            3,
        )
        self.assertEqual(
            self.attempt.client_answer,
            "Исправленный ответ клиенту",
        )
        self.assertIsNotNone(
            self.attempt.technical_passed_at,
        )
