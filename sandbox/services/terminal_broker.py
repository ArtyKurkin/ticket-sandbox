"""Trusted launcher and lifecycle for one broker per environment generation."""
import base64
import hashlib
import hmac
import time

import docker
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured


def credential(attempt_id, generation):
    message = f"terminal-broker-v2:{attempt_id}:{generation}".encode()
    return hmac.new(settings.SECRET_KEY.encode(), message, hashlib.sha256).hexdigest()


def lease_credential(attempt_id, generation):
    """Do not let a ttyd Basic password authorize internal Django lease calls."""
    message = f"terminal-broker-v2-lease:{attempt_id}:{generation}".encode()
    return hmac.new(settings.SECRET_KEY.encode(), message, hashlib.sha256).hexdigest()


def authorization_header(attempt_id, generation):
    raw = f"broker:{credential(attempt_id, generation)}".encode()
    return "Basic " + base64.b64encode(raw).decode()


def launch(client, queue, task, attempt, target, terminal_name, socket_path):
    from sandbox.services.terminal_gateway import terminal_gateway_enabled
    from terminal.broker_v2 import Identity
    from terminal.runtime_probe import SOURCE

    if not terminal_gateway_enabled():
        raise ImproperlyConfigured("Broker requires the authenticated terminal gateway")
    target = client.containers.get(target)
    target.reload()
    generation = target.labels.get("ticket-sandbox.generation", "")
    identity = Identity(target.id, attempt, queue, task, generation)
    if not identity.matches(target.attrs):
        raise ValueError("Task identity mismatch")
    # Fail before exposing a terminal if a task image lacks safe cleanup support.
    code, _ = target.exec_run(["python3", "-I", "-c", SOURCE])
    if code != 0:
        raise RuntimeError("Task image needs Bash, /proc and Python 3.9+ with Linux pidfd support")
    name = terminal_name + "-broker"
    socket_volume = name + "-" + generation + "-socket"
    state_volume = name + "-" + generation + "-state"
    labels = {"ticket-sandbox.type": "terminal-broker", "ticket-sandbox.attempt": str(attempt),
              "ticket-sandbox.generation": generation, "ticket-sandbox.target": target.id,
              "ticket-sandbox.queue": queue, "ticket-sandbox.task": task,
              "ticket-sandbox.terminal": terminal_name}
    broker = client.containers.run(
        image=settings.TERMINAL_BROKER_IMAGE, name=name, detach=True,
        command=["--container-id", target.id, "--attempt", str(attempt), "--queue", queue,
                 "--task", task, "--generation", generation, "--socket-dir", "/run/terminal",
                 "--state-dir", "/var/lib/terminal", "--authorization-url",
                 settings.TERMINAL_BROKER_AUTHORIZATION_URL],
        environment={"TB_AUTHORIZATION_TOKEN": lease_credential(attempt, generation)},
        volumes={socket_path: {"bind": "/var/run/docker.sock", "mode": "rw"},
                 socket_volume: {"bind": "/run/terminal", "mode": "rw"},
                 state_volume: {"bind": "/var/lib/terminal", "mode": "rw"}},
        network=settings.TERMINAL_DOCKER_NETWORK,
        labels=labels, mem_limit="128m", pids_limit=64, read_only=True,
        cap_drop=["ALL"], security_opt=["no-new-privileges:true"],
        restart_policy={"Name": "on-failure", "MaximumRetryCount": 3},
    )
    # Readiness must come from the process, not merely an open ttyd TCP port.
    deadline = time.monotonic() + settings.TERMINAL_BROKER_START_TIMEOUT
    while time.monotonic() < deadline:
        broker.reload()
        if broker.status != "running":
            raise RuntimeError("Terminal broker exited before readiness; journal retained")
        code, _ = broker.exec_run(["python", "-c",
            "from pathlib import Path; import sys; sys.exit(not Path('/run/terminal/client.json').is_file())"])
        if code == 0:
            return broker, socket_volume, generation
        time.sleep(.1)
    raise RuntimeError("Terminal broker readiness timeout; journal retained")


def revoke(client, terminal_name, *, target_id=None, generation=None):
    """Never delete state volumes. A failed reconciliation remains reviewable."""
    try:
        broker = client.containers.get(terminal_name + "-broker")
    except docker.errors.NotFound:
        return
    if (broker.labels.get("ticket-sandbox.type") != "terminal-broker"
            or broker.labels.get("ticket-sandbox.terminal") != terminal_name
            or (target_id is not None and broker.labels.get("ticket-sandbox.target") != target_id)
            or (generation is not None and broker.labels.get("ticket-sandbox.generation") != generation)):
        raise RuntimeError("Refusing to stop a foreign container")
    broker.stop(timeout=20)
    # A forced stop or a cleanup failure must be reconciled before removing the
    # broker container. Otherwise its restart path and identity would be lost.
    code = broker.wait(timeout=5)["StatusCode"]
    if code != 0:
        raise RuntimeError("Broker stopped without confirmed cleanup; retained for recovery")
    broker.remove()
