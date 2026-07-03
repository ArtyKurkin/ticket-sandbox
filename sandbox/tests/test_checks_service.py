from unittest.mock import patch

from sandbox.models import TaskAttempt, TraineeProfile
from sandbox.services.checks import _run_attempt_check_background

from .base import SandboxTestCase


class ChecksServiceBackgroundTests(SandboxTestCase):
    def setUp(self):
        self.queue = self.create_queue(
            slug="l1",
            name="ОТП Cloud L1",
            order=1,
            required_level=TraineeProfile.Level.L1,
        )
        self.user = self.create_user(
            username="checks-trainee",
            level=TraineeProfile.Level.L1,
        )
        self.task = self.create_task(
            queue=self.queue,
            slug="checks-task",
            order=1,
        )
        self.attempt = TaskAttempt.objects.create(
            user=self.user,
            task=self.task,
            status=TaskAttempt.Status.IN_PROGRESS,
            check_status=TaskAttempt.CheckStatus.RUNNING,
        )

    @patch("sandbox.services.checks.close_old_connections")
    @patch("sandbox.services.checks.capture_exception")
    @patch("sandbox.services.checks.run_attempt_check")
    def test_attempt_check_background_captures_exception(
        self,
        run_attempt_check_mock,
        capture_exception_mock,
        close_old_connections_mock,
    ):
        error = RuntimeError("Docker API unavailable")
        run_attempt_check_mock.side_effect = error

        _run_attempt_check_background(
            attempt_id=self.attempt.id,
            user_id=self.user.id,
        )

        capture_exception_mock.assert_called_once_with(error)

        self.attempt.refresh_from_db()

        self.assertEqual(self.attempt.status, TaskAttempt.Status.FAILED)
        self.assertEqual(
            self.attempt.check_status,
            TaskAttempt.CheckStatus.ERROR,
        )
        self.assertIsNotNone(self.attempt.check_finished_at)
        self.assertIn(
            "Неожиданная ошибка фоновой автопроверки.",
            self.attempt.last_check_output,
        )
