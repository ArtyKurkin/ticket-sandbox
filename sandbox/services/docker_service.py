from pathlib import Path

import docker
import random
import socket

from django.conf import settings


def get_free_port(start: int = 20000, end: int = 30000):
    for _ in range(100):
        port = random.randint(start, end)

        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            result = sock.connect_ex(("127.0.0.1", port))

            if result != 0:
                return port

    raise RuntimeError("Не удалось найти свободный порт для терминала")


def get_docker_client():
    mac_socket = Path.home() / ".docker" / "run" / "docker.sock"

    if mac_socket.exists():
        return docker.DockerClient(base_url=f"unix://{mac_socket}")

    return docker.from_env()


def get_docker_socket_path():
    mac_socket = Path.home() / ".docker" / "run" / "docker.sock"

    if mac_socket.exists():
        return str(mac_socket)

    return "/var/run/docker.sock"


def create_task_container(queue_slug: str, task_slug: str, attempt_id: int):
    client = get_docker_client()

    container_name = f"ticket-sandbox-{queue_slug}-{task_slug}-{attempt_id}"
    image_name = f"ticket-sandbox-{queue_slug}-{task_slug}"

    task_path = Path(f"training_tasks/{queue_slug}/{task_slug}")

    if not task_path.exists():
        raise FileNotFoundError(
            f"Для задания '{task_slug}' не найдено окружение: {task_path}"
        )

    try:
        client.images.get(image_name)

    except docker.errors.ImageNotFound:
        client.images.build(
            path=str(task_path),
            tag=image_name,
        )

    container = client.containers.run(
        image=image_name,
        name=container_name,
        detach=True,
        tty=True,
        mem_limit="768m",
        pids_limit=256,
        security_opt=[
            "no-new-privileges:true",
        ],
        cap_drop=[
            "AUDIT_WRITE",
            "MKNOD",
        ],
        tmpfs={
            "/tmp": "rw,nosuid,size=128m",
            "/run": "rw,nosuid,size=64m",
        },
        labels={
            "ticket-sandbox.type": "task",
            "ticket-sandbox.queue": queue_slug,
            "ticket-sandbox.task": task_slug,
            "ticket-sandbox.attempt": str(attempt_id),
        },
    )

    return container


def check_task_container(container_name: str):
    client = get_docker_client()

    container = client.containers.get(container_name)

    timeout_seconds = settings.CHECK_TASK_TIMEOUT_SECONDS

    exit_code, output = container.exec_run(
        cmd=[
            "timeout",
            "--kill-after=5s",
            f"{timeout_seconds}s",
            "bash",
            "/task/check.sh",
        ],
        stdout=True,
        stderr=True,
    )

    decoded_output = output.decode("utf-8", errors="replace")

    if exit_code == 124:
        decoded_output = (
            decoded_output.rstrip()
            + "\n\n"
            + f"Проверка остановлена: check.sh выполнялся дольше {timeout_seconds} секунд."
        ).strip()

    return exit_code, decoded_output


def remove_task_container(container_name: str):
    client = get_docker_client()

    try:
        container = client.containers.get(container_name)
        container.remove(force=True)
        return True, f"Контейнер {container_name} удален."
    except docker.errors.NotFound:
        return True, f"Контейнер {container_name} уже отсутствует."


def create_terminal_container(
    queue_slug: str,
    task_slug: str,
    attempt_id: int,
    target_container_name: str,
    port: int,
    base_path: str = "",
):
    client = get_docker_client()

    terminal_container_name = f"ticket-sandbox-terminal-{queue_slug}-{task_slug}-{attempt_id}"
    socket_path = get_docker_socket_path()

    try:
        old_container = client.containers.get(terminal_container_name)
        old_container.remove(force=True)
    except docker.errors.NotFound:
        pass

    base_path_option = ""

    if base_path:
        base_path_option = f"--base-path {base_path} "

    container = client.containers.run(
        image="ticket-sandbox-ttyd",
        name=terminal_container_name,
        command=(
            "ttyd -W "
            f"{base_path_option}"
            "sh -c "
            f"'docker exec -it {target_container_name} bash'"
        ),
        volumes={
            socket_path: {
                "bind": "/var/run/docker.sock",
                "mode": "rw",
            }
        },
        ports={
            "7681/tcp": ("127.0.0.1", port),
        },
        detach=True,
        mem_limit="256m",
        pids_limit=128,
        security_opt=[
            "no-new-privileges:true",
        ],
        cap_drop=[
            "ALL",
        ],
        tmpfs={
            "/tmp": "rw,nosuid,size=64m",
        },
        labels={
            "ticket-sandbox.type": "terminal",
            "ticket-sandbox.queue": queue_slug,
            "ticket-sandbox.task": task_slug,
            "ticket-sandbox.attempt": str(attempt_id),
        },
    )

    return container


def remove_terminal_container(container_name: str):
    client = get_docker_client()

    if not container_name:
        return True, "Контейнер терминала не указан."

    try:
        container = client.containers.get(container_name)
        container.remove(force=True)
        return True, f"Контейнер терминала {container_name} удален."
    except docker.errors.NotFound:
        return True, f"Контейнер терминала {container_name} уже отсутствует."
