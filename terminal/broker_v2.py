"""One immutable task identity per broker. Only this trusted service sees Docker.

The old laboratory entrypoint remains available for reproducing earlier tests.
Lite uses Docker's PTY directly and journals each exact interactive process.
Requires Linux python3 with pidfd support in the task image for safe cleanup.
"""
import argparse
import dataclasses
import fcntl
import hmac
import json
import logging
import os
from pathlib import Path
import re
import secrets
import select
import signal
import socket
import tempfile
import threading
import time
import uuid
import urllib.request
import urllib.error

import docker

from experiments.terminal_broker.terminal_broker import prepare_socket_path
from terminal.protocol import dimensions, receive

log = logging.getLogger("terminal.broker")
FULL_ID = re.compile(r"[0-9a-f]{64}\Z")
TOKEN = re.compile(r"[0-9a-f]{32}\Z")


@dataclasses.dataclass(frozen=True)
class Identity:
    container_id: str
    attempt: int
    queue: str
    task: str
    generation: str

    def __post_init__(self):
        if (not FULL_ID.fullmatch(self.container_id) or type(self.attempt) is not int
                or self.attempt < 1 or str(uuid.UUID(self.generation)) != self.generation
                or not all(re.fullmatch(r"[a-z0-9_-]{1,100}", s) for s in (self.queue, self.task))):
            raise ValueError("Invalid immutable task identity")

    def matches(self, obj):
        labels = obj.get("Config", {}).get("Labels") or {}
        return (obj.get("Id") == self.container_id
                and obj.get("State", {}).get("Running") is True
                and all(labels.get("ticket-sandbox." + key) == value for key, value in {
                    "type": "task", "attempt": str(self.attempt), "queue": self.queue,
                    "task": self.task, "generation": self.generation,
                }.items()))


def atomic_json(path, content):
    fd, temp = tempfile.mkstemp(prefix=".pending-", dir=path.parent)
    try:
        with os.fdopen(fd, "w") as output:
            os.fchmod(output.fileno(), 0o600)
            json.dump(content, output)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temp, path)
        sync_dir(path.parent)
    finally:
        Path(temp).unlink(missing_ok=True)


