from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import docker
from django.test import SimpleTestCase, override_settings

from sandbox.services.docker_service import (
    check_task_container,
    create_task_container,
    create_terminal_container,
)


class DockerServiceSecurityTests(SimpleTestCase):
    @patch("sandbox.services.docker_service.Path.exists", return_value=True)
    @patch("sandbox.services.docker_service.get_docker_client")
    def test_create_task_container_uses_resource_limits(
        self,
        get_docker_client_mock,
        path_exists_mock,
    ):
        client = MagicMock()
        get_docker_client_mock.return_value = client

        client.containers.run.return_value = SimpleNamespace(
            id="container-id",
            name="task-container",
        )

        container = create_task_container(
            queue_slug="l1",
            task_slug="nginx-task",
            attempt_id=1,
        )

        self.assertEqual(container.name, "task-container")

        client.containers.run.assert_called_once()

        run_kwargs = client.containers.run.call_args.kwargs

        self.assertEqual(run_kwargs["mem_limit"], "768m")
        self.assertEqual(run_kwargs["pids_limit"], 256)
        self.assertEqual(
            run_kwargs["security_opt"],
            ["no-new-privileges:true"],
        )
        self.assertEqual(
            run_kwargs["cap_drop"],
            ["AUDIT_WRITE", "MKNOD"],
        )
        self.assertEqual(
            run_kwargs["labels"]["ticket-sandbox.type"],
            "task",
        )
        self.assertEqual(
            run_kwargs["labels"]["ticket-sandbox.attempt"],
            "1",
        )

    @patch("sandbox.services.docker_service.get_docker_socket_path")
    @patch("sandbox.services.docker_service.get_docker_client")
    def test_create_terminal_container_uses_resource_limits(
        self,
        get_docker_client_mock,
        get_docker_socket_path_mock,
    ):
        client = MagicMock()
        get_docker_client_mock.return_value = client
        get_docker_socket_path_mock.return_value = "/var/run/docker.sock"

        client.containers.get.side_effect = docker.errors.NotFound(
            "missing terminal"
        )

        client.containers.run.return_value = SimpleNamespace(
            id="terminal-id",
            name="terminal-container",
        )

        container = create_terminal_container(
            queue_slug="l1",
            task_slug="nginx-task",
            attempt_id=1,
            target_container_name="task-container",
            port=25000,
        )

        self.assertEqual(container.name, "terminal-container")

        client.containers.run.assert_called_once()

        run_kwargs = client.containers.run.call_args.kwargs

        self.assertEqual(run_kwargs["mem_limit"], "256m")
        self.assertEqual(run_kwargs["pids_limit"], 128)
        self.assertEqual(
            run_kwargs["security_opt"],
            ["no-new-privileges:true"],
        )
        self.assertEqual(
            run_kwargs["cap_drop"],
            ["ALL"],
        )
        self.assertEqual(
            run_kwargs["labels"]["ticket-sandbox.type"],
            "terminal",
        )
        self.assertEqual(
            run_kwargs["labels"]["ticket-sandbox.attempt"],
            "1",
        )
        self.assertEqual(
            run_kwargs["ports"],
            {
                "7681/tcp": ("127.0.0.1", 25000),
            },
        )
        self.assertEqual(
            run_kwargs["command"],
            "ttyd -W sh -c 'docker exec -it task-container bash'",
        )

    @patch("sandbox.services.docker_service.get_docker_socket_path")
    @patch("sandbox.services.docker_service.get_docker_client")
    def test_create_terminal_container_uses_base_path_when_provided(
        self,
        get_docker_client_mock,
        get_docker_socket_path_mock,
    ):
        client = MagicMock()
        get_docker_client_mock.return_value = client
        get_docker_socket_path_mock.return_value = "/var/run/docker.sock"

        client.containers.get.side_effect = docker.errors.NotFound(
            "missing terminal"
        )

        client.containers.run.return_value = SimpleNamespace(
            id="terminal-id",
            name="terminal-container",
        )

        create_terminal_container(
            queue_slug="l1",
            task_slug="nginx-task",
            attempt_id=123,
            target_container_name="task-container",
            port=25000,
            base_path="/terminal/123/25000/",
        )

        client.containers.run.assert_called_once()

        run_kwargs = client.containers.run.call_args.kwargs

        self.assertEqual(
            run_kwargs["command"],
            (
                "ttyd -W "
                "--base-path /terminal/123/25000/ "
                "sh -c 'docker exec -it task-container bash'"
            ),
        )


    @override_settings(CHECK_TASK_TIMEOUT_SECONDS=60)
    @patch("sandbox.services.docker_service.get_docker_client")
    def test_check_task_container_runs_check_sh_with_timeout(
        self,
        get_docker_client_mock,
    ):
        client = MagicMock()
        container = MagicMock()

        get_docker_client_mock.return_value = client
        client.containers.get.return_value = container
        container.exec_run.return_value = (0, b"OK\n")

        exit_code, output = check_task_container("task-container")

        self.assertEqual(exit_code, 0)
        self.assertEqual(output, "OK\n")

        client.containers.get.assert_called_once_with("task-container")
        container.exec_run.assert_called_once_with(
            cmd=[
                "timeout",
                "--kill-after=5s",
                "60s",
                "bash",
                "/task/check.sh",
            ],
            stdout=True,
            stderr=True,
        )

    @override_settings(CHECK_TASK_TIMEOUT_SECONDS=30)
    @patch("sandbox.services.docker_service.get_docker_client")
    def test_check_task_container_returns_readable_message_on_timeout(
        self,
        get_docker_client_mock,
    ):
        client = MagicMock()
        container = MagicMock()

        get_docker_client_mock.return_value = client
        client.containers.get.return_value = container
        container.exec_run.return_value = (
            124,
            b"Partial check output\n",
        )

        exit_code, output = check_task_container("task-container")

        self.assertEqual(exit_code, 124)
        self.assertIn("Partial check output", output)
        self.assertIn(
            "Проверка остановлена: check.sh выполнялся дольше 30 секунд.",
            output,
        )
