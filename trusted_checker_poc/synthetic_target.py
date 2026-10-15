"""Intentionally untrusted fixture. Echo is correlation, not application attestation."""
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import hashlib
from pathlib import Path
import time

CONFIG = Path('/fixture/service.json')
READY = Path('/fixture/ready.json')


def read_config():
    config = json.loads(CONFIG.read_text())
    if (set(config) - {'bind', 'response_delay'} or
            config.get('bind') not in ('127.0.0.1', '0.0.0.0') or
            type(config.get('response_delay', 0)) not in (int, float) or
            not 0 <= config.get('response_delay', 0) <= 10):
        raise ValueError('invalid_fixture_config')
    return config


def config_digest(config):
    return hashlib.sha256(json.dumps(config, sort_keys=True).encode()).hexdigest()


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path != '/probe':
            self.send_error(404)
            return
        # A bounded, explicitly configured synthetic workload for deadline and
        # concurrency tests. Not a checker startup/validation sleep.
        time.sleep(self.server.response_delay)
        body = json.dumps({'challenge':self.headers.get('X-PoC-Challenge',''), 'service':'synthetic-ipv4-v1'}).encode()
        self.send_response(200)
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def log_message(self, *_):
        pass


def main():
    # Integration operator changes a run-owned fixture; no Docker restart.
    while True:
        config = read_config()
        address = config['bind']
        server = HTTPServer((address,8080), Handler)
        server.timeout = 0.2
        server.response_delay = config.get('response_delay', 0)
        ready = READY.with_suffix('.tmp')
        ready.write_text(json.dumps({'config_digest':config_digest(config)}))
        ready.replace(READY)
        try:
            while read_config() == config:
                server.handle_request()
        finally:
            server.server_close()


if __name__ == '__main__':
    main()
