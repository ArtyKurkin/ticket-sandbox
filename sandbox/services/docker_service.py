from pathlib import Path

import time
import docker
import random
import socket
import uuid
import hashlib

from django.conf import settings

from sandbox.services.terminal_gateway import terminal_uses_docker_network


def task_resource_name(queue_slug, task_slug, attempt_id=None, *, terminal=False):
    # The default is unchanged. Isolated test settings use a private namespace
    # while exercising the actual production launcher without monkeypatches.
    prefix = getattr(settings, "SANDBOX_DOCKER_PREFIX", "ticket-sandbox")
    suffix = f"-{attempt_id}" if attempt_id is not None else ""
    kind = "-terminal" if terminal else ""
    name = f"{prefix}{kind}-{queue_slug}-{task_slug}{suffix}"
    # Docker accepts longer names, but DNS/idna consumers reject labels >63.
    # Keep short legacy names stable; full identity remains in immutable labels.
    if len(name) > 63:
        return name[:46] + '-' + hashlib.sha256(name.encode()).hexdigest()[:16]
    return name


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


def wait_for_terminal_ready(
    terminal_container_name: str,
    port: int | None = None,
    timeout_seconds: float = 10.0,
):
    deadline = time.monotonic() + timeout_seconds

    if terminal_uses_docker_network():
        host = terminal_container_name
        target_port = 7681
    else:
        if port is None:
            raise ValueError(
                "Для режима host_port необходимо указать порт терминала"
            )

        host = "127.0.0.1"
        target_port = port

    while time.monotonic() < deadline:
        try:
            with socket.create_connection(
                (host, target_port),
                timeout=1,
            ):
                return

        except OSError:
            time.sleep(0.2)

    raise RuntimeError(
        f"Терминал {terminal_container_name} "
        f"не стал доступен за {timeout_seconds} секунд"
    )


def create_task_container(queue_slug: str, task_slug: str, attempt_id: int):
    client = get_docker_client()

    container_name = task_resource_name(queue_slug, task_slug, attempt_id)
    image_name = task_resource_name(queue_slug, task_slug)

    task_path = Path(f"training_tasks/{queue_slug}/{task_slug}")

    if not task_path.exists():
        raise FileNotFoundError(
            f"Для задания '{task_slug}' не найдено окружение: {task_path}"
        )

    try:
        from .observation_config import selected, pilot_launch
        pilot = selected(queue_slug, task_slug, attempt_id)
        pilot_options = {}
        if pilot:
            image_name, pilot_options = pilot_launch(client, attempt_id)
        else:
            client.images.get(image_name)

    except docker.errors.ImageNotFound:
        if pilot:
            raise
        client.images.build(
            path=str(task_path),
            tag=image_name,
        )

    container = client.containers.run(
        image=image_name,
        name=container_name,
        detach=True,
        tty=True,
        **({"init": True} if settings.TERMINAL_BROKER_ENABLED else {}),
        environment={"TZ": settings.TASK_CONTAINER_TZ},
        mem_limit="768m",
        pids_limit=256,
        security_opt=[
            "no-new-privileges:true",
        ],
        cap_drop=["ALL"] if pilot else [
            "AUDIT_WRITE",
            "MKNOD",
        ],
        tmpfs={} if pilot else {
            "/tmp": "rw,nosuid,size=128m",
            "/run": "rw,nosuid,size=64m",
        },
        labels={
            **pilot_options.pop("labels", {}),
            "ticket-sandbox.type": "task",
            "ticket-sandbox.queue": queue_slug,
            "ticket-sandbox.task": task_slug,
            "ticket-sandbox.attempt": str(attempt_id),
            **({"ticket-sandbox.generation": str(uuid.uuid4())}
               if settings.TERMINAL_BROKER_ENABLED else {}),
        },
        **pilot_options,
    )

    return container


