import os
from contextlib import contextmanager
from datetime import timedelta
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, patch

from django.core.management import call_command
from django.utils import timezone

from sandbox.models import TaskAttempt, TraineeProfile

from .base import SandboxTestCase


@contextmanager
def change_working_directory(path):
    old_path = os.getcwd()
    os.chdir(path)

    try:
        yield
    finally:
        os.chdir(old_path)


class BuildTaskImagesCommandTests(SandboxTestCase):
    @patch("sandbox.management.commands.build_task_images.get_docker_client")
    def test_build_task_images_builds_nested_training_task_images(
        self,
        get_docker_client_mock,
    ):
        docker_client = MagicMock()
        get_docker_client_mock.return_value = docker_client

        stdout = StringIO()
        stderr = StringIO()

        with TemporaryDirectory() as temp_dir:
            with change_working_directory(temp_dir):
                task_dir = Path("training_tasks/l1/nginx-not-starting")
                task_dir.mkdir(parents=True)

                dockerfile = task_dir / "Dockerfile"
                dockerfile.write_text(
                    "FROM ubuntu:24.04\n",
                    encoding="utf-8",
                )

                call_command(
                    "build_task_images",
                    stdout=stdout,
                    stderr=stderr,
                )

        docker_client.images.build.assert_called_once_with(
            path="training_tasks/l1/nginx-not-starting",
            tag="ticket-sandbox-l1-nginx-not-starting",
        )

        self.assertIn(
            "Built ticket-sandbox-l1-nginx-not-starting",
            stdout.getvalue(),
        )

        self.assertEqual(stderr.getvalue(), "")

    @patch("sandbox.management.commands.build_task_images.get_docker_client")
    def test_build_task_images_skips_task_without_dockerfile(
        self,
        get_docker_client_mock,
    ):
        docker_client = MagicMock()
        get_docker_client_mock.return_value = docker_client

        stdout = StringIO()
        stderr = StringIO()

        with TemporaryDirectory() as temp_dir:
            with change_working_directory(temp_dir):
                task_dir = Path("training_tasks/l1/task-without-dockerfile")
                task_dir.mkdir(parents=True)

                call_command(
                    "build_task_images",
                    stdout=stdout,
                    stderr=stderr,
                )

        docker_client.images.build.assert_not_called()

        self.assertIn(
            "Skip l1/task-without-dockerfile: Dockerfile not found",
            stdout.getvalue(),
        )

        self.assertEqual(stderr.getvalue(), "")

    @patch("sandbox.management.commands.build_task_images.get_docker_client")
    def test_build_task_images_handles_missing_training_tasks_directory(
        self,
        get_docker_client_mock,
    ):
        docker_client = MagicMock()
        get_docker_client_mock.return_value = docker_client

        stdout = StringIO()
        stderr = StringIO()

        with TemporaryDirectory() as temp_dir:
            with change_working_directory(temp_dir):
                call_command(
                    "build_task_images",
                    stdout=stdout,
                    stderr=stderr,
                )

        docker_client.images.build.assert_not_called()

        self.assertIn(
            "training_tasks directory not found",
            stderr.getvalue(),
        )


