"""Experimental per-attempt Unix-socket terminal broker.

Security boundary: socket file permissions and process isolation. Whoever can
connect to the socket gets a shell in the pinned task. Do not expose this socket
outside the dedicated terminal sidecar. Not production-ready: TTY resize and
lifecycle/revocation must be integrated into Django before rollout.
"""
from __future__ import annotations

import argparse
import errno
import fcntl
import json
import tempfile
import os
import pty
import re
import selectors
import signal
import socket
import stat
import subprocess
import threading
import secrets
import time
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


def remote_shell_pid(master: int, token: str, timeout: float = 5.0) -> int:
    # The trusted exec wrapper reports the remote PID before normal I/O starts.
    import select
    prefix = f'__TB_PID_{token}__='.encode()
    deadline = time.monotonic() + timeout
    buffer = bytearray()
    while time.monotonic() < deadline and len(buffer) < 4096:
        ready, _, _ = select.select([master], [], [], 0.2)
        if ready:
            chunk = os.read(master, 4096)
            if not chunk:
                break
            buffer.extend(chunk)
            for line in buffer.splitlines():
                if line.startswith(prefix):
                    raw = line[len(prefix):].strip()
                    if raw.isdigit() and int(raw) > 1:
                        return int(raw)
                    raise RuntimeError('Invalid remote PID')
    raise RuntimeError('Remote PID handshake timed out')


def _remote_pid_action(container_id: str, pid: int, token: str, action: str) -> int:
    """0=absent, 10=alive and owned, 11=identity mismatch, 12=unreadable, 13=signal sent."""
    script = (
        'pid=$1; token=$2; action=$3; '
        '[ -d "/proc/$pid" ] || exit 0; '
        '[ -r "/proc/$pid/environ" ] || exit 12; '
        'tr "\\000" "\\n" < "/proc/$pid/environ" | '
        'grep -Fxq "TB_SESSION_TOKEN=$token" || exit 11; '
        '[ "$action" = probe ] && exit 10; '
        'case "$action" in TERM|KILL) kill -s "$action" "$pid" || exit 12;; '
        '*) exit 12;; esac; '
        'exit 13'
    )
    result = subprocess.run(
        ['docker', 'exec', container_id, 'sh', '-c', script, 'sh',
         str(pid), token, action],
        check=False, capture_output=True, timeout=5,
    )
    return result.returncode


def cleanup_remote_shell(container_id: str, pid: int, token: str) -> bool:
    """TERM, verify disappearance, then identity-checked KILL and verify again.

    A successful kill(2) does NOT mean the remote process exited.
    Interactive bash may ignore SIGTERM. Return True only when /proc/PID is gone.
    Unknown/mismatched identity always fails closed and is never signalled.
    """
    if not ID_RE.fullmatch(container_id) or pid <= 1 or not re.fullmatch(r'[a-f0-9]{32}', token):
        return False
    try:
        for action in ('TERM', 'KILL'):
            state = _remote_pid_action(container_id, pid, token, 'probe')
            if state == 0:
                return True
            if state != 10:
                return False
            sent = _remote_pid_action(container_id, pid, token, action)
            if sent == 0:
                return True
            if sent != 13:
                return False
            for _ in range(10):
                time.sleep(0.1)
                state = _remote_pid_action(container_id, pid, token, 'probe')
                if state == 0:
                    return True
                if state != 10:
                    return False
        return False
    except (OSError, subprocess.SubprocessError):
        return False


def _state_path(state_dir: Path, token: str) -> Path:
    if not re.fullmatch(r"[a-f0-9]{32}", token):
        raise ValueError("Invalid session token")
    return state_dir / (token + ".json")


