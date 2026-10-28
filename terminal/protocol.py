"""Bounded binary protocol. A client can send input and dimensions, never a target."""
import json
import struct
import time

MAX_FRAME = 16384
HEADER = struct.Struct("!cI")


def receive_exact(sock, count, deadline=None):
    result = bytearray()
    while len(result) < count:
        if deadline is not None:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("Frame deadline exceeded")
            sock.settimeout(remaining)
        data = sock.recv(count - len(result))
        if not data:
            raise EOFError
        result.extend(data)
    return bytes(result)


def receive(sock, deadline=None):
    kind, size = HEADER.unpack(receive_exact(sock, HEADER.size, deadline))
    if size > MAX_FRAME:
        raise ValueError("Frame too large")
    return kind, receive_exact(sock, size, deadline)


def send(sock, kind, payload):
    if len(payload) > MAX_FRAME:
        raise ValueError("Frame too large")
    sock.sendall(HEADER.pack(kind, len(payload)) + payload)


def dimensions(payload):
    obj = json.loads(payload)
    if (type(obj) is not list or len(obj) != 2
            or any(type(n) is not int or not 1 <= n <= 1000 for n in obj)):
        raise ValueError("Invalid terminal dimensions")
    return obj
