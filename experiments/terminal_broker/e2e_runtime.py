"""Explicit opt-in Docker E2E fixture. Run only on a disposable lab/CI Docker host.

No existing resource is removed. Source and /lab must be separate bind mounts.
The driver needs the project's dependencies and Docker socket; ttyd does not.
Containers/volumes are retained until an operator explicitly cleans them up.
"""
import json
import os
from pathlib import Path
import secrets
import threading
import time
import uuid
from socketserver import ThreadingMixIn
from wsgiref.simple_server import WSGIRequestHandler, WSGIServer, make_server

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django
django.setup()

import docker
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.wsgi import get_wsgi_application
from django.test import Client, override_settings

from sandbox.models import Queue, Task, TaskAttempt, TraineeProfile
from sandbox.services.docker_service import _create_broker_terminal

PREFIX = os.environ.get("TB_E2E_PREFIX", "tc-tb2-20261028-")
if not PREFIX.startswith("tc-tb2-") or not PREFIX.endswith("-"):
    raise RuntimeError("A dedicated tc-tb2- prefix is required")
ROOT = Path(os.environ.get("TB_E2E_ROOT", "/lab"))
HOST_ROOT = os.environ["TB_E2E_HOST_ROOT"]
NETWORK = os.environ["TERMINAL_DOCKER_NETWORK"]
client = docker.from_env(timeout=10)
control = secrets.token_hex(32)
fixtures = {}
django_lock = threading.Lock()


def bootstrap():
    call_command("migrate", interactive=False, verbosity=0)
    users = [get_user_model().objects.create_user(username=name) for name in ("tb2-owner", "tb2-outsider")]
    profile, _ = TraineeProfile.objects.get_or_create(user=users[0])
    profile.level = "l1"
    profile.save(update_fields=["level"])
    queue, _ = Queue.objects.get_or_create(slug="l1", defaults={"name": "Lab", "required_level": "l1"})
    task = Task.objects.create(queue=queue, title="Broker E2E", slug="broker-e2e", order=1)
    sessions = []
    for user in users:
        browser = Client()
        browser.force_login(user)
        sessions.append(browser.cookies[settings.SESSION_COOKIE_NAME].value)
    for index, mode in enumerate(("host_port", "docker_network")):
        generation = str(uuid.uuid4())
        # Separate Task rows keep both attempts current and available.
        if index:
            queue = Queue.objects.create(slug="tb2-e2e-network", name="Isolated network E2E", required_level="l1")
            task = Task.objects.create(queue=queue, title="Broker E2E network", slug="broker-e2e-network", order=1)
        attempt = TaskAttempt.objects.create(user=users[0], task=task, status="in_progress",
            environment_generation=generation, environment_status="starting")
        # Use the same task slug in Docker identity and DB for this mode.
        slug = task.slug
        target = client.containers.run(os.environ["TB_E2E_TARGET_IMAGE"], ["sleep", "infinity"],
            name=PREFIX + mode + "-target", detach=True, init=True, labels={
                "ticket-sandbox.type": "task", "ticket-sandbox.attempt": str(attempt.pk),
                "ticket-sandbox.queue": queue.slug, "ticket-sandbox.task": slug,
                "ticket-sandbox.generation": generation, "terminal-broker.e2e": PREFIX},
            mem_limit="128m", pids_limit=128, security_opt=["no-new-privileges:true"])
        attempt.container_id = target.id
        attempt.container_name = target.name
        attempt.save(update_fields=["container_id", "container_name"])
        sentinel = client.api.exec_create(target.id, ["sleep", "600"])["Id"]
        client.api.exec_start(sentinel, detach=True)
        port = 29183 if mode == "host_port" else None
        path = f"/terminal/{attempt.pk}/{port}/" if port else f"/terminal/{attempt.pk}/"
        fixtures[mode] = {"attempt": attempt, "target": target, "port": port, "path": path,
                          "name": PREFIX + mode + "-terminal", "slug": slug, "queue": queue.slug,
                          "sentinel": sentinel}
    # Publish session data only into the private lab mount; never print it.
    (ROOT / "session.json").write_text(json.dumps({"owner": sessions[0], "outsider": sessions[1],
        "control": control, "paths": {mode: item["path"] for mode, item in fixtures.items()}}))
    (ROOT / "session.json").chmod(0o600)


