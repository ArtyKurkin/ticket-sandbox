"""One-shot LOCAL smoke verifier. No Docker, Django, task exec or listening API.

Only an operator-owned parent pipe supplies this request. The echoed binding is
correlation, not authentication. This module does not verify container identity,
socket bind, process ownership, network isolation, or academic completion.
"""
import ipaddress
import json
import socket
import sys
import time
from uuid import UUID

TASK = "l1/service-bind-localhost"
TASK_PORT = 8080  # Semantic requirement; local surrogate port is not proof of it.
PATH = "/"
BODY = b"APP OK: customer service is running\n"
REQUEST_LIMIT = 1024
RESULT_LIMIT = 2048
HEADER_LIMIT = 4096
BODY_LIMIT = 256
PROBE_SECONDS = 0.6


def parse_request(raw):
    if type(raw) is not bytes or len(raw) > REQUEST_LIMIT:
        raise ValueError("request")

    def unique(pairs):
        obj = {}
        for key, value in pairs:
            if key in obj:
                raise ValueError("duplicate")
            obj[key] = value
        return obj

    obj = json.loads(raw, object_pairs_hook=unique)
    keys = {"task", "attempt_id", "environment_id", "runtime_id", "run_id", "ip", "port"}
    if type(obj) is not dict or set(obj) != keys or obj["task"] != TASK:
        raise ValueError("fields")
    if type(obj["attempt_id"]) is not int or not 0 < obj["attempt_id"] < 2**63:
        raise ValueError("attempt")
    for key in ("environment_id", "runtime_id", "run_id"):
        if type(obj[key]) is not str or str(UUID(obj[key])) != obj[key]:
            raise ValueError("uuid")
    # LOCAL only. Parent pins an OS-selected surrogate port; no trainee URL/API.
    if obj["ip"] != "127.0.0.1" or not ipaddress.ip_address(obj["ip"]).is_loopback:
        raise ValueError("endpoint")
    if type(obj["port"]) is not int or not 1024 <= obj["port"] <= 65535:
        raise ValueError("port")
    return obj


def probe(ip, port):
    deadline = time.monotonic() + PROBE_SECONDS

    def remaining():
        left = deadline - time.monotonic()
        if left <= 0:
            raise TimeoutError
        return left

    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(remaining())
            sock.connect((ip, port))
            sock.settimeout(remaining())
            sock.sendall(f"GET / HTTP/1.0\r\nHost: 127.0.0.1:{port}\r\nConnection: close\r\n\r\n".encode("ascii"))
            data = bytearray()
            while b"\r\n\r\n" not in data:
                sock.settimeout(remaining())
                chunk = sock.recv(min(512, HEADER_LIMIT + 1 - len(data)))
                if not chunk:
                    return "unknown", "incomplete_http"
                data.extend(chunk)
                if len(data) > HEADER_LIMIT:
                    return "unknown", "http_bounds"
            header, body = bytes(data).split(b"\r\n\r\n", 1)
            lines = header.decode("ascii").split("\r\n")
            status = lines[0].split(" ", 2)
            if len(status) < 2 or status[0] not in ("HTTP/1.0", "HTTP/1.1"):
                return "unknown", "http_schema"
            headers = {}
            for line in lines[1:]:
                key, value = line.split(":", 1)
                key = key.lower()
                if key in headers or not key or key.strip() != key:
                    return "unknown", "http_schema"
                headers[key] = value.strip()
            if "transfer-encoding" in headers or "content-encoding" in headers:
                return "unknown", "http_schema"
            length = headers.get("content-length", "")
            if not length.isascii() or not length.isdecimal() or len(length) > 3:
                return "unknown", "http_schema"
            length = int(length)
            if length > BODY_LIMIT or len(body) > length:
                return "unknown", "http_bounds"
            while len(body) < length:
                sock.settimeout(remaining())
                chunk = sock.recv(length - len(body))
                if not chunk:
                    return "unknown", "incomplete_http"
                body += chunk
            remaining()
            if status[1] != "200" or body != BODY:
                return "mismatch", "http_mismatch"
            return "matched", "http_match"
    except TimeoutError:
        return "unknown", "timeout"
    except OSError:
        return "unknown", "endpoint_unavailable"
    except (ValueError, UnicodeError):
        return "unknown", "http_schema"


def main():
    try:
        request = parse_request(sys.stdin.buffer.read(REQUEST_LIMIT + 1))
    except (ValueError, TypeError, AttributeError):
        return 2  # No echo of invalid input or arbitrary exception text.
    state, reason = probe(request["ip"], request["port"])
    raw = json.dumps({"binding": request, "http": state, "reason": reason},
                     separators=(",", ":")).encode("ascii")
    if len(raw) > RESULT_LIMIT:
        return 2
    sys.stdout.buffer.write(raw)
    return 0  # Transport completed; NEVER interpret this exit code as a task pass.


if __name__ == "__main__":
    raise SystemExit(main())