def save_session(state_dir: Path, container_id: str, pid: int, token: str) -> None:
    """Persist the pinned exec identity before exposing terminal I/O."""
    if not ID_RE.fullmatch(container_id) or pid <= 1:
        raise ValueError("Invalid pinned exec identity")
    path = _state_path(state_dir, token)
    content = json.dumps({"container_id": container_id, "pid": pid, "token": token}).encode()
    fd, temp = tempfile.mkstemp(prefix=".session-", dir=state_dir)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "wb") as output:
            output.write(content)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temp, path)
        dir_fd = os.open(state_dir, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def recover_sessions(state_dir: Path, container_id: str) -> bool:
    """Recover only positively identified processes; retain unresolved records."""
    all_clean = True
    for path in sorted(state_dir.glob("*.json")):
        try:
            if path.is_symlink():
                raise ValueError("Symlink record")
            record = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(record, dict):
                raise ValueError("Invalid record")
            if record.get("container_id") != container_id:
                raise ValueError("Foreign container ID")
            token = record["token"]
            pid = record["pid"]
            if _state_path(state_dir, token) != path or type(pid) is not int or pid <= 1:
                raise ValueError("Invalid session identity")
            if not cleanup_remote_shell(container_id, pid, token):
                raise RuntimeError("Remote process cleanup unconfirmed")
            path.unlink()
            print(f"SESSION RECOVERED pid={pid}", flush=True)
        except (OSError, KeyError, TypeError, ValueError, RuntimeError) as exc:
            all_clean = False
            print(f"WARNING: recovery blocked for {path.name}: {exc}", flush=True)
    return all_clean


def peer_disconnected(conn: socket.socket) -> bool:
    """Detect EOF even if forwarding workers have not terminated yet."""
    try:
        return conn.recv(1, socket.MSG_PEEK | socket.MSG_DONTWAIT) == b""
    except BlockingIOError:
        return False
    except OSError:
        return True


def session(conn: socket.socket, container_id: str, attempt: int,
            queue: str, task: str, shutdown: threading.Event, state_dir: Path) -> None:
    if not valid_target(container_id, attempt, queue, task):
        return
    token = secrets.token_hex(16)
    print(f"SESSION OPEN token={token[:8]}", flush=True)
    master, slave = pty.openpty()
    wrapper = f'printf "__TB_PID_{token}__=%s\\n" "$$"; exec bash'
    try:
        process = subprocess.Popen(
            ['docker', 'exec', '-it', '-e', f'TB_SESSION_TOKEN={token}',
             container_id, 'sh', '-c', wrapper],
            stdin=slave, stdout=slave, stderr=slave, start_new_session=True,
            close_fds=True,
        )
    finally:
        os.close(slave)
    try:
        remote_pid = remote_shell_pid(master, token)
    except (OSError, RuntimeError):
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
        os.close(master)
        return

    try:
        save_session(state_dir, container_id, remote_pid, token)
    except (OSError, ValueError):
        cleanup_remote_shell(container_id, remote_pid, token)
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        process.wait(timeout=3)
        os.close(master)
        return

    stop = threading.Event()
    up = threading.Thread(target=forward, args=(conn.fileno(), master, stop), daemon=True)
    down = threading.Thread(target=forward, args=(master, conn.fileno(), stop), daemon=True)
    up.start()
    down.start()
    try:
        while not shutdown.wait(0.25):
            if peer_disconnected(conn):
                print(f"SESSION EOF token={token[:8]}", flush=True)
                break
            if process.poll() is not None or not up.is_alive() or not down.is_alive():
                break
            # No automatic reconnection to an ID that has been replaced/relabelled.
            if not valid_target(container_id, attempt, queue, task):
                break
    finally:
        stop.set()
        # Terminate the tracked remote process *before* stopping docker exec.
        cleaned = cleanup_remote_shell(container_id, remote_pid, token)
        print(f"SESSION CLEANUP pid={remote_pid} exited={cleaned}", flush=True)
        if cleaned:
            try:
                _state_path(state_dir, token).unlink(missing_ok=True)
            except OSError:
                print("WARNING: could not remove session record", flush=True)
        else:
            print(f"WARNING: remote shell cleanup unconfirmed for PID {remote_pid}", flush=True)
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



def prepare_socket_path(sockpath: Path) -> bool:
    """Remove only a demonstrably dead, self-owned Unix socket.

    Caller MUST hold the exclusive broker flock before calling. If another
    listener accepts connections (or the state is ambiguous), refuse startup.
    No normal file, symlink or foreign-owned socket is ever removed.
    Returns True if it removed a stale socket.
    """
    try:
        info = sockpath.lstat()
    except FileNotFoundError:
        return False
    if not stat.S_ISSOCK(info.st_mode) or info.st_uid != os.geteuid():
        raise RuntimeError("Socket path is not an owned Unix socket")
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as probe:
        probe.settimeout(1.0)
        try:
            probe.connect(str(sockpath))
        except OSError as exc:
            if isinstance(exc, ConnectionRefusedError) or exc.errno == errno.ECONNREFUSED:
                # Confirm this is still the same filesystem object we probed.
                now = sockpath.lstat()
                if ((now.st_dev, now.st_ino, now.st_uid, now.st_mode) !=
                        (info.st_dev, info.st_ino, info.st_uid, info.st_mode)):
                    raise RuntimeError("Socket changed while checking liveness")
                sockpath.unlink()
                print("STALE SOCKET REMOVED", flush=True)
                return True
            raise RuntimeError(f"Socket liveness not established: {exc}") from exc
    raise RuntimeError("Socket already has an active listener")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--container-id", required=True)
    parser.add_argument("--attempt", type=int, required=True)
    parser.add_argument("--queue", required=True)
    parser.add_argument("--task", required=True)
    parser.add_argument("--socket", required=True)
    parser.add_argument("--state-dir", required=True)
    args = parser.parse_args()
    if not ID_RE.fullmatch(args.container_id) or args.attempt < 1:
        parser.error("Full Docker ID and a positive attempt number required")
    if not valid_target(args.container_id, args.attempt, args.queue, args.task):
        parser.error("Target ID, runtime state or task labels did not match")

    sockpath = Path(args.socket)
    if not sockpath.parent.is_dir():
        parser.error("Socket directory must be created by the launcher")
    if sockpath.parent.stat().st_mode & 0o077:
        parser.error("Socket directory must be accessible only by its owner")
    state_dir = Path(args.state_dir)
    if (not state_dir.is_dir() or state_dir.is_symlink()
            or state_dir.stat().st_mode & 0o077):
        parser.error("Private state directory (mode 0700) required")
    lock_fd = os.open(state_dir / ".broker.lock", os.O_CREAT | os.O_RDWR, 0o600)
    try:
        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        parser.error("Another broker owns this state directory")
    if not recover_sessions(state_dir, args.container_id):
        parser.error("Unresolved orphan sessions; inspect records before restarting")
    # Lock is held and remote orphan sessions are reconciled before reuse.
    try:
        prepare_socket_path(sockpath)
    except (OSError, RuntimeError) as exc:
        parser.error(str(exc))
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
                                args.queue, args.task, shutdown, state_dir)
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
