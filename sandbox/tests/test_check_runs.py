from unittest.mock import patch

from django.urls import reverse

from sandbox.models import CheckRun, TaskAttempt, TraineeProfile

from .base import SandboxTestCase


class CheckRunTests(SandboxTestCase):
    def setUp(self):
        self.queue = self.create_queue(
            slug="l1",
            name="ОТП Cloud L1",
            order=1,
            required_level=TraineeProfile.Level.L1,
        )

        self.task = self.create_task(
            queue=self.queue,
            slug="check-run-task",
            order=1,
        )

        self.user = self.create_user(
            username="check-run-user",
            level=TraineeProfile.Level.L1,
        )

        self.attempt = TaskAttempt.objects.create(
            user=self.user,
            task=self.task,
            status=TaskAttempt.Status.IN_PROGRESS,
            container_name="check-run-container",
            terminal_container_name="check-run-terminal-container",
        )

        self.client.login(
            username="check-run-user",
            password="test-password",
        )

    @patch("sandbox.views.remove_terminal_container")
    @patch("sandbox.views.remove_task_container")
    @patch("sandbox.views.check_task_container")
    def test_successful_check_creates_passed_check_run(
        self,
        check_task_container_mock,
        remove_task_container_mock,
        remove_terminal_container_mock,
    ):
        check_task_container_mock.return_value = (
            0,
            "Проверка пройдена.",
        )

        remove_task_container_mock.return_value = (
            True,
            "Контейнер удален.",
        )

        remove_terminal_container_mock.return_value = (
            True,
            "Терминал удален.",
        )

        response = self.client.post(
            reverse("sandbox:check_task", args=[self.attempt.id]),
            data={
                "client_answer": "Здравствуйте, проблема исправлена.",
                "trainee_report": "Проверил сервис и восстановил работу.",
            },
        )

        self.assertEqual(response.status_code, 302)

        check_run = CheckRun.objects.get(attempt=self.attempt)

        self.assertEqual(check_run.result, CheckRun.Result.PASSED)
        self.assertEqual(check_run.output, "Проверка пройдена.")
        self.assertEqual(check_run.exit_code, 0)

        self.attempt.refresh_from_db()

        self.assertEqual(self.attempt.status, TaskAttempt.Status.PASSED)
        self.assertEqual(self.attempt.attempts_count, 1)

    @patch("sandbox.views.check_task_container")
    def test_failed_check_creates_failed_check_run(
        self,
        check_task_container_mock,
    ):
        check_task_container_mock.return_value = (
            1,
            "Nginx все еще не запущен.",
        )

        response = self.client.post(
            reverse("sandbox:check_task", args=[self.attempt.id]),
            data={
                "client_answer": "Здравствуйте, проблема пока в работе.",
                "trainee_report": "Проверил nginx, но ошибка осталась.",
            },
        )

        self.assertEqual(response.status_code, 302)

        check_run = CheckRun.objects.get(attempt=self.attempt)

        self.assertEqual(check_run.result, CheckRun.Result.FAILED)
        self.assertEqual(check_run.output, "Nginx все еще не запущен.")
        self.assertEqual(check_run.exit_code, 1)

        self.attempt.refresh_from_db()

        self.assertEqual(self.attempt.status, TaskAttempt.Status.FAILED)
        self.assertEqual(self.attempt.attempts_count, 1)

    @patch("sandbox.views.check_task_container")
    def test_each_check_creates_separate_check_run(
        self,
        check_task_container_mock,
    ):
        check_task_container_mock.return_value = (
            1,
            "Первая проверка не прошла.",
        )

        first_response = self.client.post(
            reverse("sandbox:check_task", args=[self.attempt.id]),
            data={
                "client_answer": "Ответ клиенту.",
                "trainee_report": "Комментарий по диагностике.",
            },
        )

        self.assertEqual(first_response.status_code, 302)

        self.attempt.refresh_from_db()
        self.attempt.status = TaskAttempt.Status.IN_PROGRESS
        self.attempt.save()

        check_task_container_mock.return_value = (
            1,
            "Вторая проверка не прошла.",
        )

        second_response = self.client.post(
            reverse("sandbox:check_task", args=[self.attempt.id]),
            data={
                "client_answer": "Ответ клиенту после доработки.",
                "trainee_report": "Комментарий после доработки.",
            },
        )

        self.assertEqual(second_response.status_code, 302)

        self.assertEqual(
            CheckRun.objects.filter(attempt=self.attempt).count(),
            2,
        )

        outputs = list(
            CheckRun.objects.filter(attempt=self.attempt)
            .order_by("created_at")
            .values_list("output", flat=True)
        )

        self.assertEqual(
            outputs,
            [
                "Первая проверка не прошла.",
                "Вторая проверка не прошла.",
            ],
        )

        self.attempt.refresh_from_db()

        self.assertEqual(self.attempt.status, TaskAttempt.Status.FAILED)
        self.assertEqual(self.attempt.attempts_count, 2)

    def test_task_detail_displays_check_run_history(self):
        CheckRun.objects.create(
            attempt=self.attempt,
            result=CheckRun.Result.FAILED,
            output="Первая проверка не прошла.",
            exit_code=1,
        )

        CheckRun.objects.create(
            attempt=self.attempt,
            result=CheckRun.Result.PASSED,
            output="Вторая проверка пройдена.",
            exit_code=0,
        )

        response = self.client.get(
            reverse("sandbox:task_detail", args=[self.attempt.id])
        )

        self.assertEqual(response.status_code, 200)

        self.assertContains(response, "История проверок")
        self.assertContains(response, "Первая проверка не прошла.")
        self.assertContains(response, "Вторая проверка пройдена.")
        self.assertContains(response, "Exit code: 1")
        self.assertContains(response, "Exit code: 0")
