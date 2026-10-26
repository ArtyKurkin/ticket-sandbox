"""Host-owned local control fixture and external-process supervisor.

No request listener or result-upload API; no production integration. LocalControl
is trusted in-memory demo configuration, NOT an implemented Docker observer.
"""
from dataclasses import asdict, dataclass
import json
import os
from pathlib import Path
import selectors
import subprocess
import sys
import time
from uuid import uuid4

from . import verifier

WORKER = Path(__file__).with_name("verifier.py").resolve()
TOTAL_SECONDS = 1.5
REAP_SECONDS = 0.5


@dataclass(frozen=True)
class LocalBinding:
    attempt_id: int
    environment_id: str
    runtime_id: str
    port: int
    ip: str = "127.0.0.1"


class LocalControl:
    """Only the trusted test/operator calls assign. Never exposed over HTTP."""
    def __init__(self):
        self._targets = {}

    def assign(self, binding):
        if type(binding) is not LocalBinding:
            raise ValueError("local_binding_required")
        request = dict(asdict(binding), task=verifier.TASK, run_id=str(uuid4()))
        verifier.parse_request(json.dumps(request).encode())
        self._targets[binding.attempt_id] = binding

    def snapshot(self, attempt_id):
        return self._targets[attempt_id]


def _read_worker(request, deadline):
    """Standard pipes/Popen only; cap output while reading, then reap our child."""
    child = None
    try:
        child = subprocess.Popen(
            [sys.executable, "-I", "-S", str(WORKER)],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            env={"LANG": "C", "LC_ALL": "C", "PYTHONDONTWRITEBYTECODE": "1"},
            close_fds=True,
        )
        with child.stdin:
            child.stdin.write(json.dumps(request, separators=(",", ":")).encode())
        with child.stdout, selectors.DefaultSelector() as selector:
            selector.register(child.stdout, selectors.EVENT_READ)
            output = bytearray()
            while True:
                left = deadline - time.monotonic()
                if left <= 0:
                    raise TimeoutError
                if not selector.select(left):
                    raise TimeoutError
                chunk = os.read(child.stdout.fileno(), verifier.RESULT_LIMIT + 1 - len(output))
                if not chunk:
                    break
                output.extend(chunk)
                if len(output) > verifier.RESULT_LIMIT:
                    raise ValueError("result_bounds")
            left = deadline - time.monotonic()
            if left <= 0:
                raise TimeoutError
            if child.wait(timeout=left) != 0:
                raise ValueError("worker_exit")
            return bytes(output)
    finally:
        if child is not None:
            if child.poll() is None:
                child.kill()
            child.wait(timeout=REAP_SECONDS)


def _validate_result(raw, request):
    if type(raw) is not bytes or len(raw) > verifier.RESULT_LIMIT:
        raise ValueError("result_bounds")
    # Only called on the just-created worker's private stdout, never HTTP input.
    obj = json.loads(raw)
    if type(obj) is not dict or set(obj) != {"binding", "http", "reason"}:
        raise ValueError("result_schema")
    if obj["binding"] != request:
        raise ValueError("stale_result")
    verifier.parse_request(json.dumps(obj["binding"]).encode())
    allowed = {
        ("matched", "http_match"), ("mismatch", "http_mismatch"),
        *(("unknown", reason) for reason in (
            "incomplete_http", "http_bounds", "http_schema", "timeout", "endpoint_unavailable")),
    }
    if (obj["http"], obj["reason"]) not in allowed:
        raise ValueError("result_schema")
    return obj["http"], obj["reason"]


def check(control, attempt_id):
    """Run a fresh observation. No API accepts a supplied result, URL, or code."""
    started = time.monotonic()
    run_id = str(uuid4())
    request = None
    state, reason = "unknown", "control_unavailable"
    binding_status = "unverified"
    try:
        before = control.snapshot(attempt_id)
        request = dict(asdict(before), task=verifier.TASK, run_id=run_id)
        verifier.parse_request(json.dumps(request).encode())
        raw = _read_worker(request, started + TOTAL_SECONDS)
        state, reason = _validate_result(raw, request)
        if control.snapshot(attempt_id) != before:
            state, reason = "unknown", "attempt_changed"
        else:
            binding_status = "matched_local_control_record"
        if time.monotonic() - started > TOTAL_SECONDS:
            state, reason = "unknown", "timeout"
    except (TimeoutError, subprocess.TimeoutExpired):
        state, reason = "unknown", "timeout"
    except Exception:
        state, reason = "unknown", "checker_or_control_unavailable"
    return {
        "schema": 1, "task": verifier.TASK, "attempt_id": attempt_id,
        "run_id": run_id, "environment_id": request["environment_id"] if request else None,
        "runtime_id": request["runtime_id"] if request else None,
        "http": state, "reason": reason, "attempt_binding": binding_status,
        "service_process_state": "unverified", "bind_address_and_port": "unverified",
        "container_identity": "unverified", "network_isolation": "unverified",
        "task_verdict": "failed" if state == "mismatch" else "unknown",
        "academic_pass": False, "continuous_verification": False,
    }
