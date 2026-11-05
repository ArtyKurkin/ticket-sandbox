"""Disposable HTTP/auth/WebSocket peer; no Django, database or Docker access."""

import base64
import hashlib
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    last_auth = None

    def reply(self, status, data=None, headers=None):
        body = json.dumps(data).encode() if data is not None else b""
        self.send_response(status)
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
        record = {
            "path": self.path, "method": self.command, "body": body.decode(),
            "headers": dict(self.headers), "generation": os.environ.get("GENERATION"),
        }
        if self.path == "/terminal-auth/":
            Handler.last_auth = record
            if self.headers.get("Cookie") != "sessionid=fixture":
                return self.reply(403)
            return self.reply(204, headers={
                "X-Terminal-Upstream": "terminal-peer:8000",
                "X-Terminal-Authorization": "Basic Zml4dHVyZTpzZWNyZXQ=",
            })
        if self.path == "/_fixture_auth_seen":
            return self.reply(200, Handler.last_auth)
        if self.path == "/redirect/":
            upstream = os.environ.get("UPSTREAM_HOST", "web:8000")
            return self.reply(302, headers={"Location": f"http://{upstream}/redirected/?x=1"})
        if self.path == "/healthz/" and self.headers.get("X-Forwarded-Proto") != "https":
            return self.reply(301, headers={
                "Location": "https://" + self.headers["Host"] + self.path,
            })
        if self.path.startswith("/terminal/"):
            if self.headers.get("Authorization") != "Basic Zml4dHVyZTpzZWNyZXQ=":
                return self.reply(401)
            if self.headers.get("Upgrade", "").lower() == "websocket":
                key = self.headers["Sec-WebSocket-Key"] + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
                accept = base64.b64encode(hashlib.sha1(key.encode()).digest()).decode()
                self.send_response(101)
                self.send_header("Upgrade", "websocket")
                self.send_header("Connection", "Upgrade")
                self.send_header("Sec-WebSocket-Accept", accept)
                self.end_headers()
                while True:
                    frame = self.rfile.read(2)
                    if len(frame) != 2 or frame[0] & 0x0f == 8:
                        return
                    length = frame[1] & 0x7f
                    if length > 125 or not frame[1] & 0x80:
                        raise ValueError("Fixture only accepts short masked client frames")
                    mask = self.rfile.read(4)
                    payload = self.rfile.read(length)
                    decoded = bytes(v ^ mask[i % 4] for i, v in enumerate(payload))
                    self.wfile.write(bytes([0x81, len(decoded)]) + decoded)
                    self.wfile.flush()
        return self.reply(200, record)

    do_POST = do_GET


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", 8000), Handler).serve_forever()
