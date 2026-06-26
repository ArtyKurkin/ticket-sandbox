#!/usr/bin/env python3
import http.server
import socketserver
import sys

PORT = 8080

class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(b"APP OK: instance running\n")
    def log_message(self, *args):
        pass

class Server(socketserver.TCPServer):
    allow_reuse_address = True  # избегаем TIME_WAIT при перезапуске

if __name__ == "__main__":
    try:
        with Server(("0.0.0.0", PORT), Handler) as httpd:
            httpd.serve_forever()
    except OSError as e:
        sys.stderr.write("ERROR: %s\n" % e)
        sys.exit(98)
