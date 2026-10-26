"""Small end-to-end threat suite: only owned loopback sockets and local Python."""
from contextlib import contextmanager
from dataclasses import replace
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
from pathlib import Path
import socket
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
from uuid import uuid4

from . import local, verifier


@contextmanager
def service(control, body=verifier.BODY, status=200, delay=0, port=None, raw=None):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            time.sleep(delay)
            try:
                if raw is not None:
                    self.connection.sendall(raw)
                    return
                self.send_response(status)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def log_message(self, *args):
            pass

    class Server(HTTPServer):
        allow_reuse_address = True

    # Binding failure is an explicit test error: never touch an existing service.
    port = control.snapshot(17).port if port is None else port
    server = Server(("127.0.0.1", port), Handler)
    thread = threading.Thread(target=server.serve_forever,
                              kwargs={"poll_interval": 0.01})
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
        if thread.is_alive():
            raise RuntimeError("owned fixture did not stop")


def fixture():
    control = local.LocalControl()
    with socket.socket() as reservation:
        reservation.bind(("127.0.0.1", 0))
        port = reservation.getsockname()[1]
    binding = local.LocalBinding(17, str(uuid4()), str(uuid4()), port)
    control.assign(binding)
    return control, binding


class MVPThreats(unittest.TestCase):
    def test_live_http_is_independent_but_never_full_task_pass(self):
        control, binding = fixture()
        with service(control):
            result = local.check(control, binding.attempt_id)
        self.assertEqual(result["http"], "matched")
        self.assertEqual(result["attempt_binding"], "matched_local_control_record")
        self.assertEqual(result["task_verdict"], "unknown")
        self.assertEqual(result["container_identity"], "unverified")
        self.assertFalse(result["academic_pass"])
        self.assertLess(len(json.dumps(result)), 2048)

    def test_replaced_check_sh_and_spoofed_tools_are_not_executed(self):
        control, binding = fixture()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            marker = root / "executed"
            # Both exit-0 and command-output spoofing are inert files, not run.
            for name in ("check.sh", "curl", "ip", "python"):
                file = root / name
                file.write_text(f"#!/bin/sh\ntouch '{marker}'\necho '{{\"passed\":true}}'\nexit 0\n")
                file.chmod(0o755)
            with patch.dict(os.environ, {"PATH": directory, "PYTHONPATH": directory}), service(control, body=b"wrong"):
                result = local.check(control, binding.attempt_id)
            self.assertFalse(marker.exists())
            self.assertEqual(result["http"], "mismatch")
            self.assertEqual(result["task_verdict"], "failed")

    def test_service_down_is_unknown_not_zero_exit_success(self):
        control, binding = fixture()
        # Reserve the port without listening; ensure there is no unrelated target.
        with socket.socket() as guard:
            guard.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            guard.bind(("127.0.0.1", binding.port))
            result = local.check(control, binding.attempt_id)
        self.assertEqual(result["http"], "unknown")
        # OS may refuse immediately or time out for a bound non-listening socket.
        self.assertIn(result["reason"], ("endpoint_unavailable", "timeout"))
        self.assertEqual(result["task_verdict"], "unknown")

    def test_loopback_bind_with_http_200_is_not_credited_as_correct_bind(self):
        control, binding = fixture()
        with service(control) as server:
            self.assertEqual(server.socket.getsockname(), ("127.0.0.1", binding.port))
            result = local.check(control, binding.attempt_id)
        self.assertEqual(result["http"], "matched")
        self.assertEqual(result["bind_address_and_port"], "unverified")
        self.assertEqual(result["service_process_state"], "unverified")
        self.assertFalse(result["academic_pass"])

    def test_wrong_body_status_or_prepared_result_json_do_not_match(self):
        control, binding = fixture()
        for body, status in ((b"wrong", 200), (verifier.BODY, 503),
                             (b'{"result":"passed","http":"matched"}', 200)):
            with self.subTest(status=status, body=body):
                with service(control, body, status):
                    result = local.check(control, binding.attempt_id)
                self.assertEqual(result["http"], "mismatch")
                self.assertFalse(result["academic_pass"])

    def test_wrong_port_is_not_discovered_or_used(self):
        control, binding = fixture()
        with socket.socket() as guard:
            guard.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            guard.bind(("127.0.0.1", binding.port))
            with service(control, port=0) as server:
                self.assertNotEqual(server.server_port, binding.port)
                result = local.check(control, binding.attempt_id)
        self.assertEqual(result["http"], "unknown")

    def test_previous_attempt_generation_and_run_results_are_rejected(self):
        control, binding = fixture()
        recorded = []
        read = local._read_worker

        def remember(request, deadline):
            raw = read(request, deadline)
            recorded.append((request, raw))
            return raw

        with service(control), patch.object(local, "_read_worker", remember):
            self.assertEqual(local.check(control, 17)["http"], "matched")
        request, raw = recorded[0]
        for key, value in (("attempt_id", 18), ("environment_id", str(uuid4())),
                           ("runtime_id", str(uuid4())), ("run_id", str(uuid4()))):
            with self.subTest(key=key):
                altered = dict(request, **{key: value})
                with self.assertRaisesRegex(ValueError, "stale_result"):
                    local._validate_result(raw, altered)
        with patch.object(local, "_read_worker", return_value=raw):
            replay = local.check(control, 17)
        self.assertEqual(replay["http"], "unknown")

    def test_checker_or_control_unavailable_is_unknown(self):
        control, _ = fixture()
        with patch.object(local, "WORKER", Path("/nonexistent/tc-mvp-verifier.py")):
            self.assertEqual(local.check(control, 17)["http"], "unknown")
        self.assertEqual(local.check(local.LocalControl(), 17)["http"], "unknown")

    def test_timeout_and_slow_header_have_total_deadline(self):
        control, _ = fixture()
        started = time.monotonic()
        with service(control, delay=0.9):
            result = local.check(control, 17)
        self.assertEqual(result["reason"], "timeout")
        self.assertLess(time.monotonic() - started, 2.5)
        with service(control, raw=b"HTTP/1.0 200 OK\r\nContent-Length: 33\r\n"):
            self.assertEqual(local.check(control, 17)["http"], "unknown")
        spawned = []
        popen = local.subprocess.Popen

        def remember(*args, **kwargs):
            child = popen(*args, **kwargs)
            spawned.append(child)
            return child

        with service(control, delay=0.9), patch.object(local, "TOTAL_SECONDS", 0.1), \
                patch.object(local.subprocess, "Popen", remember):
            self.assertEqual(local.check(control, 17)["reason"], "timeout")
        self.assertEqual(len(spawned), 1)
        self.assertIsNotNone(spawned[0].poll())

    def test_http_cannot_supply_control_commands_or_redirect_probe(self):
        control, binding = fixture()
        raw = (b"HTTP/1.0 302 Found\r\nLocation: http://127.0.0.1:1/control\r\n"
               b"Content-Length: 0\r\n\r\n")
        with service(control, raw=raw):
            result = local.check(control, 17)
        self.assertEqual(result["http"], "mismatch")
        self.assertEqual(control.snapshot(17), binding)
        # Only host-owned endpoint metadata; no operation/URL/argv/command fields.
        request = dict(local.asdict(binding), task=verifier.TASK, run_id=str(uuid4()))
        for key, value in (("command", "exit 0"), ("argv", ["exit", "0"]),
                           ("url", "http://127.0.0.1/control")):
            with self.subTest(key=key), self.assertRaises(ValueError):
                verifier.parse_request(json.dumps(dict(request, **{key: value})).encode())

    def test_environment_change_during_check_discards_http_match(self):
        control, binding = fixture()
        read = local._read_worker

        def reset(request, deadline):
            raw = read(request, deadline)
            control.assign(replace(binding, environment_id=str(uuid4()), runtime_id=str(uuid4())))
            return raw

        with service(control), patch.object(local, "_read_worker", reset):
            result = local.check(control, 17)
        self.assertEqual(result["http"], "unknown")
        self.assertEqual(result["reason"], "attempt_changed")

    def test_change_after_check_requires_new_observation(self):
        control, _ = fixture()
        with service(control):
            old = local.check(control, 17)
        self.assertEqual(old["http"], "matched")
        self.assertFalse(old["continuous_verification"])
        self.assertEqual(old["task_verdict"], "unknown")
        with socket.socket() as guard:
            guard.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            guard.bind(("127.0.0.1", control.snapshot(17).port))
            fresh = local.check(control, 17)
        self.assertEqual(fresh["http"], "unknown")
        self.assertNotEqual(old["run_id"], fresh["run_id"])

    def test_malformed_or_oversized_http_is_bounded(self):
        control, _ = fixture()
        cases = (b"X" * 5000,
                 b"HTTP/1.0 200 OK\r\nContent-Length: 999\r\n\r\n",
                 b"HTTP/1.0 200 OK\r\nContent-Length: 0\r\nContent-Length: 0\r\n\r\n",
                 b"HTTP/1.0 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n")
        for raw in cases:
            with self.subTest(raw=raw[:60]):
                with service(control, raw=raw):
                    result = local.check(control, 17)
                self.assertEqual(result["http"], "unknown")


if __name__ == "__main__":
    unittest.main()
