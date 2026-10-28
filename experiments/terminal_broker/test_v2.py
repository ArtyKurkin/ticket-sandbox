import dataclasses
import json
import io
import socket
import tempfile
import threading
import time
import unittest
import signal
from pathlib import Path
from unittest.mock import MagicMock, patch

from terminal.broker_v2 import Broker, Identity, atomic_json, CLEANUP
from terminal.protocol import HEADER, dimensions, receive, send

IDENTITY = Identity("a" * 64, 17, "l1", "task", "1a71d3e5-0ff3-48da-855b-e232359f46e8")


class IdentityTests(unittest.TestCase):
    def target(self):
        return {"Id": IDENTITY.container_id, "State": {"Running": True}, "Config": {"Labels": {
            "ticket-sandbox.type": "task", "ticket-sandbox.attempt": "17", "ticket-sandbox.queue": "l1",
            "ticket-sandbox.task": "task", "ticket-sandbox.generation": IDENTITY.generation}}}

    def test_every_identity_component_is_required(self):
        self.assertTrue(IDENTITY.matches(self.target()))
        for key in ("type", "attempt", "queue", "task", "generation"):
            obj = self.target()
            obj["Config"]["Labels"]["ticket-sandbox." + key] = "foreign"
            self.assertFalse(IDENTITY.matches(obj), key)
        obj = self.target()
        obj["Id"] = "b" * 64
        self.assertFalse(IDENTITY.matches(obj))
        obj = self.target()
        obj["State"]["Running"] = False
        self.assertFalse(IDENTITY.matches(obj))

    def test_untrusted_identity_rejected(self):
        for changes in ({"container_id": "short"}, {"attempt": True}, {"generation": "bad"},
                        {"queue": "../l1"}, {"task": "task;id"}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                dataclasses.replace(IDENTITY, **changes)


class ProtocolTests(unittest.TestCase):
    def test_fragmented_binary_input_is_lossless(self):
        left, right = socket.socketpair()
        payload = bytes(range(256)) * 10
        def writer():
            frame = HEADER.pack(b"I", len(payload)) + payload
            for start in range(0, len(frame), 3):
                right.sendall(frame[start:start + 3])
        thread = threading.Thread(target=writer)
        try:
            thread.start()
            self.assertEqual(receive(left, time.monotonic() + 3), (b"I", payload))
        finally:
            thread.join()
            left.close()
            right.close()

    def test_oversized_frame_rejected_before_reading_payload(self):
        left, right = socket.socketpair()
        try:
            right.sendall(HEADER.pack(b"I", 16385))
            with self.assertRaises(ValueError):
                receive(left)
        finally:
            left.close()
            right.close()

    def test_invalid_resize_and_valid_size(self):
        self.assertEqual(dimensions(b"[48,160]"), [48, 160])
        for value in (b"[0,80]", b"[24,1001]", b"[true,80]", b"{}", b"[1]", b"[1,2,3]"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                dimensions(value)

    def test_partial_frame_deadline(self):
        left, right = socket.socketpair()
        try:
            right.sendall(b"I")
            with self.assertRaises(TimeoutError):
                receive(left, time.monotonic() + .05)
        finally:
            left.close()
            right.close()


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)
        self.api = MagicMock()
        self.broker = Broker(self.api, IDENTITY, self.path, self.path / "socket")
        self.token = "b" * 32
        self.exec_id = "c" * 64

    def test_journal_retained_on_unconfirmed_cleanup_then_recovered(self):
        self.broker.save(self.token, self.exec_id)
        path = self.path / (self.token + ".json")
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        with patch.object(self.broker, "cleanup", return_value=False):
            self.assertFalse(self.broker.recover())
        self.assertTrue(path.exists())
        with patch.object(self.broker, "cleanup", return_value=True) as cleanup:
            self.assertTrue(self.broker.recover())
        cleanup.assert_called_once_with(self.token, self.exec_id)
        self.assertFalse(path.exists())

    def test_foreign_or_malformed_record_never_signalled(self):
        for change in ({"identity": {}}, {"exec_id": "../bad"}, {"token": "x"}, {"version": 1}):
            self.broker.save(self.token, self.exec_id)
            path = self.path / (self.token + ".json")
            record = json.loads(path.read_text())
            record.update(change)
            atomic_json(path, record)
            with patch.object(self.broker, "cleanup") as cleanup:
                self.assertFalse(self.broker.recover())
            cleanup.assert_not_called()

    def test_exec_from_foreign_container_never_signalled(self):
        self.api.exec_inspect.return_value = {"ContainerID": "d" * 64, "Running": True}
        self.assertFalse(self.broker.cleanup(self.token, self.exec_id))
        self.api.exec_create.assert_not_called()

    def test_cleanup_waits_for_docker_to_publish_process_exit(self):
        self.broker.save(self.token, self.exec_id, {"pid":123, "start":456})
        self.api.exec_inspect.side_effect = [
            {"ContainerID": IDENTITY.container_id, "Running": True},
            {"Running": True, "ExitCode": None}, {"Running": False, "ExitCode": 0},
            {"Running": True}, {"Running": False},
        ]
        self.api.inspect_container.return_value = IdentityTests().target()
        self.api.exec_create.return_value = {"Id": "d" * 64}
        with patch("terminal.broker_v2.time.sleep") as sleep:
            self.assertTrue(self.broker.cleanup(self.token, self.exec_id))
        self.assertEqual(sleep.call_count, 2)

    def test_no_authorization_service_fails_closed(self):
        self.assertFalse(self.broker.authorized())

    def test_exact_process_stat_failure_is_not_silently_ignored(self):
        def run(state):
            def read(path, mode="r"):
                raise PermissionError("unreadable exact process")
            with patch("os.listdir", return_value=["123"]), patch("os.getpid", return_value=999), \
                 patch("os.pidfd_open", return_value=4, create=True), patch("os.close"), \
                 patch("builtins.open", side_effect=read), patch("sys.argv", ["helper", "123", "456"]), \
                 patch("select.select", return_value=([4] if state == "Z" else [], [], [])), \
                 patch("signal.pidfd_send_signal", create=True) as kill:
                try:
                    exec(CLEANUP, {})
                finally:
                    kill.assert_not_called()
        with self.assertRaises(PermissionError):
            run("S")

    def test_client_cannot_supply_container_or_command(self):
        for extra in ({"container_id": IDENTITY.container_id}, {"command": ["sh"]}, {"credential": "wrong"}):
            left, right = socket.socketpair()
            try:
                obj = {"version": 2, "credential": self.broker.credential, **extra}
                send(right, b"H", json.dumps(obj).encode())
                with self.assertRaises(ValueError):
                    self.broker.authenticate(left)
                self.api.exec_create.assert_not_called()
            finally:
                left.close()
                right.close()

    def test_reused_pid_is_never_signalled_and_no_environment_is_scanned(self):
        stat = '123 (bash) S ' + '0 ' * 18 + '789'
        with patch('sys.argv', ['helper', '123', '456']), \
             patch('os.pidfd_open', return_value=4, create=True), patch('os.close'), \
             patch('builtins.open', return_value=io.StringIO(stat)), \
             patch('os.listdir') as scan, patch('signal.pidfd_send_signal', create=True) as kill:
            with self.assertRaises(SystemExit) as stopped:
                exec(CLEANUP, {})
            self.assertEqual(stopped.exception.code, 0)
            scan.assert_not_called()
            kill.assert_not_called()

    def test_exact_pidfd_is_signalled_and_exit_confirmed(self):
        stat = '123 (bash) S ' + '0 ' * 18 + '456'
        with patch('sys.argv', ['helper', '123', '456']), \
             patch('os.pidfd_open', return_value=4, create=True), patch('os.close'), \
             patch('builtins.open', return_value=io.StringIO(stat)), \
             patch('select.select', side_effect=[([], [], []), ([4], [], [])]), \
             patch('signal.pidfd_send_signal', create=True) as kill:
            with self.assertRaises(SystemExit) as stopped:
                exec(CLEANUP, {})
            self.assertEqual(stopped.exception.code, 0)
            kill.assert_called_once_with(4, signal.SIGHUP)

    def test_pid_one_rejected_before_opening_pidfd(self):
        with patch('sys.argv', ['helper', '1', '456']), patch('os.pidfd_open', create=True) as open_pid:
            with self.assertRaises(AssertionError):
                exec(CLEANUP, {})
            open_pid.assert_not_called()


if __name__ == "__main__":
    unittest.main()
