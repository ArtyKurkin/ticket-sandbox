"""Experimental per-attempt Unix-socket terminal broker.

Security boundary: socket file permissions and process isolation. Whoever can
connect to the socket gets a shell in the pinned task. Do not expose this socket
outside the dedicated terminal sidecar. Not production-ready: TTY resize and
lifecycle/revocation must be integrated into Django before rollout.
"""
from __future__ import annotations

import argparse
import errno
import json
import os
import pty
import re
import selectors
import signal
import socket
import subprocess
import threading
from pathlib import Path

ID_RE = re.compile(r"[a-f0-9]{64}\Z")
MAX_SESSIONS = 4


def inspect_target(container_id: str) -> dict:
    result = subprocess.run(
        ["docker", "inspect", "--type", "container", container_id],
        capture_output=True, text=True, check=True, timeout=5,
    )
    data = json.loads(result.stdout)
    if len(data) != 1:
        raise ValueError("Expected exactly one inspected container")
    return data[0]


def valid_target(container_id: str, attempt: int, queue: str, task: str) -> bool:
    try:
        obj = inspect_target(container_id)
        labels = obj["Config"].get("Labels") or {}
        return (
            obj["Id"] == container_id
            and obj["State"]["Running"] is True
            and labels.get("ticket-sandbox.type") == "task"
            and labels.get("ticket-sandbox.attempt") == str(attempt)
            and labels.get("ticket-sandbox.queue") == queue
            and labels.get("ticket-sandbox.task") == task
        )
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError):
        return False


def forward(source: int, destination: int, stop: threading.Event) -> None:
    """Forward in bounded chunks; do not buffer unbounded terminal output."""
    while not stop.is_set():
        readable, _, _ = __import__("select").select([source], [], [], 0.2)
        if not readable:
            continue
        try:
            chunk = os.read(source, 16384)
        except OSError as exc:
            if exc.errno in (errno.EIO, errno.ECONNRESET, errno.EBADF):
                return
            raise
        if not chunk:
            return
        view = memoryview(chunk)
        while view and not stop.is_set():
            try:
                _, writable, _ = __import__("select").select([], [destination], [], 0.2)
                if not writable:
                    continue
                view = view[os.write(destination, view):]
            except OSError as exc:
                if exc.errno in (errno.EIO, errno.EPIPE, errno.ECONNRESET, errno.EBADF):
                    return
                raise


def session(conn: socket.socket, container_id: str, attempt: int,
            queue: str, task: str, shutdown: threading.Event) -> None:
    if not valid_target(container_id, attempt, queue, task):
        return
    master, slave = pty.openpty()
    try:
        process = subprocess.Popen(
            ["docker", "exec", "-it", container_id, "bash"],
            stdin=slave, stdout=slave, stderr=slave, start_new_session=True,
            close_fds=True,
        )
    finally:
        os.close(slave)

    stop = threading.Event()
    up = threading.Thread(target=forward, args=(conn.fileno(), master, stop), daemon=True)
    down = threading.Thread(target=forward, args=(master, conn.fileno(), stop), daemon=True)
    up.start()
    down.start()
    try:
        while not shutdown.wait(0.25):
            if process.poll() is not None or not up.is_alive() or not down.is_alive():
                break
            # No automatic reconnection to an ID that has been replaced/relabelled.
            if not valid_target(container_id, attempt, queue, task):
                break
    finally:
        stop.set()
        try:
            conn.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        if process.poll() is None:
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                process.wait()
        up.join(timeout=1)
        down.join(timeout=1)
        os.close(master)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--container-id", required=True)
    parser.add_argument("--attempt", type=int, required=True)
    parser.add_argument("--queue", required=True)
    parser.add_argument("--task", required=True)
    parser.add_argument("--socket", required=True)
    args = parser.parse_args()
    if not ID_RE.fullmatch(args.container_id) or args.attempt < 1:
        parser.error("Full Docker ID and a positive attempt number required")
    if not valid_target(args.container_id, args.attempt, args.queue, args.task):
        parser.error("Target ID, runtime state or task labels did not match")

    sockpath = Path(args.socket)
    if not sockpath.parent.is_dir():
        parser.error("Socket directory must be created by the launcher")
    if sockpath.exists() or sockpath.is_symlink():
        parser.error("Socket path must not already exist")
    if sockpath.parent.stat().st_mode & 0o077:
        parser.error("Socket directory must be accessible only by its owner")
    shutdown = threading.Event()
    active = threading.BoundedSemaphore(MAX_SESSIONS)
    workers: list[threading.Thread] = []
    server = socket.socket(socket.AF_UNIX)

    def stop_handler(_signum, _frame):
        shutdown.set()
        try:
            server.close()
        except OSError:
            pass

    signal.signal(signal.SIGTERM, stop_handler)
    signal.signal(signal.SIGINT, stop_handler)
    server.bind(str(sockpath))
    os.chmod(sockpath, 0o600)
    server.listen(MAX_SESSIONS)
    server.settimeout(0.5)
    print("BROKER READY", flush=True)
    try:
        while not shutdown.is_set():
            try:
                conn, _ = server.accept()
            except socket.timeout:
                continue
            except OSError:
                if shutdown.is_set():
                    break
                raise
            if not active.acquire(blocking=False):
                conn.close()
                continue

            def work(client: socket.socket):
                try:
                    with client:
                        session(client, args.container_id, args.attempt,
                                args.queue, args.task, shutdown)
                finally:
                    active.release()

            thread = threading.Thread(target=work, args=(conn,), daemon=True)
            workers.append(thread)
            thread.start()
    finally:
        shutdown.set()
        server.close()
        for worker in workers:
            worker.join(timeout=3)
        try:
            sockpath.unlink()
        except FileNotFoundError:
            pass

if __name__ == "__main__":
    main()
