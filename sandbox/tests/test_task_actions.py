from types import SimpleNamespace
from unittest.mock import patch

from django.conf import settings
from django.shortcuts import resolve_url
from django.urls import reverse
from django.utils import timezone

from sandbox.models import TaskAttempt, TraineeProfile

from .base import SandboxTestCase


class TaskDetailAccessTests(SandboxTestCase):
    def setUp(self):
        self.queue = self.create_queue(
            slug="l1",
            name="ОТП Cloud L1",
            order=1,
            required_level=TraineeProfile.Level.L1,
        )

        self.task = self.create_task(
            queue=self.queue,
            slug="task",
            order=1,
        )

        self.owner = self.create_user(
            username="owner",
            level=TraineeProfile.Level.L1,
        )

        self.other_user = self.create_user(
            username="other-user",
            level=TraineeProfile.Level.L1,
        )

        self.attempt = TaskAttempt.objects.create(
            user=self.owner,
            task=self.task,
        )

    def test_user_can_open_own_attempt(self):
        self.client.login(username="owner", password="test-password")

        response = self.client.get(
            reverse("sandbox:task_detail", args=[self.attempt.id])
        )

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "sandbox/task_detail.html")

    def test_task_detail_shows_failed_check_status_badge(self):
        self.attempt.status = TaskAttempt.Status.FAILED
        self.attempt.check_status = TaskAttempt.CheckStatus.FAILED
        self.attempt.mentor_decision = TaskAttempt.MentorDecision.NOT_REVIEWED
        self.attempt.save(
            update_fields=[
                "status",
                "check_status",
                "mentor_decision",
            ]
        )

        self.client.login(username="owner", password="test-password")

        response = self.client.get(
            reverse("sandbox:task_detail", args=[self.attempt.id])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Техническая часть не пройдена")
        self.assertContains(response, "Автопроверка не пройдена")

    def test_task_detail_shows_check_error_status_badge(self):
        self.attempt.status = TaskAttempt.Status.FAILED
        self.attempt.check_status = TaskAttempt.CheckStatus.ERROR
        self.attempt.mentor_decision = TaskAttempt.MentorDecision.NOT_REVIEWED
        self.attempt.save(
            update_fields=[
                "status",
                "check_status",
                "mentor_decision",
            ]
        )

        self.client.login(username="owner", password="test-password")

        response = self.client.get(
            reverse("sandbox:task_detail", args=[self.attempt.id])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Ошибка автопроверки")
        self.assertContains(response, "Автопроверка завершилась с ошибкой")

    def test_environment_starting_poll_card_is_visible(self):
        self.attempt.environment_status = TaskAttempt.EnvironmentStatus.STARTING
        self.attempt.last_check_output = "Окружение запускается..."
        self.attempt.save(
            update_fields=[
                "environment_status",
                "last_check_output",
            ]
        )

        self.client.login(username="owner", password="test-password")

        response = self.client.get(
            reverse("sandbox:task_detail", args=[self.attempt.id])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Окружение запускается")
        self.assertContains(response, "data-environment-poll-url")
        self.assertContains(response, "data-environment-poll-output")

    def test_environment_error_card_is_visible(self):
        self.attempt.status = TaskAttempt.Status.FAILED
        self.attempt.environment_status = TaskAttempt.EnvironmentStatus.ERROR
        self.attempt.last_check_output = (
            "Не удалось запустить окружение задания из-за ошибки Docker API."
        )
        self.attempt.save(
            update_fields=[
                "status",
                "environment_status",
                "last_check_output",
            ]
        )

        self.client.login(username="owner", password="test-password")

        response = self.client.get(
            reverse("sandbox:task_detail", args=[self.attempt.id])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Ошибка запуска окружения")
        self.assertContains(response, "Окружение не запустилось")

    def test_task_detail_shows_manual_revision_status_badge(self):
        self.task.requires_manual_review = True
        self.task.save(update_fields=["requires_manual_review"])

        self.attempt.status = TaskAttempt.Status.FAILED
        self.attempt.check_status = TaskAttempt.CheckStatus.PASSED
        self.attempt.technical_passed_at = timezone.now()
        self.attempt.mentor_decision = TaskAttempt.MentorDecision.NEEDS_REVISION
        self.attempt.save(
            update_fields=[
                "status",
                "check_status",
                "technical_passed_at",
                "mentor_decision",
            ]
        )

        self.client.login(username="owner", password="test-password")

        response = self.client.get(
            reverse("sandbox:task_detail", args=[self.attempt.id])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Доработать ответ")

    def test_manual_review_badge_is_visible_when_task_requires_manual_review(self):
        self.task.requires_manual_review = True
        self.task.save(update_fields=["requires_manual_review"])

        self.client.login(username="owner", password="test-password")

        response = self.client.get(
            reverse("sandbox:task_detail", args=[self.attempt.id])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "После автопроверки нужна ручная проверка наставника",
        )

    def test_manual_review_badge_is_hidden_when_task_does_not_require_manual_review(self):
        self.task.requires_manual_review = False
        self.task.save(update_fields=["requires_manual_review"])

        self.client.login(username="owner", password="test-password")

        response = self.client.get(
            reverse("sandbox:task_detail", args=[self.attempt.id])
        )

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(
            response,
            "После автопроверки нужна ручная проверка наставника",
        )

    def test_user_cannot_open_other_user_attempt(self):
        self.client.login(username="other-user", password="test-password")

        response = self.client.get(
            reverse("sandbox:task_detail", args=[self.attempt.id])
        )

        self.assertEqual(response.status_code, 404)

    def test_answer_form_is_hidden_before_technical_pass(self):
        self.attempt.task.requires_manual_review = True
        self.attempt.task.save(update_fields=["requires_manual_review"])

        self.attempt.status = TaskAttempt.Status.IN_PROGRESS
        self.attempt.technical_passed_at = None
        self.attempt.save(
            update_fields=[
                "status",
                "technical_passed_at",
            ]
        )

        self.client.login(username="owner", password="test-password")

        response = self.client.get(
            reverse("sandbox:task_detail", args=[self.attempt.id])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "Сначала выполни техническую часть задания",
        )
        self.assertNotContains(
            response,
            "Отправить ответ на проверку",
        )

    def test_answer_form_is_visible_after_technical_pass_when_manual_review_required(self):
        self.attempt.task.requires_manual_review = True
        self.attempt.task.save(update_fields=["requires_manual_review"])

        self.attempt.status = TaskAttempt.Status.IN_PROGRESS
        self.attempt.technical_passed_at = timezone.now()
        self.attempt.save(
            update_fields=[
                "status",
                "technical_passed_at",
            ]
        )

        self.client.login(username="owner", password="test-password")

        response = self.client.get(
            reverse("sandbox:task_detail", args=[self.attempt.id])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Ответ и диагностика")
        self.assertContains(response, "Отправить ответ на проверку")
        self.assertContains(response, "name=\"client_answer\"")
        self.assertContains(response, "name=\"trainee_report\"")

    def test_answer_form_is_hidden_when_manual_review_is_not_required(self):
        self.attempt.task.requires_manual_review = False
        self.attempt.task.save(update_fields=["requires_manual_review"])

        self.attempt.status = TaskAttempt.Status.PASSED
        self.attempt.technical_passed_at = timezone.now()
        self.attempt.finished_at = timezone.now()
        self.attempt.save(
            update_fields=[
                "status",
                "technical_passed_at",
                "finished_at",
            ]
        )

        self.client.login(username="owner", password="test-password")

        response = self.client.get(
            reverse("sandbox:task_detail", args=[self.attempt.id])
        )

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Ответ и диагностика")
        self.assertNotContains(response, "Отправить ответ на проверку")
        self.assertNotContains(response, "name=\"client_answer\"")
        self.assertNotContains(response, "name=\"trainee_report\"")

    def test_check_status_badge_is_visible_in_check_card(self):
        self.attempt.status = TaskAttempt.Status.IN_PROGRESS
        self.attempt.check_status = TaskAttempt.CheckStatus.FAILED
        self.attempt.last_check_output = "ERROR: nginx не запущен"
        self.attempt.save(
            update_fields=[
                "status",
                "check_status",
                "last_check_output",
            ]
        )

        self.client.login(username="owner", password="test-password")

        response = self.client.get(
            reverse("sandbox:task_detail", args=[self.attempt.id])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Не пройдена")
        self.assertContains(response, "ERROR: nginx не запущен")

    def test_failed_check_result_card_is_visible(self):
        self.attempt.status = TaskAttempt.Status.FAILED
        self.attempt.check_status = TaskAttempt.CheckStatus.FAILED
        self.attempt.last_check_output = "ERROR: nginx не запущен"
        self.attempt.save(
            update_fields=[
                "status",
                "check_status",
                "last_check_output",
            ]
        )

        self.client.login(username="owner", password="test-password")

        response = self.client.get(
            reverse("sandbox:task_detail", args=[self.attempt.id])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Автопроверка не пройдена")
        self.assertContains(response, "Нужно доработать техническую часть")
        self.assertContains(response, "ERROR: nginx не запущен")

    def test_error_check_result_card_is_visible(self):
        self.attempt.status = TaskAttempt.Status.FAILED
        self.attempt.check_status = TaskAttempt.CheckStatus.ERROR
        self.attempt.last_check_output = "Не удалось запустить автопроверку"
        self.attempt.save(
            update_fields=[
                "status",
                "check_status",
                "last_check_output",
            ]
        )

        self.client.login(username="owner", password="test-password")

        response = self.client.get(
            reverse("sandbox:task_detail", args=[self.attempt.id])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Автопроверка завершилась с ошибкой")
        self.assertContains(response, "Проверку не удалось выполнить")
        self.assertContains(response, "Не удалось запустить автопроверку")

    def test_check_button_shows_retry_text_after_failed_check(self):
        self.attempt.status = TaskAttempt.Status.FAILED
        self.attempt.check_status = TaskAttempt.CheckStatus.FAILED
        self.attempt.container_name = "task-container"
        self.attempt.terminal_url = "/terminal/1/24000/"
        self.attempt.terminal_port = 24000
        self.attempt.save(
            update_fields=[
                "status",
                "check_status",
                "container_name",
                "terminal_url",
                "terminal_port",
            ]
        )

        self.client.login(username="owner", password="test-password")

        response = self.client.get(
            reverse("sandbox:task_detail", args=[self.attempt.id])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Запустить автопроверку ещё раз")
        self.assertNotContains(response, "Сдать техническую часть")


class TaskFlowTests(SandboxTestCase):
    def setUp(self):
        self.queue = self.create_queue(
            slug="l1",
            name="ОТП Cloud L1",
            order=1,
            required_level=TraineeProfile.Level.L1,
        )

        self.task = self.create_task(
            queue=self.queue,
            slug="nginx-not-starting",
            order=1,
        )

        self.user = self.create_user(
            username="trainee",
            level=TraineeProfile.Level.L1,
        )

        self.attempt = TaskAttempt.objects.create(
            user=self.user,
            task=self.task,
        )

        self.client.login(username="trainee", password="test-password")

    @patch("sandbox.views.start_environment_in_background")
    def test_start_task_marks_environment_as_starting(
        self,
        start_environment_in_background_mock,
    ):
        response = self.client.post(
            reverse("sandbox:start_task", args=[self.attempt.id])
        )

        self.assertEqual(response.status_code, 302)

        self.attempt.refresh_from_db()

        self.assertEqual(self.attempt.status, TaskAttempt.Status.NEW)
        self.assertEqual(
            self.attempt.environment_status,
            TaskAttempt.EnvironmentStatus.STARTING,
        )
        self.assertIsNotNone(self.attempt.environment_started_at)
        self.assertIsNone(self.attempt.environment_finished_at)
        self.assertIn(
            "Окружение запускается",
            self.attempt.last_check_output,
        )

        start_environment_in_background_mock.assert_called_once_with(
            self.attempt.id
        )

        self.assertEqual(self.attempt.container_name, "")
        self.assertEqual(self.attempt.terminal_container_name, "")

    @patch("sandbox.views.start_environment_in_background")
    def test_start_task_does_not_start_background_when_environment_is_already_starting(
        self,
        start_environment_in_background_mock,
    ):
        self.attempt.environment_status = TaskAttempt.EnvironmentStatus.STARTING
        self.attempt.save(update_fields=["environment_status"])

        response = self.client.post(
            reverse("sandbox:start_task", args=[self.attempt.id])
        )

        self.assertEqual(response.status_code, 302)

        start_environment_in_background_mock.assert_not_called()

        self.attempt.refresh_from_db()

        self.assertEqual(
            self.attempt.environment_status,
            TaskAttempt.EnvironmentStatus.STARTING,
        )

    def test_check_task_requires_started_container(self):
        response = self.client.post(
            reverse("sandbox:check_task", args=[self.attempt.id]),
            data={
                "client_answer": "Здравствуйте, проблема исправлена.",
                "trainee_report": "Проверил nginx.",
            },
        )

        self.assertEqual(response.status_code, 302)

        self.attempt.refresh_from_db()

        self.assertEqual(self.attempt.status, TaskAttempt.Status.NEW)
        self.assertEqual(self.attempt.attempts_count, 0)

    

    def test_check_task_requires_client_answer(self):
        self.attempt.status = TaskAttempt.Status.IN_PROGRESS
        self.attempt.technical_passed_at = timezone.now()
        self.attempt.save(
            update_fields=[
                "status",
                "technical_passed_at",
            ]
        )

        response = self.client.post(
            reverse("sandbox:check_task", args=[self.attempt.id]),
            data={
                "client_answer": "",
                "trainee_report": "Проверил nginx.",
            },
        )

        self.assertEqual(response.status_code, 302)

        self.attempt.refresh_from_db()

        self.assertEqual(self.attempt.status, TaskAttempt.Status.IN_PROGRESS)
        self.assertEqual(self.attempt.attempts_count, 0)
        self.assertEqual(self.attempt.client_answer, "")
        self.assertEqual(self.attempt.trainee_report, "")

    def test_check_task_requires_trainee_report(self):
        self.attempt.status = TaskAttempt.Status.IN_PROGRESS
        self.attempt.technical_passed_at = timezone.now()
        self.attempt.save(
            update_fields=[
                "status",
                "technical_passed_at",
            ]
        )

        response = self.client.post(
            reverse("sandbox:check_task", args=[self.attempt.id]),
            data={
                "client_answer": "Здравствуйте, проблема исправлена.",
                "trainee_report": "",
            },
        )

        self.assertEqual(response.status_code, 302)

        self.attempt.refresh_from_db()

        self.assertEqual(self.attempt.status, TaskAttempt.Status.IN_PROGRESS)
        self.assertEqual(self.attempt.attempts_count, 0)
        self.assertEqual(self.attempt.client_answer, "")
        self.assertEqual(self.attempt.trainee_report, "")

    def test_check_task_after_technical_pass_sends_answer_to_review(self):
        self.attempt.task.requires_manual_review = True
        self.attempt.task.save(update_fields=["requires_manual_review"])

        self.attempt.status = TaskAttempt.Status.IN_PROGRESS
        self.attempt.technical_passed_at = timezone.now()
        self.attempt.save(
            update_fields=[
                "status",
                "technical_passed_at",
            ]
        )

        response = self.client.post(
            reverse("sandbox:check_task", args=[self.attempt.id]),
            data={
                "client_answer": "Здравствуйте, проблема исправлена.",
                "trainee_report": "Проверил nginx, нашел ошибку в конфиге и исправил ее.",
            },
        )

        self.assertEqual(response.status_code, 302)

        self.attempt.refresh_from_db()

        self.assertEqual(self.attempt.status, TaskAttempt.Status.ON_REVIEW)
        self.assertEqual(
            self.attempt.client_answer,
            "Здравствуйте, проблема исправлена.",
        )
        self.assertEqual(
            self.attempt.trainee_report,
            "Проверил nginx, нашел ошибку в конфиге и исправил ее.",
        )
        self.assertEqual(
            self.attempt.mentor_decision,
            TaskAttempt.MentorDecision.NOT_REVIEWED,
        )
        self.assertIsNone(self.attempt.mentor_reviewed_by)
        self.assertIsNone(self.attempt.mentor_reviewed_at)

    def test_check_task_on_review_does_not_overwrite_answer(self):
        self.attempt.task.requires_manual_review = True
        self.attempt.task.save(update_fields=["requires_manual_review"])

        self.attempt.status = TaskAttempt.Status.ON_REVIEW
        self.attempt.technical_passed_at = timezone.now()
        self.attempt.client_answer = "Старый ответ клиенту."
        self.attempt.trainee_report = "Старый внутренний комментарий."
        self.attempt.save(
            update_fields=[
                "status",
                "technical_passed_at",
                "client_answer",
                "trainee_report",
            ]
        )

        response = self.client.post(
            reverse("sandbox:check_task", args=[self.attempt.id]),
            data={
                "client_answer": "Новый ответ, который не должен сохраниться.",
                "trainee_report": "Новый комментарий, который не должен сохраниться.",
            },
        )

        self.assertEqual(response.status_code, 302)

        self.attempt.refresh_from_db()

        self.assertEqual(self.attempt.status, TaskAttempt.Status.ON_REVIEW)
        self.assertEqual(self.attempt.client_answer, "Старый ответ клиенту.")
        self.assertEqual(self.attempt.trainee_report, "Старый внутренний комментарий.")

    
    @patch("sandbox.views.notify_manual_review_required")
    def test_check_task_after_technical_pass_sends_manual_review_notification(
        self,
        notify_manual_review_required_mock,
    ):
        self.attempt.task.requires_manual_review = True
        self.attempt.task.save(update_fields=["requires_manual_review"])

        self.attempt.status = TaskAttempt.Status.IN_PROGRESS
        self.attempt.technical_passed_at = timezone.now()
        self.attempt.save(
            update_fields=[
                "status",
                "technical_passed_at",
            ]
        )

        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(
                reverse("sandbox:check_task", args=[self.attempt.id]),
                data={
                    "client_answer": "Здравствуйте, проблема исправлена.",
                    "trainee_report": "Проверил nginx, нашел ошибку в конфиге и исправил ее.",
                },
            )

        self.assertEqual(response.status_code, 302)

        self.attempt.refresh_from_db()

        self.assertEqual(self.attempt.status, TaskAttempt.Status.ON_REVIEW)
        notify_manual_review_required_mock.assert_called_once()

        notified_attempt = notify_manual_review_required_mock.call_args.args[0]
        self.assertEqual(notified_attempt.id, self.attempt.id)

    @patch("sandbox.views.get_free_port")
    @patch("sandbox.views.create_terminal_container")
    @patch("sandbox.views.create_task_container")
    @patch("sandbox.views.remove_task_container")
    @patch("sandbox.views.remove_terminal_container")
    def test_restart_task_removes_old_containers_and_creates_new_environment(
        self,
        remove_terminal_container_mock,
        remove_task_container_mock,
        create_task_container_mock,
        create_terminal_container_mock,
        get_free_port_mock,
    ):
        self.attempt.status = TaskAttempt.Status.FAILED
        self.attempt.container_id = "old-container-id"
        self.attempt.container_name = "old-task-container"
        self.attempt.terminal_container_name = "old-terminal-container"
        self.attempt.terminal_port = 24000
        self.attempt.terminal_url = "http://localhost:24000"
        self.attempt.shell_command = "docker exec -it old-task-container bash"
        self.attempt.finished_at = timezone.now()
        self.attempt.restart_count = 1
        self.attempt.save()

        remove_terminal_container_mock.return_value = (
            True,
            "Старый терминал удален.",
        )

        remove_task_container_mock.return_value = (
            True,
            "Старый контейнер удален.",
        )

        create_task_container_mock.return_value = SimpleNamespace(
            id="new-container-id",
            name="new-task-container",
        )

        create_terminal_container_mock.return_value = SimpleNamespace(
            name="new-terminal-container",
        )

        get_free_port_mock.return_value = 25001

        response = self.client.post(
            reverse("sandbox:restart_task", args=[self.attempt.id])
        )

        self.assertEqual(response.status_code, 302)

        remove_terminal_container_mock.assert_called_once_with(
            "old-terminal-container"
        )

        remove_task_container_mock.assert_called_once_with(
            "old-task-container"
        )

        self.attempt.refresh_from_db()

        self.assertEqual(self.attempt.status, TaskAttempt.Status.IN_PROGRESS)
        self.assertEqual(self.attempt.restart_count, 2)
        self.assertIsNone(self.attempt.finished_at)

        self.assertEqual(self.attempt.container_id, "new-container-id")
        self.assertEqual(self.attempt.container_name, "new-task-container")
        self.assertEqual(
            self.attempt.terminal_container_name,
            "new-terminal-container",
        )
        self.assertEqual(self.attempt.terminal_port, 25001)
        self.assertIn(
            "docker exec -it new-task-container bash",
            self.attempt.shell_command,
        )
        self.assertIn(
            "перезапущен",
            self.attempt.last_check_output,
        )

    @patch("sandbox.views.remove_task_container")
    @patch("sandbox.views.remove_terminal_container")
    @patch("sandbox.views.create_task_container")
    def test_restart_task_handles_docker_api_error(
        self,
        create_task_container_mock,
        remove_terminal_container_mock,
        remove_task_container_mock,
    ):
        self.attempt.status = TaskAttempt.Status.IN_PROGRESS
        self.attempt.container_name = "old-task-container"
        self.attempt.terminal_container_name = "old-terminal-container"
        self.attempt.save(
            update_fields=[
                "status",
                "container_name",
                "terminal_container_name",
            ]
        )

        create_task_container_mock.side_effect = RuntimeError(
            "Docker API unavailable"
        )

        response = self.client.post(
            reverse("sandbox:restart_task", args=[self.attempt.id])
        )

        self.assertEqual(response.status_code, 302)

        remove_terminal_container_mock.assert_called_once_with(
            "old-terminal-container"
        )
        remove_task_container_mock.assert_called_once_with(
            "old-task-container"
        )

        self.attempt.refresh_from_db()

        self.assertEqual(self.attempt.status, TaskAttempt.Status.FAILED)
        self.assertIn(
            "Не удалось перезапустить окружение из-за ошибки Docker API.",
            self.attempt.last_check_output,
        )
        self.assertIn(
            "Docker API unavailable",
            self.attempt.last_check_output,
        )

    @patch("sandbox.views.start_environment_in_background")
    def test_start_task_does_not_start_locked_task(
        self,
        start_environment_in_background_mock,
    ):
        second_task = self.create_task(
            queue=self.queue,
            slug="second-task",
            order=2,
        )

        second_attempt = TaskAttempt.objects.create(
            user=self.user,
            task=second_task,
        )

        response = self.client.post(
            reverse("sandbox:start_task", args=[second_attempt.id])
        )

        self.assertEqual(response.status_code, 302)

        start_environment_in_background_mock.assert_not_called()

        second_attempt.refresh_from_db()

        self.assertEqual(second_attempt.status, TaskAttempt.Status.NEW)
        self.assertEqual(second_attempt.container_name, "")

    @patch("sandbox.services.checks.check_task_container")
    def test_passed_task_is_not_checked_again(
        self,
        check_task_container_mock,
    ):
        self.attempt.status = TaskAttempt.Status.PASSED
        self.attempt.container_name = "task-container"
        self.attempt.attempts_count = 1
        self.attempt.save()

        response = self.client.post(
            reverse("sandbox:check_task", args=[self.attempt.id]),
            data={
                "client_answer": "Здравствуйте, проблема исправлена.",
                "trainee_report": "Проверил nginx.",
            },
        )

        self.assertEqual(response.status_code, 302)

        check_task_container_mock.assert_not_called()

        self.attempt.refresh_from_db()

        self.assertEqual(self.attempt.status, TaskAttempt.Status.PASSED)
        self.assertEqual(self.attempt.attempts_count, 1)

    @patch("sandbox.services.checks.check_task_container")
    def test_on_review_task_is_not_checked_again(
        self,
        check_task_container_mock,
    ):
        self.attempt.status = TaskAttempt.Status.ON_REVIEW
        self.attempt.container_name = "task-container"
        self.attempt.client_answer = "Здравствуйте, проблема исправлена."
        self.attempt.trainee_report = "Проверил nginx."
        self.attempt.save()

        response = self.client.post(
            reverse("sandbox:check_task", args=[self.attempt.id]),
            data={
                "client_answer": "Здравствуйте, проблема исправлена.",
                "trainee_report": "Проверил nginx.",
            },
        )

        self.assertEqual(response.status_code, 302)

        check_task_container_mock.assert_not_called()

        self.attempt.refresh_from_db()

        self.assertEqual(self.attempt.status, TaskAttempt.Status.ON_REVIEW)
        self.assertEqual(self.attempt.attempts_count, 0)

    @patch("sandbox.views.remove_task_container")
    @patch("sandbox.views.remove_terminal_container")
    def test_restart_task_does_not_remove_containers_for_locked_task(
        self,
        remove_terminal_container_mock,
        remove_task_container_mock,
    ):
        locked_task = self.create_task(
            queue=self.queue,
            slug="locked-restart-task",
            order=2,
        )

        locked_attempt = TaskAttempt.objects.create(
            user=self.user,
            task=locked_task,
            status=TaskAttempt.Status.IN_PROGRESS,
            container_name="locked-task-container",
            terminal_container_name="locked-terminal-container",
        )

        response = self.client.post(
            reverse("sandbox:restart_task", args=[locked_attempt.id])
        )

        self.assertEqual(response.status_code, 302)

        remove_terminal_container_mock.assert_not_called()
        remove_task_container_mock.assert_not_called()

        locked_attempt.refresh_from_db()

        self.assertEqual(
            locked_attempt.container_name,
            "locked-task-container",
        )
        self.assertEqual(
            locked_attempt.terminal_container_name,
            "locked-terminal-container",
        )

    @patch("sandbox.views.start_environment_in_background")
    def test_next_task_is_available_after_previous_technical_pass(
        self,
        start_environment_in_background_mock,
    ):
        self.attempt.status = TaskAttempt.Status.ON_REVIEW
        self.attempt.technical_passed_at = timezone.now()
        self.attempt.save(
            update_fields=[
                "status",
                "technical_passed_at",
            ]
        )

        second_task = self.create_task(
            queue=self.queue,
            slug="second-task-after-technical-pass",
            order=2,
        )

        second_attempt = TaskAttempt.objects.create(
            user=self.user,
            task=second_task,
        )

        response = self.client.post(
            reverse("sandbox:start_task", args=[second_attempt.id])
        )

        self.assertEqual(response.status_code, 302)

        start_environment_in_background_mock.assert_called_once_with(
            second_attempt.id
        )

        second_attempt.refresh_from_db()

        self.assertEqual(second_attempt.status, TaskAttempt.Status.NEW)
        self.assertEqual(
            second_attempt.environment_status,
            TaskAttempt.EnvironmentStatus.STARTING,
        )
        self.assertEqual(second_attempt.container_name, "")

    @patch("sandbox.services.checks.check_task_container")
    def test_manual_review_resubmit_does_not_require_container(
        self,
        check_task_container_mock,
    ):
        self.task.requires_manual_review = True
        self.task.save(update_fields=["requires_manual_review"])

        self.attempt.status = TaskAttempt.Status.FAILED
        self.attempt.technical_passed_at = timezone.now()
        self.attempt.container_name = ""
        self.attempt.client_answer = "Старый ответ клиенту."
        self.attempt.trainee_report = "Старый отчет."
        self.attempt.mentor_decision = TaskAttempt.MentorDecision.NEEDS_REVISION
        self.attempt.mentor_feedback = "Поправь ответ клиенту."
        self.attempt.mentor_reviewed_at = timezone.now()
        self.attempt.save(
            update_fields=[
                "status",
                "technical_passed_at",
                "container_name",
                "client_answer",
                "trainee_report",
                "mentor_decision",
                "mentor_feedback",
                "mentor_reviewed_at",
            ]
        )

        response = self.client.post(
            reverse("sandbox:check_task", args=[self.attempt.id]),
            data={
                "client_answer": "Доработанный ответ клиенту.",
                "trainee_report": "Доработал ответ по комментарию наставника.",
            },
        )

        self.assertEqual(response.status_code, 302)

        check_task_container_mock.assert_not_called()

        self.attempt.refresh_from_db()

        self.assertEqual(self.attempt.status, TaskAttempt.Status.ON_REVIEW)
        self.assertEqual(
            self.attempt.mentor_decision,
            TaskAttempt.MentorDecision.NOT_REVIEWED,
        )
        self.assertEqual(
            self.attempt.client_answer,
            "Доработанный ответ клиенту.",
        )
        self.assertEqual(
            self.attempt.trainee_report,
            "Доработал ответ по комментарию наставника.",
        )

    @patch("sandbox.views.start_attempt_check_in_background")
    def test_check_task_starts_background_check(
        self,
        start_attempt_check_in_background_mock,
    ):
        self.attempt.status = TaskAttempt.Status.IN_PROGRESS
        self.attempt.container_name = "task-container"
        self.attempt.save(
            update_fields=[
                "status",
                "container_name",
            ]
        )

        response = self.client.post(
            reverse("sandbox:check_task", args=[self.attempt.id]),
            data={
                "client_answer": "Здравствуйте, проблема исправлена.",
                "trainee_report": "Проверил nginx.",
            },
        )

        self.assertEqual(response.status_code, 302)

        start_attempt_check_in_background_mock.return_value = object()

        called_attempt = start_attempt_check_in_background_mock.call_args.kwargs["attempt"]
        called_user_id = start_attempt_check_in_background_mock.call_args.kwargs["user_id"]

        self.assertEqual(called_attempt.id, self.attempt.id)
        self.assertEqual(called_user_id, self.user.id)

    @patch("sandbox.views.start_attempt_check_in_background")
    def test_check_task_shows_already_running_message_when_background_was_not_started(
        self,
        start_attempt_check_in_background_mock,
    ):
        self.attempt.status = TaskAttempt.Status.IN_PROGRESS
        self.attempt.container_name = "task-container"
        self.attempt.save(
            update_fields=[
                "status",
                "container_name",
            ]
        )

        start_attempt_check_in_background_mock.return_value = None

        response = self.client.post(
            reverse("sandbox:check_task", args=[self.attempt.id]),
            data={
                "client_answer": "Здравствуйте, проблема исправлена.",
                "trainee_report": "Проверил nginx.",
            },
            follow=True,
        )

        self.assertEqual(response.status_code, 200)

        messages_text = [str(message) for message in response.context["messages"]]

        self.assertIn(
            "Автопроверка уже выполняется. Дождись результата.",
            messages_text,
        )

    @patch("sandbox.views.start_attempt_check_in_background")
    def test_check_task_does_not_start_background_check_when_check_is_running(
        self,
        start_attempt_check_in_background_mock,
    ):
        self.attempt.status = TaskAttempt.Status.IN_PROGRESS
        self.attempt.container_name = "task-container"
        self.attempt.check_status = TaskAttempt.CheckStatus.RUNNING
        self.attempt.save(
            update_fields=[
                "status",
                "container_name",
                "check_status",
            ]
        )

        response = self.client.post(
            reverse("sandbox:check_task", args=[self.attempt.id]),
            data={
                "client_answer": "Здравствуйте, проблема исправлена.",
                "trainee_report": "Проверил nginx.",
            },
        )

        self.assertEqual(response.status_code, 302)

        start_attempt_check_in_background_mock.assert_not_called()


class TaskActionAccessTests(SandboxTestCase):
    def setUp(self):
        self.queue = self.create_queue(
            slug="l1",
            name="ОТП Cloud L1",
            order=1,
            required_level=TraineeProfile.Level.L1,
        )

        self.task = self.create_task(
            queue=self.queue,
            slug="access-task",
            order=1,
        )

        self.owner = self.create_user(
            username="action-owner",
            level=TraineeProfile.Level.L1,
        )

        self.other_user = self.create_user(
            username="action-other-user",
            level=TraineeProfile.Level.L1,
        )

        self.attempt = TaskAttempt.objects.create(
            user=self.owner,
            task=self.task,
        )

        self.client.login(
            username="action-other-user",
            password="test-password",
        )

    def test_other_user_cannot_start_attempt(self):
        response = self.client.post(
            reverse("sandbox:start_task", args=[self.attempt.id])
        )

        self.assertEqual(response.status_code, 404)

    def test_other_user_cannot_restart_attempt(self):
        response = self.client.post(
            reverse("sandbox:restart_task", args=[self.attempt.id])
        )

        self.assertEqual(response.status_code, 404)

    def test_other_user_cannot_check_attempt(self):
        response = self.client.post(
            reverse("sandbox:check_task", args=[self.attempt.id]),
            data={
                "client_answer": "Ответ клиенту.",
                "trainee_report": "Комментарий по диагностике.",
            },
        )

        self.assertEqual(response.status_code, 404)


class AuthenticationRequiredTests(SandboxTestCase):
    def setUp(self):
        self.queue = self.create_queue(
            slug="l1",
            name="ОТП Cloud L1",
            order=1,
            required_level=TraineeProfile.Level.L1,
        )

        self.task = self.create_task(
            queue=self.queue,
            slug="auth-task",
            order=1,
        )

        self.user = self.create_user(
            username="auth-user",
            level=TraineeProfile.Level.L1,
        )

        self.attempt = TaskAttempt.objects.create(
            user=self.user,
            task=self.task,
        )

    def assert_redirects_to_login(self, response):
        self.assertEqual(response.status_code, 302)

        login_url = resolve_url(settings.LOGIN_URL)

        self.assertTrue(
            response["Location"].startswith(login_url),
            f"Expected redirect to {login_url}, got {response['Location']}",
        )

        self.assertIn("next=", response["Location"])

    def test_dashboard_requires_login(self):
        response = self.client.get(reverse("sandbox:dashboard"))

        self.assert_redirects_to_login(response)

    def test_task_detail_requires_login(self):
        response = self.client.get(
            reverse("sandbox:task_detail", args=[self.attempt.id])
        )

        self.assert_redirects_to_login(response)

    def test_start_task_requires_login(self):
        response = self.client.post(
            reverse("sandbox:start_task", args=[self.attempt.id])
        )

        self.assert_redirects_to_login(response)

    def test_restart_task_requires_login(self):
        response = self.client.post(
            reverse("sandbox:restart_task", args=[self.attempt.id])
        )

        self.assert_redirects_to_login(response)

    def test_check_task_requires_login(self):
        response = self.client.post(
            reverse("sandbox:check_task", args=[self.attempt.id]),
            data={
                "client_answer": "Ответ клиенту.",
                "trainee_report": "Комментарий по диагностике.",
            },
        )

        self.assert_redirects_to_login(response)
