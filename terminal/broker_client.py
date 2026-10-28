"""ttyd child: preserve bytes, propagate PTY size, close the socket on hangup."""
import fcntl
import argparse
import json
import os
import select
import signal
import socket
import struct
import sys
import termios
import tty
from pathlib import Path

from terminal.protocol import send


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--socket-dir", default="/run/terminal")
    folder = Path(parser.parse_args().socket_dir)
    config = json.loads((folder / "client.json").read_text())
    conn = socket.socket(socket.AF_UNIX)
    conn.connect(str(folder / "broker.sock"))
    conn.settimeout(5)
    send(conn, b"H", json.dumps({"version": 2, "credential": config["credential"]}).encode())
    # No shell until the broker has authenticated the client.
    if conn.recv(1) != b"\x01":
        raise RuntimeError("Terminal authorization failed")
    conn.settimeout(None)
    previous = termios.tcgetattr(0)
    resized = True
    stopped = False

    def resize(*_):
        nonlocal resized
        resized = True

    def stop(*_):
        nonlocal stopped
        stopped = True

    signal.signal(signal.SIGWINCH, resize)
    for sig in (signal.SIGHUP, signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, stop)
    try:
        tty.setraw(0)
        while not stopped:
            if resized:
                resized = False
                rows, cols, _, _ = struct.unpack("HHHH", fcntl.ioctl(0, termios.TIOCGWINSZ, b"\0" * 8))
                send(conn, b"R", json.dumps([max(rows, 1), max(cols, 1)]).encode())
            ready, _, _ = select.select([0, conn], [], [], 0.1)
            if 0 in ready:
                data = os.read(0, 16384)
                if not data:
                    break
                send(conn, b"I", data)
            if conn in ready:
                data = conn.recv(16384)
                if not data:
                    break
                view = memoryview(data)
                while view:
                    view = view[os.write(1, view):]
    finally:
        conn.close()
        termios.tcsetattr(0, termios.TCSANOW, previous)


if __name__ == "__main__":
    main()
