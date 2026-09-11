#!/usr/bin/env python3

import http.server
import os
import socketserver
import sys


PORT = 8080
MESSAGE = os.getenv("APP_MESSAGE", "APP OK: instance running")


class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(f"{MESSAGE}\n".encode())

    def log_message(self, *args):
        pass


class Server(socketserver.TCPServer):
    allow_reuse_address = True


if __name__ == "__main__":
    try:
        with Server(("0.0.0.0", PORT), Handler) as httpd:
            httpd.serve_forever()
    except OSError as error:
        sys.stderr.write(f"ERROR: {error}\n")
        sys.exit(98)