def check_task_container(container_name: str):
    try:
        client = get_docker_client()

        container = client.containers.get(container_name)

        timeout_seconds = settings.CHECK_TASK_TIMEOUT_SECONDS
        check_command = ["bash", "/task/check.sh"]
        if (
            container.labels.get("ticket-sandbox.queue") == "l1"
            and container.labels.get("ticket-sandbox.task") == "wordpress-500-after-move"
        ):
            # Keep validation logic outside the trainee image: no solution hints in
            # /task/check.sh and no writable local checker that can grant a pass.
            source = (
                Path(__file__).resolve().parent.parent
                / "task_checks" / "wordpress_runtime.php"
            ).read_text(encoding="utf-8")
            check_command = ["php", "-r", source.removeprefix("<?php\n")]

    except Exception as error:
        error._sandbox_checker_started = False
        raise

    exit_code, output = container.exec_run(
        cmd=[
            "timeout",
            "--kill-after=5s",
            f"{timeout_seconds}s",
            *check_command,
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
        # Revoke associated broker even when the feature flag was switched off
        # after this environment was created.
        if container.labels.get("ticket-sandbox.generation"):
            from .terminal_broker import revoke
            terminal_name = task_resource_name(container.labels["ticket-sandbox.queue"],
                container.labels["ticket-sandbox.task"], container.labels["ticket-sandbox.attempt"], terminal=True)
            revoke(client, terminal_name,
                   target_id=container.id, generation=container.labels["ticket-sandbox.generation"])
        container.remove(force=True)
        return True, f"Контейнер {container_name} удален."
    except docker.errors.NotFound:
        return True, f"Контейнер {container_name} уже отсутствует."


def create_terminal_container(
    queue_slug: str,
    task_slug: str,
    attempt_id: int,
    target_container_name: str,
    port: int | None,
    base_path: str = "",
):
    client = get_docker_client()

    terminal_container_name = task_resource_name(queue_slug, task_slug, attempt_id, terminal=True)

    socket_path = get_docker_socket_path()

    if settings.TERMINAL_BROKER_ENABLED:
        return _create_broker_terminal(client, queue_slug, task_slug, attempt_id,
                                       target_container_name, port, base_path, socket_path)

    try:
        old_container = client.containers.get(
            terminal_container_name
        )
        old_container.remove(force=True)

    except docker.errors.NotFound:
        pass

    base_path_option = ""

    if base_path:
        base_path_option = f"--base-path {base_path} "

    run_kwargs = {
        "image": "ticket-sandbox-ttyd",
        "name": terminal_container_name,
        "command": (
            "ttyd -W "
            f"{base_path_option}"
            "sh -c "
            f"'docker exec -it {target_container_name} bash'"
        ),
        "volumes": {
            socket_path: {
                "bind": "/var/run/docker.sock",
                "mode": "rw",
            }
        },
        "detach": True,
        "mem_limit": "256m",
        "pids_limit": 128,
        "security_opt": [
            "no-new-privileges:true",
        ],
        "cap_drop": [
            "ALL",
        ],
        "tmpfs": {
            "/tmp": "rw,nosuid,size=64m",
        },
        "labels": {
            "ticket-sandbox.type": "terminal",
            "ticket-sandbox.queue": queue_slug,
            "ticket-sandbox.task": task_slug,
            "ticket-sandbox.attempt": str(attempt_id),
        },
    }

    if terminal_uses_docker_network():
        run_kwargs["network"] = settings.TERMINAL_DOCKER_NETWORK

    else:
        if port is None:
            raise ValueError(
                "Для режима host_port необходимо указать порт терминала"
            )

        run_kwargs["ports"] = {
            "7681/tcp": ("127.0.0.1", port),
        }

    container = client.containers.run(**run_kwargs)

    return container

def remove_terminal_container(container_name: str):
    client = get_docker_client()

    if not container_name:
        return True, "Контейнер терминала не указан."

    from .terminal_broker import revoke
    revoke(client, container_name)

    try:
        container = client.containers.get(container_name)
        container.remove(force=True)
        return True, f"Контейнер терминала {container_name} удален."
    except docker.errors.NotFound:
        return True, f"Контейнер терминала {container_name} уже отсутствует."


def _create_broker_terminal(client, queue, task, attempt, target, port, base_path, socket_path, *, terminal_name=None):
    from .terminal_broker import launch, credential
    name = terminal_name or task_resource_name(queue, task, attempt, terminal=True)
    if not terminal_uses_docker_network() and port is None:
        raise ValueError("host_port requires a terminal port")
    # Both old transports are opt-in; never silently fall back on broker error.
    remove_terminal_container(name)
    broker, volume, generation = launch(client, queue, task, attempt, target, name, socket_path)
    command = ["ttyd", "-W", "--check-origin", "--credential",
               f"broker:{credential(attempt, generation)}"]
    if base_path:
        command += ["--base-path", base_path]
    command += ["python3", "-m", "terminal.broker_client"]
    kwargs = dict(image=settings.TERMINAL_BROKER_TTYD_IMAGE, name=name, command=command,
        volumes={volume: {"bind": "/run/terminal", "mode": "ro"}}, detach=True,
        mem_limit="256m", pids_limit=128, read_only=True, cap_drop=["ALL"],
        security_opt=["no-new-privileges:true"], tmpfs={"/tmp": "rw,nosuid,size=64m"},
        labels={"ticket-sandbox.type": "terminal", "ticket-sandbox.attempt": str(attempt),
                "ticket-sandbox.queue": queue, "ticket-sandbox.task": task,
                "ticket-sandbox.generation": generation,
                "ticket-sandbox.target": broker.labels["ticket-sandbox.target"]})
    if terminal_uses_docker_network():
        kwargs["network"] = settings.TERMINAL_DOCKER_NETWORK
    else:
        kwargs["ports"] = {"7681/tcp": ("127.0.0.1", port)}
    try:
        return client.containers.run(**kwargs)
    except Exception:
        from .terminal_broker import revoke
        revoke(client, name)
        raise
