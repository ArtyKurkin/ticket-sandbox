#!/usr/bin/env python3

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import time

HOST = "127.0.0.1"
PORT = 9000

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/health":
            body = b"API HEALTH OK\n"
            self.send_response(200)
        elif self.path == "/report":
            time.sleep(3)
            body = b"REPORT READY\n"
            self.send_response(200)
        else:
            body = b"REPORT API\n"
            self.send_response(200)

        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        pass

if __name__ == "__main__":
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()