def sync_dir(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


from terminal.session_exec import BOOTSTRAP, CLEANUP


class Broker:
    def __init__(self, api, identity, state_dir, socket_dir, max_sessions=4,
                 authorization_url=None, authorization_token=None):
        self.api = api
        self.identity = identity
        self.state = Path(state_dir)
        self.socket_dir = Path(socket_dir)
        self.shutdown = threading.Event()
        self.slots = threading.BoundedSemaphore(max_sessions)
        self.workers = set()
        self.credential = secrets.token_hex(32)
        self.failed = threading.Event()
        self.authorization_url = authorization_url
        self.authorization_token = authorization_token

    def authorized(self):
        if not self.authorization_url:
            return False
        try:
            request = urllib.request.Request(self.authorization_url,
                data=json.dumps(dataclasses.asdict(self.identity)).encode(),
                headers={"Authorization": "Bearer " + self.authorization_token,
                         "Content-Type": "application/json"})
            # Do not forward credentials through redirects or environment proxies.
            class NoRedirect(urllib.request.HTTPRedirectHandler):
                def redirect_request(self, *args):
                    return None
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
            with opener.open(request, timeout=2) as response:
                return response.status == 204
        except (OSError, urllib.error.URLError, ValueError, TypeError):
            return False

    def valid(self):
        try:
            return self.identity.matches(self.api.inspect_container(self.identity.container_id))
        except (docker.errors.DockerException, OSError, ValueError):
            return False

    def save(self, token, exec_id, process=None):
        atomic_json(self.state / (token + ".json"), {
            "version": 3, "identity": dataclasses.asdict(self.identity),
            "token": token, "exec_id": exec_id, "process": process,
        })

    def cleanup(self, token, exec_id):
        """Keep the journal and fail closed if Docker cannot confirm cleanup."""
        try:
            info = self.api.exec_inspect(exec_id)
            if info.get("ContainerID") != self.identity.container_id:
                return False
            # A never-started Exec has no process and needs no cleanup command.
            if not info["Running"] and info.get("ExitCode") is None:
                return True
            # A removed container proves all its namespace processes are gone.
            try:
                target = self.api.inspect_container(self.identity.container_id)
            except docker.errors.NotFound:
                return True
            if not self.identity.matches(target):
                return not target.get("State", {}).get("Running", True)
            if not info["Running"] and info.get("ExitCode") is not None:
                return True  # Background processes belong to the task lifetime.
            record = json.loads((self.state / (token + ".json")).read_text())
            process = record.get("process")
            if process is None:
                # Bootstrap cannot exec Bash without a durable identity + ACK.
                for _ in range(60):
                    if not self.api.exec_inspect(exec_id)["Running"]:
                        return True
                    time.sleep(.1)
                return False
            if (set(process) != {"pid", "start"}
                    or any(type(process[k]) is not int for k in process)
                    or process["pid"] <= 1 or process["start"] <= 0):
                return False
            helper = self.api.exec_create(self.identity.container_id,
                ["python3", "-I", "-c", CLEANUP, str(process["pid"]), str(process["start"])], tty=False)["Id"]
            helper_output = self.api.exec_start(helper)
            for _ in range(20):
                helper_state = self.api.exec_inspect(helper)
                if not helper_state["Running"]:
                    break
                time.sleep(.1)
            else:
                log.error("Cleanup helper exit was not published")
                return False
            if helper_state["ExitCode"] != 0:
                log.error("Cleanup helper failed (exit %s): %r", helper_state["ExitCode"], helper_output[-2048:])
                return False
            # The helper can observe process exit before Docker publishes its
            # final Exec state. Do not mistake that short race for failed cleanup.
            for _ in range(20):
                if not self.api.exec_inspect(exec_id)["Running"]:
                    return True
                time.sleep(.1)
            return False
        except docker.errors.NotFound:
            # Missing Exec alone is ambiguous while its container still exists.
            try:
                self.api.inspect_container(self.identity.container_id)
            except docker.errors.NotFound:
                return True
            except (docker.errors.DockerException, OSError):
                pass
            return False
        except (docker.errors.DockerException, OSError, KeyError, ValueError, TypeError):
            log.exception("Session cleanup unconfirmed")
            return False

    def recover(self):
        success = True
        for path in sorted(self.state.glob("*.json")):
            try:
                if path.is_symlink():
                    raise ValueError("Symlink journal")
                record = json.loads(path.read_text())
                token, exec_id = record["token"], record["exec_id"]
                process = record['process']
                if process is not None and (type(process) is not dict or set(process) != {'pid', 'start'}
                        or any(type(process[k]) is not int for k in process)
                        or process['pid'] <= 1 or process['start'] <= 0):
                    raise ValueError('Invalid process journal')
                if (record.get("version") != 3 or record["identity"] != dataclasses.asdict(self.identity)
                        or not TOKEN.fullmatch(token) or path.name != token + ".json"
                        or not FULL_ID.fullmatch(exec_id)):
                    raise ValueError("Foreign or malformed journal")
                if not self.cleanup(token, exec_id):
                    raise RuntimeError("Orphan cleanup unconfirmed")
                path.unlink()
                sync_dir(self.state)
            except (OSError, ValueError, TypeError, KeyError, RuntimeError):
                log.exception("Recovery blocked: %s", path.name)
                success = False
        return success

    def authenticate(self, conn):
        deadline = time.monotonic() + 3
        kind, payload = receive(conn, deadline)
        obj = json.loads(payload)
        if (kind != b"H" or type(obj) is not dict or set(obj) != {"version", "credential"}
                or type(obj["version"]) is not int or obj["version"] != 2 or type(obj["credential"]) is not str
                or not hmac.compare_digest(obj["credential"], self.credential)):
            raise ValueError("Unauthorized terminal client")
        conn.sendall(b"\x01")
        kind, payload = receive(conn, deadline)
        if kind != b"R":
            raise ValueError("Initial dimensions required")
        return dimensions(payload)

    def session(self, conn):
        exec_id = None
        attached = None
        token = secrets.token_hex(16)
        stop = threading.Event()
        output = None
        try:
            rows, cols = self.authenticate(conn)
            if self.failed.is_set() or self.shutdown.is_set() or not self.valid() or not self.authorized():
                return
            exec_id = self.api.exec_create(self.identity.container_id,
                ["python3", "-I", "-c", BOOTSTRAP], stdin=True, tty=True,
                environment={"TB_SESSION_TOKEN": token, "TERM": "xterm-256color"},
                detach_keys="")["Id"]
            # No process exists until its Exec ID is durable. A crash during
            # create can leave only an unstarted Docker Exec, never a shell.
            self.save(token, exec_id)
            attached = self.api.exec_start(exec_id, tty=True, socket=True)
            raw = getattr(attached, "_sock", attached)
            raw.settimeout(2)
            header = bytearray()
            while not header.endswith(b"\n"):
                if len(header) > 256:
                    raise ValueError("Invalid Exec bootstrap")
                part = raw.recv(1)
                if not part:
                    raise EOFError("Exec bootstrap ended")
                header.extend(part)
            if not header.startswith(b"TB2 "):
                raise ValueError("Invalid Exec bootstrap prefix")
            process = json.loads(header[4:])
            if (type(process) is not dict or set(process) != {"pid", "start"}
                    or any(type(process[k]) is not int for k in process)
                    or process["pid"] <= 1 or process["start"] <= 0):
                raise ValueError("Invalid Exec process identity")
            self.save(token, exec_id, process)
            self.api.exec_resize(exec_id, height=rows, width=cols)
            raw.sendall(b"G")
            conn.settimeout(2)

            def downstream():
                try:
                    while not stop.is_set():
                        ready, _, _ = select.select([raw], [], [], .2)
                        if not ready:
                            continue
                        data = raw.recv(16384)
                        if not data:
                            break
                        conn.sendall(data)
                except OSError:
                    pass
                finally:
                    stop.set()

            output = threading.Thread(target=downstream, daemon=True)
            output.start()
            next_validate = time.monotonic()
            # Parse frames incrementally: a client sending only part of a frame
            # cannot suppress lifecycle checks or cause unbounded buffering.
            from terminal.protocol import HEADER, MAX_FRAME
            buffer = bytearray()
            while not stop.is_set() and not self.shutdown.is_set() and not self.failed.is_set():
                if time.monotonic() >= next_validate:
                    if not self.valid() or not self.authorized():
                        break
                    next_validate = time.monotonic() + .5
                ready, _, _ = select.select([conn], [], [], .2)
                if not ready:
                    continue
                data = conn.recv(16384)
                if not data:
                    break
                buffer.extend(data)
                while len(buffer) >= HEADER.size:
                    kind, size = HEADER.unpack(buffer[:HEADER.size])
                    if size > MAX_FRAME:
                        raise ValueError("Frame too large")
                    if len(buffer) < HEADER.size + size:
                        break
                    payload = bytes(buffer[HEADER.size:HEADER.size + size])
                    del buffer[:HEADER.size + size]
                    if kind == b"I":
                        raw.sendall(payload)
                    elif kind == b"R":
                        rows, cols = dimensions(payload)
                        self.api.exec_resize(exec_id, height=rows, width=cols)
                    else:
                        raise ValueError("Unknown terminal operation")
        except (OSError, EOFError, ValueError, TypeError, docker.errors.DockerException):
            log.info("Terminal connection ended", exc_info=True)
        finally:
            stop.set()
            # Shutdown both directions before joining the bounded output worker.
            try:
                conn.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            if output:
                output.join(3)
            if attached:
                # Close the owning HTTP response before its raw SocketIO. The
                # reverse order causes http.client to flush an already closed fp.
                response = getattr(attached, "_response", None)
                try:
                    if response is not None:
                        response.close()
                except (OSError, ValueError):
                    log.warning("Docker HTTP stream was already closed")
                try:
                    attached.close()
                except (OSError, ValueError):
                    pass
            if exec_id:
                if self.cleanup(token, exec_id):
                    (self.state / (token + ".json")).unlink(missing_ok=True)
                    sync_dir(self.state)
                else:
                    self.failed.set()
                    log.error("Cleanup unresolved; denying new sessions")

    def run(self):
        for path in (self.state, self.socket_dir):
            path.mkdir(mode=0o700, parents=True, exist_ok=True)
            if path.is_symlink() or path.stat().st_uid != os.geteuid():
                raise RuntimeError("Private owned directories required")
            path.chmod(0o700)
        lock = os.open(self.state / ".broker.lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            if not self.recover() or not self.valid():
                raise RuntimeError("Recovery or task identity validation failed")
            sockpath = self.socket_dir / "broker.sock"
            prepare_socket_path(sockpath)
            with socket.socket(socket.AF_UNIX) as server:
                server.bind(str(sockpath))
                sockpath.chmod(0o600)
                server.listen(4)
                server.settimeout(.2)
                atomic_json(self.socket_dir / "client.json", {"credential": self.credential})
                log.info("BROKER READY")
                try:
                    while not self.shutdown.is_set() and not self.failed.is_set():
                        if not self.valid():
                            self.shutdown.set()
                            break
                        try:
                            conn, _ = server.accept()
                        except socket.timeout:
                            continue
                        if not self.slots.acquire(blocking=False):
                            conn.close()
                            continue

                        def work(client):
                            try:
                                with client:
                                    self.session(client)
                            finally:
                                self.slots.release()

                        self.workers = {w for w in self.workers if w.is_alive()}
                        worker = threading.Thread(target=work, args=(conn,))
                        self.workers.add(worker)
                        worker.start()
                finally:
                    self.shutdown.set()
                    for worker in self.workers:
                        worker.join()
                    sockpath.unlink(missing_ok=True)
                    (self.socket_dir / "client.json").unlink(missing_ok=True)
        finally:
            os.close(lock)
        if self.failed.is_set():
            raise RuntimeError("Unresolved cleanup; journal retained")


def main():
    parser = argparse.ArgumentParser()
    for key in ("container-id", "queue", "task", "generation", "state-dir", "socket-dir"):
        parser.add_argument("--" + key, required=True)
    parser.add_argument("--attempt", required=True, type=int)
    parser.add_argument("--authorization-url", required=True)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    api = docker.from_env(timeout=5).api
    broker = Broker(api, Identity(args.container_id, args.attempt, args.queue, args.task, args.generation),
                    args.state_dir, args.socket_dir, authorization_url=args.authorization_url,
                    authorization_token=os.environ["TB_AUTHORIZATION_TOKEN"])
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda *_: broker.shutdown.set())
    broker.run()


if __name__ == "__main__":
    main()
