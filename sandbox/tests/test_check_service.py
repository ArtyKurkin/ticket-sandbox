from unittest.mock import patch

from django.utils import timezone

from sandbox.models import TaskAttempt, TraineeProfile
from sandbox.services.checks import (
    CHECK_STARTED_OUTPUT,
    run_attempt_check,
    start_attempt_check_in_background,
    try_mark_attempt_check_running,

)
from sandbox.tests.base import SandboxTestCase


class CheckServiceTests(SandboxTestCase):
    def setUp(self):
        self.queue = self.create_queue(
            slug="l1",
            name="ОТП Cloud L1",
            order=1,
            required_level=TraineeProfile.Level.L1,
        )
        self.user = self.create_user(
            username="trainee",
            level=TraineeProfile.Level.L1,
        )
        self.task = self.create_task(
            queue=self.queue,
            slug="check-service-task",
            order=1,
        )
        self.attempt = TaskAttempt.objects.create(
            user=self.user,
            task=self.task,
            status=TaskAttempt.Status.IN_PROGRESS,
            container_name="task-container",
        )

    @patch("sandbox.services.checks.threading.Thread")
    def test_start_attempt_check_in_background_marks_attempt_running_and_starts_thread(
        self,
        thread_mock,
    ):
        thread_instance = thread_mock.return_value

        result = start_attempt_check_in_background(
            attempt=self.attempt,
            user_id=self.user.id,
        )

        self.attempt.refresh_from_db()

        self.assertEqual(self.attempt.status, TaskAttempt.Status.IN_PROGRESS)
        self.assertEqual(
            self.attempt.check_status,
            TaskAttempt.CheckStatus.RUNNING,
        )
        self.assertEqual(self.attempt.attempts_count, 1)
        self.assertIsNotNone(self.attempt.check_started_at)
        self.assertIsNone(self.attempt.check_finished_at)
        self.assertEqual(self.attempt.last_check_output, CHECK_STARTED_OUTPUT)

        thread_mock.assert_called_once()
        thread_instance.start.assert_called_once()
        self.assertEqual(result, thread_instance)

    @patch("sandbox.services.checks.check_task_container")
    def test_run_attempt_check_without_mark_as_running_does_not_increment_attempts_count(
        self,
        check_task_container_mock,
    ):
        self.attempt.attempts_count = 3
        self.attempt.check_status = TaskAttempt.CheckStatus.RUNNING
        self.attempt.check_started_at = timezone.now()
        self.attempt.save(
            update_fields=[
                "attempts_count",
                "check_status",
                "check_started_at",
            ]
        )

        check_task_container_mock.return_value = (
            1,
            "ERROR: проверка не пройдена",
        )

        result = run_attempt_check(
            attempt=self.attempt,
            user_id=self.user.id,
            mark_as_running=False,
        )

        self.attempt.refresh_from_db()

        self.assertFalse(result.is_success)
        self.assertEqual(self.attempt.attempts_count, 3)
        self.assertEqual(
            self.attempt.check_status,
            TaskAttempt.CheckStatus.FAILED,
        )
        self.assertIsNotNone(self.attempt.check_finished_at)
        self.assertIn(
            "ERROR: проверка не пройдена",
            self.attempt.last_check_output,
        )

    @patch("sandbox.services.checks.notify_user_completed_all_tasks")
    @patch("sandbox.services.checks.remove_task_container")
    @patch("sandbox.services.checks.remove_terminal_container")
    @patch("sandbox.services.checks.check_task_container")
    def test_run_attempt_check_marks_attempt_passed_and_cleans_containers(
        self,
        check_task_container_mock,
        remove_terminal_container_mock,
        remove_task_container_mock,
        notify_user_completed_all_tasks_mock,
    ):
        self.task.requires_manual_review = False
        self.task.save(update_fields=["requires_manual_review"])

        self.attempt.terminal_container_name = "terminal-container"
        self.attempt.save(update_fields=["terminal_container_name"])

        check_task_container_mock.return_value = (
            0,
            "OK: техническая часть выполнена",
        )
        remove_terminal_container_mock.return_value = (
            True,
            "Терминал удален.",
        )
        remove_task_container_mock.return_value = (
            True,
            "Контейнер удален.",
        )

        with self.captureOnCommitCallbacks(execute=True):
            result = run_attempt_check(
                attempt=self.attempt,
                user_id=self.user.id,
            )

        self.attempt.refresh_from_db()

        self.assertTrue(result.is_success)
        self.assertEqual(self.attempt.status, TaskAttempt.Status.PASSED)
        self.assertEqual(
            self.attempt.check_status,
            TaskAttempt.CheckStatus.PASSED,
        )
        self.assertIsNotNone(self.attempt.technical_passed_at)
        self.assertIsNotNone(self.attempt.check_started_at)
        self.assertIsNotNone(self.attempt.check_finished_at)
        self.assertEqual(self.attempt.container_name, "")
        self.assertEqual(self.attempt.terminal_container_name, "")

        notify_user_completed_all_tasks_mock.assert_called_once()

    @patch("sandbox.services.checks.remove_task_container")
    @patch("sandbox.services.checks.remove_terminal_container")
    @patch("sandbox.services.checks.check_task_container")
    def test_run_attempt_check_with_manual_review_keeps_attempt_in_progress(
        self,
        check_task_container_mock,
        remove_terminal_container_mock,
        remove_task_container_mock,
    ):
        self.task.requires_manual_review = True
        self.task.save(update_fields=["requires_manual_review"])

        self.attempt.terminal_container_name = "terminal-container"
        self.attempt.save(update_fields=["terminal_container_name"])

        check_task_container_mock.return_value = (
            0,
            "OK: техническая часть выполнена",
        )
        remove_terminal_container_mock.return_value = (
            True,
            "Терминал удален.",
        )
        remove_task_container_mock.return_value = (
            True,
            "Контейнер удален.",
        )

        result = run_attempt_check(
            attempt=self.attempt,
            user_id=self.user.id,
        )

        self.attempt.refresh_from_db()

        self.assertTrue(result.is_success)
        self.assertEqual(self.attempt.status, TaskAttempt.Status.IN_PROGRESS)
        self.assertEqual(
            self.attempt.check_status,
            TaskAttempt.CheckStatus.PASSED,
        )
        self.assertIsNotNone(self.attempt.technical_passed_at)
        self.assertIsNone(self.attempt.finished_at)
        self.assertEqual(self.attempt.client_answer, "")
        self.assertEqual(self.attempt.trainee_report, "")
        self.assertEqual(self.attempt.container_name, "")
        self.assertEqual(self.attempt.terminal_container_name, "")

    @patch("sandbox.services.checks.check_task_container")
    def test_run_attempt_check_marks_attempt_failed_on_check_failure(
        self,
        check_task_container_mock,
    ):
        check_task_container_mock.return_value = (
            1,
            "ERROR: nginx не запущен",
        )

        result = run_attempt_check(
            attempt=self.attempt,
            user_id=self.user.id,
        )

        self.attempt.refresh_from_db()

        self.assertFalse(result.is_success)
        self.assertEqual(self.attempt.status, TaskAttempt.Status.FAILED)
        self.assertEqual(
            self.attempt.check_status,
            TaskAttempt.CheckStatus.FAILED,
        )
        self.assertIsNotNone(self.attempt.check_started_at)
        self.assertIsNotNone(self.attempt.check_finished_at)
        self.assertIn("ERROR: nginx не запущен", self.attempt.last_check_output)

    @patch("sandbox.services.checks.check_task_container")
    def test_run_attempt_check_marks_attempt_error_on_docker_error(
        self,
        check_task_container_mock,
    ):
        check_task_container_mock.side_effect = RuntimeError(
            "Docker daemon unavailable"
        )

        result = run_attempt_check(
            attempt=self.attempt,
            user_id=self.user.id,
        )

        self.attempt.refresh_from_db()

        self.assertFalse(result.is_success)
        self.assertEqual(self.attempt.status, TaskAttempt.Status.FAILED)
        self.assertEqual(
            self.attempt.check_status,
            TaskAttempt.CheckStatus.ERROR,
        )
        self.assertIsNotNone(self.attempt.check_started_at)
        self.assertIsNotNone(self.attempt.check_finished_at)
        self.assertIn(
            "Не удалось запустить автопроверку",
            self.attempt.last_check_output,
        )
        self.assertIn(
            "Docker daemon unavailable",
            self.attempt.last_check_output,
        )

    def test_try_mark_attempt_check_running_marks_attempt_running(self):
        result = try_mark_attempt_check_running(attempt=self.attempt)

        self.attempt.refresh_from_db()

        self.assertTrue(result)
        self.assertEqual(self.attempt.status, TaskAttempt.Status.IN_PROGRESS)
        self.assertEqual(
            self.attempt.check_status,
            TaskAttempt.CheckStatus.RUNNING,
        )
        self.assertEqual(self.attempt.attempts_count, 1)
        self.assertIsNotNone(self.attempt.check_started_at)
        self.assertIsNone(self.attempt.check_finished_at)
        self.assertEqual(self.attempt.last_check_output, CHECK_STARTED_OUTPUT)

    def test_try_mark_attempt_check_running_returns_false_when_already_running(self):
        self.attempt.check_status = TaskAttempt.CheckStatus.RUNNING
        self.attempt.attempts_count = 1
        self.attempt.check_started_at = timezone.now()
        self.attempt.save(
            update_fields=[
                "check_status",
                "attempts_count",
                "check_started_at",
            ]
        )

        result = try_mark_attempt_check_running(attempt=self.attempt)

        self.attempt.refresh_from_db()

        self.assertFalse(result)
        self.assertEqual(self.attempt.attempts_count, 1)
        self.assertEqual(
            self.attempt.check_status,
            TaskAttempt.CheckStatus.RUNNING,
        )

    @patch("sandbox.services.checks.threading.Thread")
    def test_start_attempt_check_in_background_does_not_start_thread_when_already_running(
        self,
        thread_mock,
    ):
        self.attempt.check_status = TaskAttempt.CheckStatus.RUNNING
        self.attempt.attempts_count = 1
        self.attempt.save(
            update_fields=[
                "check_status",
                "attempts_count",
            ]
        )

        result = start_attempt_check_in_background(
            attempt=self.attempt,
            user_id=self.user.id,
        )

        self.attempt.refresh_from_db()

        self.assertIsNone(result)
        self.assertEqual(self.attempt.attempts_count, 1)
        thread_mock.assert_not_called()

    def test_try_mark_attempt_check_running_replaces_previous_check_output(self):
        self.attempt.status = TaskAttempt.Status.FAILED
        self.attempt.check_status = TaskAttempt.CheckStatus.FAILED
        self.attempt.last_check_output = "ERROR: старая ошибка проверки"
        self.attempt.save(
            update_fields=[
                "status",
                "check_status",
                "last_check_output",
            ]
        )

        result = try_mark_attempt_check_running(attempt=self.attempt)

        self.attempt.refresh_from_db()

        self.assertTrue(result)
        self.assertEqual(
            self.attempt.check_status,
            TaskAttempt.CheckStatus.RUNNING,
        )
        self.assertEqual(self.attempt.last_check_output, CHECK_STARTED_OUTPUT)
