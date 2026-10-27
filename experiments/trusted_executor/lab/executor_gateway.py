"""Lab-only gateway. Not a production security boundary."""

import json
import os
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

os.environ.setdefault(
    "DJANGO_SETTINGS_MODULE",
    "config.e2e_settings",
)

import django
django.setup()

from executor_protocol import MAX_BODY, verify_request
from sandbox.services.http_observations import run_observation


SECRET = Path("/run/secrets/executor-key").read_bytes().strip()
if len(SECRET) < 32:
    raise RuntimeError("executor_secret_too_short")

seen_nonces = set()


class Handler(BaseHTTPRequestHandler):
    def reply(self, status, message):
        body = json.dumps({"status": message}).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        if self.path != "/observe":
            return self.reply(404, "not_found")

        try:
            size = int(self.headers.get("Content-Length", "-1"))
            if not 0 <= size <= MAX_BODY:
                return self.reply(413, "invalid_size")

            body = self.rfile.read(size)
            signature = self.headers.get("X-Executor-Signature", "")

            data = verify_request(body, signature, SECRET)

            nonce = data["nonce"]
            if nonce in seen_nonces:
                return self.reply(409, "replay")

            if len(seen_nonces) >= 10000:
                return self.reply(503, "nonce_store_full")

            seen_nonces.add(nonce)

        except ValueError:
            return self.reply(403, "rejected")

        run_observation(data["run_id"])
        self.reply(200, "processed")


if __name__ == "__main__":
    HTTPServer(("0.0.0.0", 8765), Handler).serve_forever()
