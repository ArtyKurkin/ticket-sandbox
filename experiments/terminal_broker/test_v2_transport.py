"""Real PTY + client process + broker protocol, with a simulated Docker stream.

Does not replace the separately gated real Docker/browser E2E.
"""
import fcntl
import json
import os
from pathlib import Path
import pty
import select
import signal
import socket
import struct
import subprocess
import sys
import tempfile
import termios
import threading
import time
import unittest
from unittest.mock import MagicMock, patch

from terminal.broker_v2 import Broker, Identity


def eventually(predicate, timeout=5):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(.02)
    raise AssertionError("Condition did not become true")


class PTYTransportTests(unittest.TestCase):
    def test_real_client_raw_bytes_resize_and_hangup_cleanup(self):
        with tempfile.TemporaryDirectory(prefix="tb2-", dir="/tmp") as folder:
            root = Path(folder)
            identity = Identity("a" * 64, 17, "l1", "task", "1a71d3e5-0ff3-48da-855b-e232359f46e8")
            api = MagicMock()
            attached, remote = socket.socketpair()
            api.exec_create.return_value = {"Id": "b" * 64}
            api.exec_start.return_value = attached
            broker = Broker(api, identity, root, root)
            (root / "client.json").write_text(json.dumps({"credential": broker.credential}))
            listener = socket.socket(socket.AF_UNIX)
            listener.bind(str(root / "broker.sock"))
            listener.listen(1)
            master, slave = pty.openpty()
            fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", 24, 80, 0, 0))
            process = subprocess.Popen([sys.executable, "-m", "terminal.broker_client", "--socket-dir", folder],
                stdin=slave, stdout=slave, stderr=slave, start_new_session=True)
            os.close(slave)
            worker = None
            try:
                conn, _ = listener.accept()
                with patch.object(broker, "valid", return_value=True), patch.object(broker, "authorized", return_value=True), \
                     patch.object(broker, "cleanup", return_value=True) as cleanup:
                    worker = threading.Thread(target=broker.session, args=(conn,))
                    worker.start()
                    eventually(lambda: api.exec_resize.call_count >= 1)
                    self.assertEqual(api.exec_resize.call_args.kwargs, {"height": 24, "width": 80})
                    # Ctrl+C must pass through as a byte, without killing the client.
                    os.write(master, b"hello\x03\x1b[A\x00")
                    remote.settimeout(3)
                    received = bytearray()
                    while len(received) < 10:
                        received.extend(remote.recv(100))
                    self.assertEqual(received, b"hello\x03\x1b[A\x00")
                    remote.sendall(b"REMOTE_OUTPUT\r\n")
                    ready, _, _ = select.select([master], [], [], 3)
                    self.assertTrue(ready)
                    self.assertIn(b"REMOTE_OUTPUT", os.read(master, 4096))
                    fcntl.ioctl(master, termios.TIOCSWINSZ, struct.pack("HHHH", 43, 132, 0, 0))
                    os.kill(process.pid, signal.SIGWINCH)
                    eventually(lambda: api.exec_resize.call_args.kwargs == {"height": 43, "width": 132})
                    self.assertIsNone(process.poll())
                    os.kill(process.pid, signal.SIGHUP)
                    process.wait(timeout=5)
                    worker.join(timeout=5)
                    self.assertFalse(worker.is_alive())
                    cleanup.assert_called_once()
                    self.assertEqual([p.name for p in root.glob("*.json")], ["client.json"])
                    conn.close()
            finally:
                if process.poll() is None:
                    process.kill()
                process.wait()
                broker.shutdown.set()
                if worker:
                    worker.join(timeout=5)
                os.close(master)
                listener.close()
                attached.close()
                remote.close()


if __name__ == "__main__":
    unittest.main()
