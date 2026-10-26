"""Standalone stdlib-only peer runner. No SDK, filesystem/task access or keys."""
import base64
import ipaddress
import json
import os
import re
import select
import socket
import sys
import time

# Generated artifact identity must equal runtime/live_contract.py. No URL input.
POLICY_ID = 'service-bind-localhost-live-peer-v2'
POLICY_VERSION = 2
PROTOCOL_VERSION = 2
MAX_BODY, MAX_HEADERS, HTTP_SECONDS, RUN_SECONDS = 1024, 8192, 2.0, 8.0


def numeric_ipv4(value):
    ip = ipaddress.IPv4Address(value)
    if str(ip) != value or not any(ip in ipaddress.IPv4Network(n) for n in
                                              ('10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16')):
        raise ValueError('endpoint_invalid')
    return value


def packet(ip, status=None, body=b'', complete=False, transport='uncertain'):
    return dict(protocol_version=PROTOCOL_VERSION, policy_id=POLICY_ID, policy_version=POLICY_VERSION,
                target_ipv4=ip, status=status, body_b64=base64.b64encode(body).decode('ascii'),
                complete=complete, transport=transport)


def probe(ip, *, socket_factory=socket.socket, clock=time.monotonic):
    ip = numeric_ipv4(ip)
    deadline = clock()+HTTP_SECONDS
    sock = socket_factory(socket.AF_INET, socket.SOCK_STREAM)
    try:
        def remaining():
            seconds = deadline-clock()
            if seconds <= 0:
                raise TimeoutError()
            sock.settimeout(seconds)
        remaining()
        sock.connect((ip, 8080))  # AF_INET numeric tuple; no getaddrinfo/DNS/proxy.
        remaining()
        sock.sendall(b'GET / HTTP/1.0\r\nHost: '+ip.encode('ascii')+b':8080\r\nConnection: close\r\n\r\n')
        raw = bytearray()
        while b'\r\n\r\n' not in raw:
            remaining()
            chunk = sock.recv(1)  # Hard header limit and absolute deadline, no over-read.
            if not chunk or len(raw) >= MAX_HEADERS:
                return packet(ip)
            raw.extend(chunk)
        lines = bytes(raw[:-4]).split(b'\r\n')
        if len(lines) > 33 or not re.fullmatch(rb'HTTP/1\.[01] [1-5][0-9]{2}(?: [\x20-\x7e]*)?', lines[0]):
            return packet(ip)
        status = int(lines[0].split(b' ')[1])
        headers = {}
        for line in lines[1:]:
            if b':' not in line or line[:1] in (b' ', b'\t'):
                return packet(ip)
            key, value = line.split(b':', 1)
            if not re.fullmatch(rb'[A-Za-z0-9-]+', key) or key.lower() in headers:
                return packet(ip)
            headers[key.lower()] = value.strip(b' \t')
        # Actual task speaks HTTP/1.0 + Content-Length. Unsupported framing is
        # protocol unknown, never guessed into a successful complete response.
        if b'transfer-encoding' in headers or b'content-encoding' in headers:
            return packet(ip)
        length = headers.get(b'content-length')
        if length is not None and (not re.fullmatch(rb'[0-9]{1,12}', length)):
            return packet(ip)
        expected = int(length) if length is not None else None
        body = bytearray()
        while len(body) <= MAX_BODY:
            if expected is not None and len(body) >= expected:
                return packet(ip, status, bytes(body), True, 'none')
            remaining()
            chunk = sock.recv(min(MAX_BODY+1-len(body), expected-len(body) if expected is not None else MAX_BODY+1))
            if not chunk:
                return packet(ip, status, bytes(body), expected is None or len(body) == expected, 'none')
            body.extend(chunk)
        return packet(ip, status, bytes(body), True, 'none')  # Bounded oversize sentinel1025.
    except ConnectionRefusedError:
        return packet(ip, transport='refused')
    except (TimeoutError, socket.timeout):
        return packet(ip, transport='timeout')
    except OSError:
        return packet(ip)
    finally:
        sock.close()


def await_command(fd, expected, deadline, *, clock=time.monotonic):
    data = bytearray()
    while clock() < deadline and len(data) < 8:
        ready, _, _ = select.select([fd], [], [], max(0, deadline-clock()))
        if not ready:
            break
        chunk = os.read(fd, 1)
        if not chunk:
            break
        data.extend(chunk)
        if chunk == b'\n':
            return bytes(data) == expected
    return False


def await_release(fd, *, clock=time.monotonic):
    return await_command(fd, b'PROBE\n', clock()+RUN_SECONDS-HTTP_SECONDS, clock=clock)


def main():
    try:
        deadline = time.monotonic()+RUN_SECONDS
        ip = numeric_ipv4(os.environ['TC_TARGET_IPV4'])
        result = probe(ip) if await_command(sys.stdin.fileno(), b'PROBE\n', deadline-HTTP_SECONDS) else packet(ip)
        encoded = json.dumps(result, sort_keys=True, separators=(',', ':'))
        if len(encoded) > 4096:
            return 2
        print(encoded, flush=True)
        return 0 if await_command(sys.stdin.fileno(), b'FINISH\n', deadline) else 2
    except Exception:
        return 2  # No arbitrary exception/body/credentials on stderr.


if __name__ == '__main__':
    sys.exit(main())
