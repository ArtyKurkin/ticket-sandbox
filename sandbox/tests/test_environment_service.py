from types import SimpleNamespace
from unittest.mock import patch

from django.utils import timezone

from sandbox.models import TaskAttempt, TraineeProfile
from sandbox.services.environments import (
    ENVIRONMENT_RESTARTING_OUTPUT,
    ENVIRONMENT_STARTING_OUTPUT,
    mark_environment_restart_error,
    mark_environment_restarting,
    mark_environment_start_error,
    mark_environment_starting,
    run_environment_restart,
    run_environment_start,
    try_mark_environment_restarting,
    try_mark_environment_starting,
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
        self.attempt.stuck_reason = TaskAttempt.StuckReason.CHECK
        self.attempt.save(update_fields=["stuck_reason"])

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
        self.assertEqual(
            self.attempt.stuck_reason,
            TaskAttempt.StuckReason.NONE,
        )

    def test_try_mark_environment_starting_does_not_override_restarting_state(self):
        self.attempt.environment_status = TaskAttempt.EnvironmentStatus.RESTARTING
        self.attempt.environment_started_at = timezone.now()
        self.attempt.environment_finished_at = None
        self.attempt.last_check_output = ENVIRONMENT_RESTARTING_OUTPUT
        self.attempt.save(
            update_fields=[
                "environment_status",
                "environment_started_at",
                "environment_finished_at",
                "last_check_output",
            ]
        )

        result = try_mark_environment_starting(self.attempt)

        self.assertFalse(result)

        self.attempt.refresh_from_db()

        self.assertEqual(
            self.attempt.environment_status,
            TaskAttempt.EnvironmentStatus.RESTARTING,
        )
        self.assertEqual(
            self.attempt.last_check_output,
            ENVIRONMENT_RESTARTING_OUTPUT,
        )

    def test_try_mark_environment_restarting_does_not_override_starting_state(self):
        self.attempt.environment_status = TaskAttempt.EnvironmentStatus.STARTING
        self.attempt.environment_started_at = timezone.now()
        self.attempt.environment_finished_at = None
        self.attempt.last_check_output = ENVIRONMENT_STARTING_OUTPUT
        self.attempt.save(
            update_fields=[
                "environment_status",
                "environment_started_at",
                "environment_finished_at",
                "last_check_output",
            ]
        )

        result = try_mark_environment_restarting(self.attempt)

        self.assertFalse(result)

        self.attempt.refresh_from_db()

        self.assertEqual(
            self.attempt.environment_status,
            TaskAttempt.EnvironmentStatus.STARTING,
        )
        self.assertEqual(
            self.attempt.last_check_output,
            ENVIRONMENT_STARTING_OUTPUT,
        )

    def test_try_mark_environment_restarting_resets_finished_at(self):
        self.attempt.status = TaskAttempt.Status.FAILED
        self.attempt.finished_at = timezone.now()
        self.attempt.check_status = TaskAttempt.CheckStatus.FAILED
        self.attempt.check_started_at = timezone.now()
        self.attempt.check_finished_at = timezone.now()
        self.attempt.stuck_reason = TaskAttempt.StuckReason.CHECK
        self.attempt.save(
            update_fields=[
                "status",
                "finished_at",
                "check_status",
                "check_started_at",
                "check_finished_at",
                "stuck_reason",
            ]
        )

        result = try_mark_environment_restarting(self.attempt)

        self.assertTrue(result)

        self.attempt.refresh_from_db()

        self.assertEqual(
            self.attempt.environment_status,
            TaskAttempt.EnvironmentStatus.RESTARTING,
        )
        self.assertIsNone(self.attempt.finished_at)
        self.assertEqual(
            self.attempt.check_status,
            TaskAttempt.CheckStatus.IDLE,
        )
        self.assertIsNone(self.attempt.check_started_at)
        self.assertIsNone(self.attempt.check_finished_at)
        self.assertEqual(
            self.attempt.stuck_reason,
            TaskAttempt.StuckReason.NONE,
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

    def test_mark_environment_restarting_updates_attempt_state(self):
        self.attempt.check_status = TaskAttempt.CheckStatus.FAILED
        self.attempt.check_started_at = timezone.now()
        self.attempt.check_finished_at = timezone.now()
        self.attempt.stuck_reason = TaskAttempt.StuckReason.CHECK
        self.attempt.last_check_output = "ERROR: nginx не запущен"
        self.attempt.finished_at = timezone.now()
        self.attempt.save(
            update_fields=[
                "check_status",
                "check_started_at",
                "check_finished_at",
                "last_check_output",
                "finished_at",
                "stuck_reason",
            ]
        )

        mark_environment_restarting(self.attempt)

        self.attempt.refresh_from_db()

        self.assertEqual(
            self.attempt.environment_status,
            TaskAttempt.EnvironmentStatus.RESTARTING,
        )
        self.assertIsNotNone(self.attempt.environment_started_at)
        self.assertIsNone(self.attempt.environment_finished_at)
        self.assertIsNone(self.attempt.finished_at)
        self.assertEqual(
            self.attempt.stuck_reason,
            TaskAttempt.StuckReason.NONE,
        )
        self.assertEqual(
            self.attempt.last_check_output,
            ENVIRONMENT_RESTARTING_OUTPUT,
        )
        self.assertEqual(
            self.attempt.check_status,
            TaskAttempt.CheckStatus.IDLE,
        )
        self.assertIsNone(self.attempt.check_started_at)
        self.assertIsNone(self.attempt.check_finished_at)

    @patch("sandbox.services.environments.get_free_port")
    @patch("sandbox.services.environments.create_terminal_container")
    @patch("sandbox.services.environments.create_task_container")
    @patch("sandbox.services.environments.remove_task_container")
    @patch("sandbox.services.environments.remove_terminal_container")
    def test_run_environment_restart_removes_old_containers_and_creates_new_environment(
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
        self.attempt.terminal_url = "/terminal/1/24000/"
        self.attempt.shell_command = "docker exec -it old-task-container bash"
        self.attempt.restart_count = 1
        self.attempt.finished_at = timezone.now()
        self.attempt.check_status = TaskAttempt.CheckStatus.FAILED
        self.attempt.check_started_at = timezone.now()
        self.attempt.check_finished_at = timezone.now()
        self.attempt.save()

        create_task_container_mock.return_value = SimpleNamespace(
            id="new-container-id",
            name="new-task-container",
        )
        create_terminal_container_mock.return_value = SimpleNamespace(
            name="new-terminal-container",
        )
        get_free_port_mock.return_value = 25001

        mark_environment_restarting(self.attempt)
        run_environment_restart(self.attempt)

        self.attempt.refresh_from_db()

        remove_terminal_container_mock.assert_called_once_with(
            "old-terminal-container"
        )
        remove_task_container_mock.assert_called_once_with(
            "old-task-container"
        )

        create_task_container_mock.assert_called_once_with(
            queue_slug="l1",
            task_slug="environment-task",
            attempt_id=self.attempt.id,
        )
        create_terminal_container_mock.assert_called_once()
        get_free_port_mock.assert_called_once()

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
        self.assertEqual(
            self.attempt.shell_command,
            "docker exec -it new-task-container bash",
        )
        self.assertIn("перезапущен", self.attempt.last_check_output)

        self.assertEqual(
            self.attempt.check_status,
            TaskAttempt.CheckStatus.IDLE,
        )
        self.assertIsNone(self.attempt.check_started_at)
        self.assertIsNone(self.attempt.check_finished_at)

        self.assertEqual(
            self.attempt.environment_status,
            TaskAttempt.EnvironmentStatus.READY,
        )
        self.assertIsNotNone(self.attempt.environment_started_at)
        self.assertIsNotNone(self.attempt.environment_finished_at)

    def test_mark_environment_restart_error_updates_attempt_state(self):
        mark_environment_restarting(self.attempt)

        mark_environment_restart_error(
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
            "Не удалось перезапустить окружение из-за ошибки Docker API.",
            self.attempt.last_check_output,
        )
        self.assertIn(
            "Docker API unavailable",
            self.attempt.last_check_output,
        )
