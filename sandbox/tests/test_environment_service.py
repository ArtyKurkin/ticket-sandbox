from types import SimpleNamespace
from unittest.mock import patch

from sandbox.models import TaskAttempt, TraineeProfile
from sandbox.services.environments import (
    ENVIRONMENT_STARTING_OUTPUT,
    mark_environment_start_error,
    mark_environment_starting,
    run_environment_start,
)

from .base import SandboxTestCase


class EnvironmentServiceTests(SandboxTestCase):
    def setUp(self):
        self.queue = self.create_queue(
            slug="l1",
            name="ОТП Cloud L1",
            order=1,
            required_level=TraineeProfile.Level.L1,
        )
        self.user = self.create_user(
            username="environment-trainee",
            level=TraineeProfile.Level.L1,
        )
        self.task = self.create_task(
            queue=self.queue,
            slug="environment-task",
            order=1,
        )
        self.attempt = TaskAttempt.objects.create(
            user=self.user,
            task=self.task,
        )

    def test_mark_environment_starting_updates_attempt_state(self):
        mark_environment_starting(self.attempt)

        self.attempt.refresh_from_db()

        self.assertEqual(
            self.attempt.environment_status,
            TaskAttempt.EnvironmentStatus.STARTING,
        )
        self.assertIsNotNone(self.attempt.environment_started_at)
        self.assertIsNone(self.attempt.environment_finished_at)
        self.assertEqual(
            self.attempt.last_check_output,
            ENVIRONMENT_STARTING_OUTPUT,
        )

    @patch("sandbox.services.environments.get_free_port")
    @patch("sandbox.services.environments.create_terminal_container")
    @patch("sandbox.services.environments.create_task_container")
    def test_run_environment_start_creates_task_and_terminal_containers(
        self,
        create_task_container_mock,
        create_terminal_container_mock,
        get_free_port_mock,
    ):
        create_task_container_mock.return_value = SimpleNamespace(
            id="task-container-id",
            name="task-container-name",
        )
        create_terminal_container_mock.return_value = SimpleNamespace(
            name="terminal-container-name",
        )
        get_free_port_mock.return_value = 25001

        mark_environment_starting(self.attempt)
        run_environment_start(self.attempt)

        self.attempt.refresh_from_db()

        create_task_container_mock.assert_called_once_with(
            queue_slug="l1",
            task_slug="environment-task",
            attempt_id=self.attempt.id,
        )
        create_terminal_container_mock.assert_called_once()
        get_free_port_mock.assert_called_once()

        self.assertEqual(self.attempt.status, TaskAttempt.Status.IN_PROGRESS)
        self.assertIsNotNone(self.attempt.started_at)

        self.assertEqual(self.attempt.container_id, "task-container-id")
        self.assertEqual(self.attempt.container_name, "task-container-name")
        self.assertEqual(
            self.attempt.terminal_container_name,
            "terminal-container-name",
        )
        self.assertEqual(self.attempt.terminal_port, 25001)
        self.assertIn(
            f"/terminal/{self.attempt.id}/25001/",
            self.attempt.terminal_url,
        )
        self.assertEqual(
            self.attempt.shell_command,
            "docker exec -it task-container-name bash",
        )
        self.assertEqual(
            self.attempt.last_check_output,
            "Контейнер task-container-name успешно создан.",
        )
        self.assertEqual(
            self.attempt.environment_status,
            TaskAttempt.EnvironmentStatus.READY,
        )
        self.assertIsNotNone(self.attempt.environment_started_at)
        self.assertIsNotNone(self.attempt.environment_finished_at)

    def test_mark_environment_start_error_updates_attempt_state(self):
        mark_environment_starting(self.attempt)

        mark_environment_start_error(
            self.attempt,
            RuntimeError("Docker API unavailable"),
        )

        self.attempt.refresh_from_db()

        self.assertEqual(self.attempt.status, TaskAttempt.Status.FAILED)
        self.assertEqual(
            self.attempt.environment_status,
            TaskAttempt.EnvironmentStatus.ERROR,
        )
        self.assertIsNotNone(self.attempt.environment_started_at)
        self.assertIsNotNone(self.attempt.environment_finished_at)
        self.assertIn(
            "Не удалось запустить окружение задания из-за ошибки Docker API.",
            self.attempt.last_check_output,
        )
        self.assertIn(
            "Docker API unavailable",
            self.attempt.last_check_output,
        )
