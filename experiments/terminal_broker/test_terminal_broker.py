"""Offline unit tests: python -m unittest discover -s experiments/terminal_broker -p 'test_*.py'"""
import json
import unittest
from unittest.mock import patch

from terminal_broker import valid_target


class TargetIdentityTests(unittest.TestCase):
    def setUp(self):
        self.container_id = "a" * 64
        self.payload = {
            "Id": self.container_id,
            "State": {"Running": True},
            "Config": {"Labels": {
                "ticket-sandbox.type": "task",
                "ticket-sandbox.attempt": "17",
                "ticket-sandbox.queue": "l1",
                "ticket-sandbox.task": "service-bind-localhost",
            }},
        }

    def allowed(self, **changes):
        payload = json.loads(json.dumps(self.payload))
        for k, v in changes.items():
            payload[k] = v
        with patch("terminal_broker.inspect_target", return_value=payload):
            return valid_target(self.container_id, 17, "l1", "service-bind-localhost")

    def test_matching_target(self):
        self.assertTrue(self.allowed())

    def test_replaced_id(self):
        self.assertFalse(self.allowed(Id="b" * 64))

    def test_stopped_target(self):
        self.assertFalse(self.allowed(State={"Running": False}))

    def test_wrong_attempt(self):
        self.payload["Config"]["Labels"]["ticket-sandbox.attempt"] = "18"
        self.assertFalse(self.allowed())

    def test_wrong_queue(self):
        self.payload["Config"]["Labels"]["ticket-sandbox.queue"] = "candidate"
        self.assertFalse(self.allowed())

    def test_wrong_task(self):
        self.payload["Config"]["Labels"]["ticket-sandbox.task"] = "other"
        self.assertFalse(self.allowed())

    def test_no_labels(self):
        self.assertFalse(self.allowed(Config={"Labels": {}}))

    def test_docker_failure_closed(self):
        with patch("terminal_broker.inspect_target", side_effect=ValueError("failed")):
            self.assertFalse(valid_target(self.container_id, 17, "l1", "service-bind-localhost"))


if __name__ == "__main__":
    unittest.main()

class RemoteCleanupTests(unittest.TestCase):
    def test_rejects_unsafe_pid(self):
        from terminal_broker import cleanup_remote_shell
        with patch('terminal_broker.subprocess.run') as run:
            self.assertFalse(cleanup_remote_shell('a' * 64, 1, 'a' * 32))
            run.assert_not_called()

    def test_term_then_disappearance(self):
        from terminal_broker import cleanup_remote_shell
        with patch('terminal_broker._remote_pid_action', side_effect=[10, 13, 10, 0]) as act, patch('terminal_broker.time.sleep'):
            self.assertTrue(cleanup_remote_shell('a' * 64, 29, 'b' * 32))
        self.assertEqual([x.args[-1] for x in act.call_args_list], ['probe', 'TERM', 'probe', 'probe'])

    def test_term_ignored_then_kill_disappearance(self):
        from terminal_broker import cleanup_remote_shell
        with patch('terminal_broker._remote_pid_action', side_effect=[10, 13] + [10] * 10 + [10, 13, 0]) as act, patch('terminal_broker.time.sleep'):
            self.assertTrue(cleanup_remote_shell('a' * 64, 29, 'b' * 32))
        self.assertIn('KILL', [x.args[-1] for x in act.call_args_list])

    def test_signal_success_not_equivalent_to_exited(self):
        from terminal_broker import cleanup_remote_shell
        with patch('terminal_broker._remote_pid_action', side_effect=[10, 13] + [10] * 10 + [10, 13] + [10] * 10), patch('terminal_broker.time.sleep'):
            self.assertFalse(cleanup_remote_shell('a' * 64, 29, 'b' * 32))

    def test_identity_mismatch_does_not_signal(self):
        from terminal_broker import cleanup_remote_shell
        with patch('terminal_broker._remote_pid_action', return_value=11) as act:
            self.assertFalse(cleanup_remote_shell('a' * 64, 29, 'b' * 32))
        self.assertEqual(act.call_count, 1)

    def test_docker_failure_fails_closed(self):
        from terminal_broker import cleanup_remote_shell
        with patch('terminal_broker._remote_pid_action', side_effect=OSError('docker unavailable')):
            self.assertFalse(cleanup_remote_shell('a' * 64, 29, 'b' * 32))

    def test_remote_pid_handshake(self):
        import os
        from terminal_broker import remote_shell_pid
        r, w = os.pipe()
        try:
            os.write(w, b'__TB_PID_' + b'a' * 32 + b'__=49\r\n')
            self.assertEqual(remote_shell_pid(r, 'a' * 32), 49)
        finally:
            os.close(r)
            os.close(w)


class PeerDisconnectTests(unittest.TestCase):
    def test_open_peer(self):
        import socket
        from terminal_broker import peer_disconnected
        left, right = socket.socketpair()
        try:
            self.assertFalse(peer_disconnected(left))
            right.sendall(b"x")
            self.assertFalse(peer_disconnected(left))
            self.assertEqual(left.recv(1), b"x")
        finally:
            left.close(); right.close()

    def test_closed_peer(self):
        import socket
        from terminal_broker import peer_disconnected
        left, right = socket.socketpair()
        try:
            right.close()
            self.assertTrue(peer_disconnected(left))
        finally:
            left.close()
