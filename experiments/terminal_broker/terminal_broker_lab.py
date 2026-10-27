"""Lab-only, single-target interactive Docker terminal broker."""

import argparse
import errno
import json
import os
import pty
import re
import selectors
import socket
import subprocess
from pathlib import Path

def inspect(container_id):
    result = subprocess.run(
        ["docker", "inspect", container_id],
        capture_output=True, text=True, check=True,
        timeout=5,
    )
    return json.loads(result.stdout)[0]

def valid_target(container_id, attempt):
    try:
        obj = inspect(container_id)
        labels = obj["Config"].get("Labels") or {}
        return (
            obj["Id"] == container_id
            and obj["State"]["Running"] is True
            and labels.get("ticket-sandbox.type") == "task"
            and labels.get("ticket-sandbox.attempt") == str(attempt)
        )
    except (OSError, ValueError, KeyError, subprocess.SubprocessError):
        return False

def serve_session(conn, container_id, attempt):
    if not valid_target(container_id, attempt):
        return

    master, slave = pty.openpty()
    try:
        process = subprocess.Popen(
            ["docker", "exec", "-it", container_id, "bash"],
            stdin=slave, stdout=slave, stderr=slave,
            close_fds=True,
        )
    finally:
        os.close(slave)

    conn.setblocking(False)
    os.set_blocking(master, False)

    selector = selectors.DefaultSelector()
    selector.register(conn, selectors.EVENT_READ)
    selector.register(master, selectors.EVENT_READ)

    try:
        while process.poll() is None:
            # Stop a session if its pinned container disappears.
            if not valid_target(container_id, attempt):
                break

            for key, _ in selector.select(timeout=0.5):
                source = key.fileobj
                try:
                    data = (
                        conn.recv(4096) if source is conn
                        else os.read(master, 4096)
                    )
                    if not data:
                        return

                    destination = master if source is conn else conn.fileno()
                    view = memoryview(data)
                    while view:
                        try:
                            count = os.write(destination, view)
                            view = view[count:]
                        except BlockingIOError:
                            import select
                            select.select([], [destination], [], 1)
                except OSError as error:
                    if error.errno in (errno.EIO, errno.EPIPE, errno.ECONNRESET):
                        return
                    raise
    finally:
        selector.close()
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
        os.close(master)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--container-id", required=True)
    parser.add_argument("--attempt", required=True, type=int)
    parser.add_argument("--socket", required=True)
    args = parser.parse_args()

    if not re.fullmatch(r"[a-f0-9]{64}", args.container_id):
        parser.error("Full Docker container ID required")

    if not valid_target(args.container_id, args.attempt):
        parser.error("Pinned target identity is invalid")

    path = Path(args.socket)
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(path.parent, 0o700)

    if path.exists():
        parser.error("Socket already exists")

    server = socket.socket(socket.AF_UNIX)
    server.bind(str(path))
    os.chmod(path, 0o600)
    server.listen(1)

    print("BROKER READY", flush=True)

    try:
        while True:
            conn, _ = server.accept()
            with conn:
                serve_session(conn, args.container_id, args.attempt)
    finally:
        server.close()
        path.unlink(missing_ok=True)

if __name__ == "__main__":
    main()
