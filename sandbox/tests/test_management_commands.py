import json
import os
from contextlib import contextmanager
from datetime import timedelta
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.utils import timezone

from sandbox.models import Task, TaskAttempt, TraineeProfile

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


class SyncTrainingTasksCommandTests(SandboxTestCase):
    def setUp(self):
        self.queue = self.create_queue(
            slug="l1",
            name="ОТП Cloud L1",
            order=1,
            required_level=TraineeProfile.Level.L1,
        )

    def test_sync_training_tasks_creates_task_from_task_json(self):
        stdout = StringIO()

        with TemporaryDirectory() as temp_dir:
            self._write_training_task(
                base_dir=Path(temp_dir),
                queue_slug="l1",
                task_slug="nginx-not-starting",
                task_json={
                    "title": "Nginx не запускается",
                    "ticket_title": "Сайт перестал открываться",
                    "client_name": "Алексей Морозов",
                    "client_email": "a.morozov@example.com",
                    "description": "После правки конфига nginx сайт перестал открываться.",
                    "priority": Task.Priority.HIGH,
                    "order": 7,
                    "requires_manual_review": False,
                    "is_active": True,
                },
            )

            with self.settings(BASE_DIR=Path(temp_dir)):
                call_command(
                    "sync_training_tasks",
                    stdout=stdout,
                )

        task = Task.objects.get(
            queue=self.queue,
            slug="nginx-not-starting",
        )

        self.assertEqual(task.title, "Nginx не запускается")
        self.assertEqual(task.ticket_title, "Сайт перестал открываться")
        self.assertEqual(task.client_name, "Алексей Морозов")
        self.assertEqual(task.client_email, "a.morozov@example.com")
        self.assertEqual(
            task.description,
            "После правки конфига nginx сайт перестал открываться.",
        )
        self.assertEqual(task.priority, Task.Priority.HIGH)
        self.assertEqual(task.order, 7)
        self.assertFalse(task.requires_manual_review)
        self.assertTrue(task.is_active)

        self.assertIn(
            "CREATED l1/nginx-not-starting",
            stdout.getvalue(),
        )

    def test_sync_training_tasks_dry_run_does_not_create_task(self):
        stdout = StringIO()

        with TemporaryDirectory() as temp_dir:
            self._write_training_task(
                base_dir=Path(temp_dir),
                queue_slug="l1",
                task_slug="dry-run-task",
                task_json={
                    "title": "Dry run task",
                },
            )

            with self.settings(BASE_DIR=Path(temp_dir)):
                call_command(
                    "sync_training_tasks",
                    "--dry-run",
                    stdout=stdout,
                )

        self.assertFalse(
            Task.objects.filter(
                queue=self.queue,
                slug="dry-run-task",
            ).exists()
        )

        self.assertIn(
            "WOULD CREATE l1/dry-run-task",
            stdout.getvalue(),
        )

        self.assertIn(
            "Dry run done. would_create=1, would_update=0, skipped=0",
            stdout.getvalue(),
        )

    def test_sync_training_tasks_dry_run_reports_existing_task_as_would_update(self):
        self.create_task(
            queue=self.queue,
            slug="existing-dry-run-task",
            order=1,
            title="Старое название",
        )

        stdout = StringIO()

        with TemporaryDirectory() as temp_dir:
            self._write_training_task(
                base_dir=Path(temp_dir),
                queue_slug="l1",
                task_slug="existing-dry-run-task",
                task_json={
                    "title": "Новое название из dry-run",
                },
            )

            with self.settings(BASE_DIR=Path(temp_dir)):
                call_command(
                    "sync_training_tasks",
                    "--dry-run",
                    stdout=stdout,
                )

        task = Task.objects.get(
            queue=self.queue,
            slug="existing-dry-run-task",
        )

        self.assertEqual(task.title, "Старое название")

        self.assertIn(
            "WOULD UPDATE l1/existing-dry-run-task",
            stdout.getvalue(),
        )
        self.assertIn(
            "Dry run done. would_create=0, would_update=1, skipped=0",
            stdout.getvalue(),
        )

    def test_sync_training_tasks_updates_existing_task_from_task_json(self):
        task = self.create_task(
            queue=self.queue,
            slug="existing-task",
            order=1,
            title="Старое название",
        )

        stdout = StringIO()

        with TemporaryDirectory() as temp_dir:
            self._write_training_task(
                base_dir=Path(temp_dir),
                queue_slug="l1",
                task_slug="existing-task",
                task_json={
                    "title": "Новое название из task.json",
                    "ticket_title": "Новая тема тикета",
                    "client_name": "Мария Соколова",
                    "client_email": "m.sokolova@example.com",
                    "description": "Новое описание из task.json.",
                    "priority": Task.Priority.CRITICAL,
                    "order": 3,
                    "requires_manual_review": True,
                    "is_active": False,
                },
            )

            with self.settings(BASE_DIR=Path(temp_dir)):
                call_command(
                    "sync_training_tasks",
                    stdout=stdout,
                )

        task.refresh_from_db()

        self.assertEqual(task.title, "Новое название из task.json")
        self.assertEqual(task.ticket_title, "Новая тема тикета")
        self.assertEqual(task.client_name, "Мария Соколова")
        self.assertEqual(task.client_email, "m.sokolova@example.com")
        self.assertEqual(task.description, "Новое описание из task.json.")
        self.assertEqual(task.priority, Task.Priority.CRITICAL)
        self.assertEqual(task.order, 3)
        self.assertTrue(task.requires_manual_review)
        self.assertFalse(task.is_active)

        self.assertIn(
            "UPDATED l1/existing-task",
            stdout.getvalue(),
        )

    def test_sync_training_tasks_skips_task_without_dockerfile(self):
        stdout = StringIO()

        with TemporaryDirectory() as temp_dir:
            self._write_training_task(
                base_dir=Path(temp_dir),
                queue_slug="l1",
                task_slug="without-dockerfile",
                create_dockerfile=False,
            )

            with self.settings(BASE_DIR=Path(temp_dir)):
                call_command(
                    "sync_training_tasks",
                    stdout=stdout,
                )

        self.assertFalse(
            Task.objects.filter(
                queue=self.queue,
                slug="without-dockerfile",
            ).exists()
        )

        self.assertIn(
            "SKIP l1/without-dockerfile: Dockerfile not found",
            stdout.getvalue(),
        )

    def test_sync_training_tasks_skips_task_without_check_script(self):
        stdout = StringIO()

        with TemporaryDirectory() as temp_dir:
            self._write_training_task(
                base_dir=Path(temp_dir),
                queue_slug="l1",
                task_slug="without-check",
                create_check_script=False,
            )

            with self.settings(BASE_DIR=Path(temp_dir)):
                call_command(
                    "sync_training_tasks",
                    stdout=stdout,
                )

        self.assertFalse(
            Task.objects.filter(
                queue=self.queue,
                slug="without-check",
            ).exists()
        )

        self.assertIn(
            "SKIP l1/without-check: check.sh not found",
            stdout.getvalue(),
        )

    def test_sync_training_tasks_skips_task_when_queue_does_not_exist(self):
        stdout = StringIO()

        with TemporaryDirectory() as temp_dir:
            self._write_training_task(
                base_dir=Path(temp_dir),
                queue_slug="unknown",
                task_slug="unknown-queue-task",
            )

            with self.settings(BASE_DIR=Path(temp_dir)):
                call_command(
                    "sync_training_tasks",
                    stdout=stdout,
                )

        self.assertFalse(
            Task.objects.filter(
                slug="unknown-queue-task",
            ).exists()
        )

        self.assertIn(
            "SKIP unknown/unknown-queue-task: queue not found",
            stdout.getvalue(),
        )

    def test_sync_training_tasks_strict_raises_when_task_was_skipped(self):
        stdout = StringIO()

        with TemporaryDirectory() as temp_dir:
            self._write_training_task(
                base_dir=Path(temp_dir),
                queue_slug="l1",
                task_slug="strict-without-dockerfile",
                create_dockerfile=False,
            )

            with self.settings(BASE_DIR=Path(temp_dir)):
                with self.assertRaisesMessage(
                    CommandError,
                    "skipped 1 task(s) in strict mode",
                ):
                    call_command(
                        "sync_training_tasks",
                        "--strict",
                        stdout=stdout,
                    )

        self.assertFalse(
            Task.objects.filter(
                queue=self.queue,
                slug="strict-without-dockerfile",
            ).exists()
        )

        self.assertIn(
            "SKIP l1/strict-without-dockerfile: Dockerfile not found",
            stdout.getvalue(),
        )
        self.assertIn(
            "Done. created=0, updated=0, skipped=1",
            stdout.getvalue(),
        )

    def test_sync_training_tasks_raises_for_invalid_task_json_root(self):
        with TemporaryDirectory() as temp_dir:
            task_dir = (
                Path(temp_dir)
                / "training_tasks"
                / "l1"
                / "invalid-json-root"
            )
            files_dir = task_dir / "files"
            files_dir.mkdir(parents=True)

            (task_dir / "Dockerfile").write_text(
                "FROM ubuntu:24.04\n",
                encoding="utf-8",
            )

            check_script = files_dir / "check.sh"
            check_script.write_text(
                "#!/usr/bin/env bash\nexit 0\n",
                encoding="utf-8",
            )
            check_script.chmod(0o755)

            (task_dir / "task.json").write_text(
                '["not", "an", "object"]',
                encoding="utf-8",
            )

            with self.settings(BASE_DIR=Path(temp_dir)):
                with self.assertRaisesMessage(
                    CommandError,
                    "root value must be an object",
                ):
                    call_command("sync_training_tasks")

    def test_sync_training_tasks_raises_for_invalid_priority(self):
        with TemporaryDirectory() as temp_dir:
            self._write_training_task(
                base_dir=Path(temp_dir),
                queue_slug="l1",
                task_slug="invalid-priority",
                task_json={
                    "title": "Invalid priority task",
                    "priority": "super-important",
                },
            )

            with self.settings(BASE_DIR=Path(temp_dir)):
                with self.assertRaisesMessage(
                    CommandError,
                    '"priority" must be one of',
                ):
                    call_command("sync_training_tasks")

    def test_sync_training_tasks_raises_for_invalid_boolean_field(self):
        with TemporaryDirectory() as temp_dir:
            self._write_training_task(
                base_dir=Path(temp_dir),
                queue_slug="l1",
                task_slug="invalid-bool",
                task_json={
                    "title": "Invalid bool task",
                    "requires_manual_review": "yes",
                },
            )

            with self.settings(BASE_DIR=Path(temp_dir)):
                with self.assertRaisesMessage(
                    CommandError,
                    '"requires_manual_review" must be true or false',
                ):
                    call_command("sync_training_tasks")

    def _write_training_task(
        self,
        base_dir,
        queue_slug,
        task_slug,
        task_json=None,
        create_dockerfile=True,
        create_check_script=True,
    ):
        task_dir = base_dir / "training_tasks" / queue_slug / task_slug
        files_dir = task_dir / "files"

        files_dir.mkdir(parents=True)

        if create_dockerfile:
            (task_dir / "Dockerfile").write_text(
                "FROM ubuntu:24.04\n",
                encoding="utf-8",
            )

        if create_check_script:
            check_script = files_dir / "check.sh"
            check_script.write_text(
                "#!/usr/bin/env bash\nexit 0\n",
                encoding="utf-8",
            )
            check_script.chmod(0o755)

        if task_json is not None:
            (task_dir / "task.json").write_text(
                json.dumps(
                    task_json,
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
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
            environment_status=TaskAttempt.EnvironmentStatus.READY,
            environment_started_at=started_at,
            environment_finished_at=started_at,
            check_status=TaskAttempt.CheckStatus.RUNNING,
            check_started_at=started_at,
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
        self.assertEqual(
            attempt.environment_status,
            TaskAttempt.EnvironmentStatus.IDLE,
        )
        self.assertIsNone(attempt.environment_started_at)
        self.assertIsNone(attempt.environment_finished_at)
        self.assertEqual(attempt.check_status, TaskAttempt.CheckStatus.IDLE)
        self.assertIsNone(attempt.check_started_at)
        self.assertIsNone(attempt.check_finished_at)

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

    @patch("sandbox.management.commands.cleanup_task_containers.remove_terminal_container")
    @patch("sandbox.management.commands.cleanup_task_containers.remove_task_container")
    def test_cleanup_task_containers_dry_run_does_not_remove_or_update_attempts(
        self,
        remove_task_container_mock,
        remove_terminal_container_mock,
    ):
        old_time = timezone.now() - timedelta(hours=73)

        attempt = TaskAttempt.objects.create(
            user=self.user,
            task=self.task,
            status=TaskAttempt.Status.IN_PROGRESS,
            started_at=old_time,
            container_id="old-container-id",
            container_name="old-task-container",
            shell_command="docker exec -it old-task-container bash",
            terminal_container_name="old-terminal-container",
            terminal_url="/terminal/1/24000/",
            terminal_port=24000,
            environment_status=TaskAttempt.EnvironmentStatus.READY,
            environment_started_at=old_time,
            environment_finished_at=old_time,
            check_status=TaskAttempt.CheckStatus.RUNNING,
            check_started_at=old_time,
        )

        output = StringIO()

        call_command(
            "cleanup_task_containers",
            "--dry-run",
            stdout=output,
        )

        attempt.refresh_from_db()

        remove_task_container_mock.assert_not_called()
        remove_terminal_container_mock.assert_not_called()

        self.assertEqual(attempt.status, TaskAttempt.Status.IN_PROGRESS)
        self.assertEqual(attempt.container_name, "old-task-container")
        self.assertEqual(attempt.terminal_container_name, "old-terminal-container")
        self.assertEqual(
            attempt.environment_status,
            TaskAttempt.EnvironmentStatus.READY,
        )
        self.assertIsNotNone(attempt.environment_started_at)
        self.assertIsNotNone(attempt.environment_finished_at)
        self.assertEqual(attempt.check_status, TaskAttempt.CheckStatus.RUNNING)
        self.assertIsNotNone(attempt.check_started_at)

        self.assertIn("WOULD CLEANUP attempt", output.getvalue())
        self.assertIn("would_cleanup=1", output.getvalue())


class DetectStuckAttemptsCommandTests(SandboxTestCase):
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
        self.user = self.create_user(username="trainee")
        self.attempt = TaskAttempt.objects.create(
            user=self.user,
            task=self.task,
            attempt_number=1,
            is_current=True,
        )

    @patch("sandbox.management.commands.detect_stuck_attempts.notify_stuck_attempt_detected")
    def test_detect_stuck_attempts_marks_stuck_environment_as_error(
        self,
        notify_stuck_attempt_detected_mock,
    ):
        self.attempt.environment_status = TaskAttempt.EnvironmentStatus.STARTING
        self.attempt.environment_started_at = timezone.now() - timedelta(minutes=11)
        self.attempt.save(
            update_fields=[
                "environment_status",
                "environment_started_at",
            ]
        )

        stdout = StringIO()

        call_command(
            "detect_stuck_attempts",
            stdout=stdout,
        )

        self.attempt.refresh_from_db()

        self.assertEqual(
            self.attempt.environment_status,
            TaskAttempt.EnvironmentStatus.ERROR,
        )
        self.assertEqual(
            self.attempt.status,
            TaskAttempt.Status.FAILED,
        )
        self.assertIsNotNone(self.attempt.environment_finished_at)
        self.assertIn(
            "Запуск окружения был прерван",
            self.attempt.last_check_output,
        )
        self.assertIn(
            "marked_environment=1",
            stdout.getvalue(),
        )

        notify_stuck_attempt_detected_mock.assert_called_once_with(
            attempt=self.attempt,
            reason="завис запуск или перезапуск окружения",
        )

    @patch("sandbox.management.commands.detect_stuck_attempts.notify_stuck_attempt_detected")
    def test_detect_stuck_attempts_marks_stuck_check_as_error(
        self,
        notify_stuck_attempt_detected_mock,
    ):
        self.attempt.check_status = TaskAttempt.CheckStatus.RUNNING
        self.attempt.check_started_at = timezone.now() - timedelta(minutes=11)
        self.attempt.save(
            update_fields=[
                "check_status",
                "check_started_at",
            ]
        )

        stdout = StringIO()

        call_command(
            "detect_stuck_attempts",
            stdout=stdout,
        )

        self.attempt.refresh_from_db()

        self.assertEqual(
            self.attempt.check_status,
            TaskAttempt.CheckStatus.ERROR,
        )
        self.assertEqual(
            self.attempt.status,
            TaskAttempt.Status.FAILED,
        )
        self.assertIsNotNone(self.attempt.check_finished_at)
        self.assertIn(
            "Автопроверка была прервана",
            self.attempt.last_check_output,
        )
        self.assertIn(
            "marked_check=1",
            stdout.getvalue(),
        )

        notify_stuck_attempt_detected_mock.assert_called_once_with(
            attempt=self.attempt,
            reason="зависла автопроверка",
        )

    @patch("sandbox.management.commands.detect_stuck_attempts.notify_stuck_attempt_detected")
    def test_detect_stuck_attempts_dry_run_does_not_change_attempt(
        self,
        notify_stuck_attempt_detected_mock,
    ):
        self.attempt.environment_status = TaskAttempt.EnvironmentStatus.STARTING
        self.attempt.environment_started_at = timezone.now() - timedelta(minutes=11)
        self.attempt.save(
            update_fields=[
                "environment_status",
                "environment_started_at",
            ]
        )

        stdout = StringIO()

        call_command(
            "detect_stuck_attempts",
            "--dry-run",
            stdout=stdout,
        )

        self.attempt.refresh_from_db()

        self.assertEqual(
            self.attempt.environment_status,
            TaskAttempt.EnvironmentStatus.STARTING,
        )
        self.assertIsNone(self.attempt.environment_finished_at)
        self.assertIn(
            "would_mark_environment=1",
            stdout.getvalue(),
        )

        notify_stuck_attempt_detected_mock.assert_not_called()

    @patch("sandbox.management.commands.detect_stuck_attempts.notify_stuck_attempt_detected")
    def test_detect_stuck_attempts_ignores_recent_background_state(
        self,
        notify_stuck_attempt_detected_mock,
    ):
        self.attempt.environment_status = TaskAttempt.EnvironmentStatus.STARTING
        self.attempt.environment_started_at = timezone.now() - timedelta(minutes=3)
        self.attempt.check_status = TaskAttempt.CheckStatus.RUNNING
        self.attempt.check_started_at = timezone.now() - timedelta(minutes=3)
        self.attempt.save(
            update_fields=[
                "environment_status",
                "environment_started_at",
                "check_status",
                "check_started_at",
            ]
        )

        stdout = StringIO()

        call_command(
            "detect_stuck_attempts",
            stdout=stdout,
        )

        self.attempt.refresh_from_db()

        self.assertEqual(
            self.attempt.environment_status,
            TaskAttempt.EnvironmentStatus.STARTING,
        )
        self.assertEqual(
            self.attempt.check_status,
            TaskAttempt.CheckStatus.RUNNING,
        )
        self.assertIsNone(self.attempt.environment_finished_at)
        self.assertIsNone(self.attempt.check_finished_at)
        self.assertIn(
            "marked_environment=0",
            stdout.getvalue(),
        )
        self.assertIn(
            "marked_check=0",
            stdout.getvalue(),
        )

        notify_stuck_attempt_detected_mock.assert_not_called()

    @patch("sandbox.management.commands.detect_stuck_attempts.notify_stuck_attempt_detected")
    def test_detect_stuck_attempts_respects_custom_minutes_threshold(
        self,
        notify_stuck_attempt_detected_mock,
    ):
        self.attempt.environment_status = TaskAttempt.EnvironmentStatus.STARTING
        self.attempt.environment_started_at = timezone.now() - timedelta(minutes=6)
        self.attempt.save(
            update_fields=[
                "environment_status",
                "environment_started_at",
            ]
        )

        stdout = StringIO()

        call_command(
            "detect_stuck_attempts",
            "--minutes",
            "5",
            stdout=stdout,
        )

        self.attempt.refresh_from_db()

        self.assertEqual(
            self.attempt.environment_status,
            TaskAttempt.EnvironmentStatus.ERROR,
        )
        self.assertIsNotNone(self.attempt.environment_finished_at)
        self.assertIn(
            "marked_environment=1",
            stdout.getvalue(),
        )
        notify_stuck_attempt_detected_mock.assert_called_once_with(
            attempt=self.attempt,
            reason="завис запуск или перезапуск окружения",
        )

    @patch("sandbox.management.commands.detect_stuck_attempts.notify_stuck_attempt_detected")
    def test_detect_stuck_attempts_does_not_touch_technically_passed_attempt(
        self,
        notify_stuck_attempt_detected_mock,
    ):
        self.attempt.status = TaskAttempt.Status.ON_REVIEW
        self.attempt.technical_passed_at = timezone.now() - timedelta(minutes=20)
        self.attempt.environment_status = TaskAttempt.EnvironmentStatus.STARTING
        self.attempt.environment_started_at = timezone.now() - timedelta(minutes=20)
        self.attempt.check_status = TaskAttempt.CheckStatus.RUNNING
        self.attempt.check_started_at = timezone.now() - timedelta(minutes=20)
        self.attempt.save(
            update_fields=[
                "status",
                "technical_passed_at",
                "environment_status",
                "environment_started_at",
                "check_status",
                "check_started_at",
            ]
        )

        stdout = StringIO()

        call_command(
            "detect_stuck_attempts",
            stdout=stdout,
        )

        self.attempt.refresh_from_db()

        self.assertEqual(self.attempt.status, TaskAttempt.Status.ON_REVIEW)
        self.assertEqual(
            self.attempt.environment_status,
            TaskAttempt.EnvironmentStatus.STARTING,
        )
        self.assertEqual(
            self.attempt.check_status,
            TaskAttempt.CheckStatus.RUNNING,
        )
        self.assertIsNone(self.attempt.environment_finished_at)
        self.assertIsNone(self.attempt.check_finished_at)

        self.assertIn(
            "marked_environment=0",
            stdout.getvalue(),
        )
        self.assertIn(
            "marked_check=0",
            stdout.getvalue(),
        )

        notify_stuck_attempt_detected_mock.assert_not_called()

    @patch("sandbox.management.commands.detect_stuck_attempts.notify_stuck_attempt_detected")
    def test_detect_stuck_attempts_prioritizes_stuck_environment_over_stuck_check(
        self,
        notify_stuck_attempt_detected_mock,
    ):
        old_time = timezone.now() - timedelta(minutes=11)

        self.attempt.environment_status = TaskAttempt.EnvironmentStatus.STARTING
        self.attempt.environment_started_at = old_time
        self.attempt.check_status = TaskAttempt.CheckStatus.RUNNING
        self.attempt.check_started_at = old_time
        self.attempt.save(
            update_fields=[
                "environment_status",
                "environment_started_at",
                "check_status",
                "check_started_at",
            ]
        )

        stdout = StringIO()

        call_command(
            "detect_stuck_attempts",
            stdout=stdout,
        )

        self.attempt.refresh_from_db()

        self.assertEqual(
            self.attempt.environment_status,
            TaskAttempt.EnvironmentStatus.ERROR,
        )
        self.assertEqual(
            self.attempt.check_status,
            TaskAttempt.CheckStatus.ERROR,
        )
        self.assertIsNotNone(self.attempt.environment_finished_at)
        self.assertIsNotNone(self.attempt.check_finished_at)
        self.assertIn(
            "Запуск окружения был прерван",
            self.attempt.last_check_output,
        )
        self.assertIn(
            "marked_environment=1",
            stdout.getvalue(),
        )
        self.assertIn(
            "marked_check=0",
            stdout.getvalue(),
        )

        notify_stuck_attempt_detected_mock.assert_called_once_with(
            attempt=self.attempt,
            reason="завис запуск или перезапуск окружения",
        )
