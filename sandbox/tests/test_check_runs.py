from unittest.mock import patch

from sandbox.models import CheckRun, TaskAttempt, TraineeProfile
from sandbox.services.checks import run_attempt_check

from .base import SandboxTestCase


class CheckRunTests(SandboxTestCase):
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
            slug="check-run-task",
            order=1,
        )

        self.attempt = TaskAttempt.objects.create(
            user=self.user,
            task=self.task,
            status=TaskAttempt.Status.IN_PROGRESS,
            container_name="task-container",
        )

    @patch("sandbox.services.checks.notify_user_completed_all_tasks")
    @patch("sandbox.services.checks.remove_task_container")
    @patch("sandbox.services.checks.check_task_container")
    def test_successful_check_creates_passed_check_run(
        self,
        check_task_container_mock,
        remove_task_container_mock,
        notify_user_completed_all_tasks_mock,
    ):
        self.task.requires_manual_review = False
        self.task.save(update_fields=["requires_manual_review"])

        check_task_container_mock.return_value = (
            0,
            "OK: проверка пройдена",
        )
        remove_task_container_mock.return_value = (
            True,
            "Контейнер удален.",
        )

        with self.captureOnCommitCallbacks(execute=True):
            run_attempt_check(
                attempt=self.attempt,
                user_id=self.user.id,
            )

        check_run = CheckRun.objects.get(attempt=self.attempt)

        self.assertEqual(check_run.result, CheckRun.Result.PASSED)
        self.assertEqual(check_run.exit_code, 0)
        self.assertEqual(check_run.output, "OK: проверка пройдена")

        notify_user_completed_all_tasks_mock.assert_called_once()

    @patch("sandbox.services.checks.check_task_container")
    def test_failed_check_creates_failed_check_run(
        self,
        check_task_container_mock,
    ):
        check_task_container_mock.return_value = (
            1,
            "ERROR: проверка не пройдена",
        )

        run_attempt_check(
            attempt=self.attempt,
            user_id=self.user.id,
        )

        check_run = CheckRun.objects.get(attempt=self.attempt)

        self.assertEqual(check_run.result, CheckRun.Result.FAILED)
        self.assertEqual(check_run.exit_code, 1)
        self.assertEqual(check_run.output, "ERROR: проверка не пройдена")

    @patch("sandbox.services.checks.check_task_container")
    def test_each_check_creates_separate_check_run(
        self,
        check_task_container_mock,
    ):
        check_task_container_mock.side_effect = [
            (
                1,
                "ERROR: первая проверка",
            ),
            (
                1,
                "ERROR: вторая проверка",
            ),
        ]

        run_attempt_check(
            attempt=self.attempt,
            user_id=self.user.id,
        )

        self.attempt.refresh_from_db()

        run_attempt_check(
            attempt=self.attempt,
            user_id=self.user.id,
        )

        check_runs = CheckRun.objects.filter(
            attempt=self.attempt,
        ).order_by("created_at")

        self.assertEqual(check_runs.count(), 2)
        self.assertEqual(check_runs[0].output, "ERROR: первая проверка")
        self.assertEqual(check_runs[1].output, "ERROR: вторая проверка")