def statistics(mode):
    item = fixtures[mode]
    # Inspect namespace processes without returning environment values/tokens.
    code, output = item["target"].exec_run(["python3", "-I", "-c", """
import os,json,select
owned=[]
for entry in os.listdir('/proc'):
    if not entry.isdigit() or int(entry)<=1: continue
    try:
        env=open('/proc/'+entry+'/environ','rb').read().split(b'\\0')
        if any(x.startswith(b'TB_SESSION_TOKEN=') for x in env): owned.append(int(entry))
    except PermissionError:
        try:
            fd=os.pidfd_open(int(entry))
            try:
                if not select.select([fd],[],[],.25)[0]: raise
            finally: os.close(fd)
        except (FileNotFoundError, ProcessLookupError): pass
    except (FileNotFoundError, ProcessLookupError): pass
print(json.dumps(owned))
"""])
    if code:
        print("Process census failed:", output.decode(errors="replace"), flush=True)
        raise RuntimeError("Process census failed")
    item["target"].reload()
    broker = client.containers.get(item["name"] + "-broker")
    return {"pids": json.loads(output), "pid1Running": item["target"].attrs["State"]["Running"],
            "foreignRunning": client.api.exec_inspect(item["sentinel"])["Running"],
            "brokerErrors": b"ERROR:terminal.broker" in broker.logs()}


def action(obj):
    mode = obj["mode"]
    item = fixtures[mode]
    attempt = TaskAttempt.objects.get(pk=item["attempt"].pk)
    operation = obj["action"]
    if operation == "stats":
        return statistics(mode)
    if operation == "kill":
        broker = client.containers.get(item["name"] + "-broker")
        _, digest = broker.exec_run(["python", "-c", "import hashlib; print(hashlib.sha256(open('/run/terminal/client.json','rb').read()).hexdigest())"])
        item["old_config_digest"] = digest
        # Freeze automatic restart only for this disposable fault-injection test.
        # Recovery must clean an intentionally HUP/TERM-resistant orphan.
        broker.update(restart_policy={"Name": "no"})
        broker.kill(signal="SIGKILL")
        return {"ok": True}
    if operation == "restart-broker":
        broker = client.containers.get(item["name"] + "-broker")
        broker.start()
        for _ in range(100):
            try:
                code, digest = broker.exec_run(["python", "-c", "import hashlib; print(hashlib.sha256(open('/run/terminal/client.json','rb').read()).hexdigest())"])
                if code == 0 and digest != item["old_config_digest"]:
                    return {"ok": True}
            except docker.errors.APIError:
                pass
            time.sleep(.1)
        raise RuntimeError("Broker recovery did not reach readiness")
    if operation in ("revoke", "allow"):
        attempt.environment_status = "restarting" if operation == "revoke" else "ready"
        attempt.save(update_fields=["environment_status"])
        return {"ok": True}
    if operation == "replace-generation":
        attempt.environment_generation = uuid.uuid4()
        attempt.save(update_fields=["environment_generation"])
        return {"ok": True}
    raise ValueError("Unknown test operation")


class ThreadingServer(ThreadingMixIn, WSGIServer):
    daemon_threads = True


class QuietHandler(WSGIRequestHandler):
    def log_message(self, *_):
        pass


django_app = get_wsgi_application()


def application(environ, start_response):
    if environ["PATH_INFO"] == "/__e2e__/action":
        if not secrets.compare_digest(environ.get("HTTP_AUTHORIZATION", ""), "Bearer " + control):
            start_response("403 Forbidden", [])
            return [b""]
        try:
            count = int(environ.get("CONTENT_LENGTH") or 0)
            if not 0 < count < 2048:
                raise ValueError
            result = action(json.loads(environ["wsgi.input"].read(count)))
            start_response("200 OK", [("Content-Type", "application/json")])
            return [json.dumps(result).encode()]
        except Exception as exc:
            start_response("500 Error", [("Content-Type", "text/plain")])
            return [type(exc).__name__.encode()]
    # One Django service exercises both gateway modes against the same DB.
    path = environ["PATH_INFO"]
    mode = "host_port" if any(item["path"] in environ.get("HTTP_X_ORIGINAL_URI", "")
        for key, item in fixtures.items() if key == "host_port") else "docker_network"
    if path.startswith("/terminal-broker-auth/"):
        mode = "docker_network"  # lease checks do not depend on gateway mode
    with django_lock, override_settings(TERMINAL_NETWORK_MODE=mode):
        return django_app(environ, start_response)


def main():
    ROOT.mkdir(parents=True, exist_ok=True)
    bootstrap()
    server = make_server("0.0.0.0", 8000, application, server_class=ThreadingServer, handler_class=QuietHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    for mode in fixtures:
        item = fixtures[mode]
        # launch() intentionally goes through Django's real Docker launcher.
        # Each mode uses its corresponding immutable DB task slug.
        with override_settings(TERMINAL_NETWORK_MODE=mode):
            terminal = _create_broker_terminal(client, item["queue"], item["slug"], item["attempt"].pk,
                item["target"].id, item["port"], item["path"], "/var/run/docker.sock",
                terminal_name=item["name"])
        attempt = item["attempt"]
        attempt.terminal_container_name = terminal.name
        attempt.terminal_port = item["port"]
        attempt.terminal_url = item["path"]
        attempt.environment_status = "ready"
        attempt.save(update_fields=["terminal_container_name", "terminal_port", "terminal_url", "environment_status"])
    (ROOT / "ready").write_text("ready")
    print("E2E FIXTURE READY", flush=True)
    while True:
        time.sleep(1)


if __name__ == "__main__":
    main()