class CleanupTaskContainersCommandTests(SandboxTestCase):
    def setUp(self):
        self.queue = self.create_queue(
            slug="l1",
            name="ОТП Cloud L1",
            order=1,
            required_level=TraineeProfile.Level.L1,
        )

        self.task = self.create_task(
            queue=self.queue,
            slug="cleanup-task",
            order=1,
        )

        self.user = self.create_user(
            username="cleanup-user",
            level=TraineeProfile.Level.L1,
        )

    @patch("sandbox.management.commands.cleanup_task_containers.remove_terminal_container")
    @patch("sandbox.management.commands.cleanup_task_containers.remove_task_container")
    def test_cleanup_removes_expired_unfinished_attempt_containers(
        self,
        remove_task_container_mock,
        remove_terminal_container_mock,
    ):
        started_at = timezone.now() - timedelta(hours=73)

        attempt = TaskAttempt.objects.create(
            user=self.user,
            task=self.task,
            status=TaskAttempt.Status.IN_PROGRESS,
            started_at=started_at,
            container_id="old-container-id",
            container_name="old-task-container",
            shell_command="docker exec -it old-task-container bash",
            terminal_container_name="old-terminal-container",
            terminal_url="http://localhost:24000",
            terminal_port=24000,
        )

        remove_task_container_mock.return_value = (
            True,
            "Контейнер удален.",
        )

        remove_terminal_container_mock.return_value = (
            True,
            "Контейнер терминала удален.",
        )

        stdout = StringIO()

        call_command(
            "cleanup_task_containers",
            stdout=stdout,
        )

        remove_task_container_mock.assert_called_once_with(
            "old-task-container"
        )

        remove_terminal_container_mock.assert_called_once_with(
            "old-terminal-container"
        )

        attempt.refresh_from_db()

        self.assertEqual(attempt.status, TaskAttempt.Status.NEW)
        self.assertEqual(attempt.container_id, "")
        self.assertEqual(attempt.container_name, "")
        self.assertEqual(attempt.shell_command, "")
        self.assertEqual(attempt.terminal_container_name, "")
        self.assertEqual(attempt.terminal_url, "")
        self.assertIsNone(attempt.terminal_port)

        self.assertIn(
            f"Cleanup attempt #{attempt.id}",
            stdout.getvalue(),
        )

        self.assertIn(
            "Cleanup completed",
            stdout.getvalue(),
        )

    @patch("sandbox.management.commands.cleanup_task_containers.remove_terminal_container")
    @patch("sandbox.management.commands.cleanup_task_containers.remove_task_container")
    def test_cleanup_does_not_touch_recent_attempt(
        self,
        remove_task_container_mock,
        remove_terminal_container_mock,
    ):
        started_at = timezone.now() - timedelta(hours=1)

        attempt = TaskAttempt.objects.create(
            user=self.user,
            task=self.task,
            status=TaskAttempt.Status.IN_PROGRESS,
            started_at=started_at,
            container_id="recent-container-id",
            container_name="recent-task-container",
            shell_command="docker exec -it recent-task-container bash",
            terminal_container_name="recent-terminal-container",
            terminal_url="http://localhost:24001",
            terminal_port=24001,
        )

        call_command("cleanup_task_containers")

        remove_task_container_mock.assert_not_called()
        remove_terminal_container_mock.assert_not_called()

        attempt.refresh_from_db()

        self.assertEqual(attempt.status, TaskAttempt.Status.IN_PROGRESS)
        self.assertEqual(attempt.container_id, "recent-container-id")
        self.assertEqual(attempt.container_name, "recent-task-container")
        self.assertEqual(
            attempt.terminal_container_name,
            "recent-terminal-container",
        )
        self.assertEqual(attempt.terminal_port, 24001)

    @patch("sandbox.management.commands.cleanup_task_containers.remove_terminal_container")
    @patch("sandbox.management.commands.cleanup_task_containers.remove_task_container")
    def test_cleanup_does_not_touch_finished_attempt(
        self,
        remove_task_container_mock,
        remove_terminal_container_mock,
    ):
        started_at = timezone.now() - timedelta(hours=73)
        finished_at = timezone.now() - timedelta(hours=72)

        attempt = TaskAttempt.objects.create(
            user=self.user,
            task=self.task,
            status=TaskAttempt.Status.PASSED,
            started_at=started_at,
            finished_at=finished_at,
            container_id="finished-container-id",
            container_name="finished-task-container",
            shell_command="docker exec -it finished-task-container bash",
            terminal_container_name="finished-terminal-container",
            terminal_url="http://localhost:24002",
            terminal_port=24002,
        )

        call_command("cleanup_task_containers")

        remove_task_container_mock.assert_not_called()
        remove_terminal_container_mock.assert_not_called()

        attempt.refresh_from_db()

        self.assertEqual(attempt.status, TaskAttempt.Status.PASSED)
        self.assertEqual(attempt.container_id, "finished-container-id")
        self.assertEqual(attempt.container_name, "finished-task-container")
        self.assertEqual(
            attempt.terminal_container_name,
            "finished-terminal-container",
        )
        self.assertEqual(attempt.terminal_port, 24002)

    @patch("sandbox.management.commands.cleanup_task_containers.remove_terminal_container")
    @patch("sandbox.management.commands.cleanup_task_containers.remove_task_container")
    def test_cleanup_does_not_touch_technically_passed_attempts(
        self,
        remove_task_container_mock,
        remove_terminal_container_mock,
    ):
        attempt = TaskAttempt.objects.create(
            user=self.user,
            task=self.task,
            status=TaskAttempt.Status.ON_REVIEW,
            is_current=True,
            started_at=timezone.now() - timedelta(hours=100),
            technical_passed_at=timezone.now() - timedelta(hours=90),
            container_id="passed-container-id",
            container_name="passed-task-container",
            shell_command="docker exec -it passed-task-container bash",
            terminal_container_name="passed-terminal-container",
            terminal_url="http://localhost:24003",
            terminal_port=24003,
        )

        call_command("cleanup_task_containers")

        remove_task_container_mock.assert_not_called()
        remove_terminal_container_mock.assert_not_called()

        attempt.refresh_from_db()

        self.assertEqual(attempt.status, TaskAttempt.Status.ON_REVIEW)
        self.assertEqual(attempt.container_id, "passed-container-id")
        self.assertEqual(attempt.container_name, "passed-task-container")
        self.assertEqual(attempt.shell_command, "docker exec -it passed-task-container bash")
        self.assertEqual(attempt.terminal_container_name, "passed-terminal-container")
        self.assertEqual(attempt.terminal_url, "http://localhost:24003")
        self.assertEqual(attempt.terminal_port, 24003)
