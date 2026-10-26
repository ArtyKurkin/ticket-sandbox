"""Fixed image entry: one HTTP probe; no Docker client, listener, or task exec."""
import ipaddress
import json
import os
from pathlib import Path
import re
import runpy
import sys
from uuid import UUID

POLICY = "tc-mvp-docker-http-v1"
REQUEST_LIMIT = 4096
STDOUT_LIMIT = 4096
STDERR_LIMIT = 1024
RUNTIME_KEYS = {
    "attempt_id", "user_id", "environment_uuid", "run_id", "ordinal",
    "container_id", "daemon_id", "started_at", "restart_count", "pid",
    "network_id", "endpoint_id", "ip",
}
REASONS = {
    ("matched", "http_match"), ("mismatch", "http_mismatch"),
    *(("unknown", code) for code in (
        "incomplete_http", "http_bounds", "http_schema", "timeout", "endpoint_unavailable")),
}


def decode(raw, limit):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate_key")
            result[key] = value
        return result
    if type(raw) is not bytes or len(raw) > limit:
        raise ValueError("wire_bounds")
    return json.loads(raw, object_pairs_hook=unique)


def uuid(value):
    if type(value) is not str or str(UUID(value)) != value:
        raise ValueError("uuid")


def full_id(value):
    return type(value) is str and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def validate(request):
    if type(request) is not dict or set(request) != {"policy", "execution_uuid", "runtime"}:
        raise ValueError("request_schema")
    if request["policy"] != POLICY:
        raise ValueError("policy")
    uuid(request["execution_uuid"])
    runtime = request["runtime"]
    if type(runtime) is not dict or set(runtime) != RUNTIME_KEYS:
        raise ValueError("runtime_schema")
    for key in ("attempt_id", "user_id", "ordinal", "pid"):
        if type(runtime[key]) is not int or not 0 < runtime[key] < 2**63:
            raise ValueError("runtime_integer")
    if type(runtime["restart_count"]) is not int or not 0 <= runtime["restart_count"] < 2**31:
        raise ValueError("restart_count")
    for key in ("environment_uuid", "run_id"):
        uuid(runtime[key])
    for key in ("container_id", "network_id", "endpoint_id"):
        if not full_id(runtime[key]):
            raise ValueError("runtime_id")
    if type(runtime["daemon_id"]) is not str or not re.fullmatch(r"[A-Za-z0-9:._-]{1,128}", runtime["daemon_id"]):
        raise ValueError("daemon_id")
    if type(runtime["started_at"]) is not str or not re.fullmatch(r"20\d\d-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d{1,9})?Z", runtime["started_at"]):
        raise ValueError("started_at")
    address = ipaddress.IPv4Address(runtime["ip"])
    if not any(address in ipaddress.IPv4Network(n) for n in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16")):
        raise ValueError("target_ip")
    if str(address) != runtime["ip"]:
        raise ValueError("target_ip")
    if len(json.dumps(request).encode()) > REQUEST_LIMIT:
        raise ValueError("request_bounds")
    return request


def main():
    try:
        request = validate(decode(os.environ["TC_MVP_REQUEST"].encode("ascii"), REQUEST_LIMIT))
        # Fixed sibling path in the pinned read-only image. Reuse Stage 1 probe.
        probe = runpy.run_path(str(Path(__file__).with_name("verifier.py")))["probe"]
        state, reason = probe(request["runtime"]["ip"], 8080)
        raw = json.dumps({"binding": request, "http": state, "reason": reason},
                         separators=(",", ":")).encode("ascii")
        if len(raw) > STDOUT_LIMIT:
            return 2
        sys.stdout.buffer.write(raw)
        return 0  # Completed observation transport, never academic/task success.
    except Exception:
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
