#!/usr/bin/env python3
import socketserver

class Handler(socketserver.BaseRequestHandler):
    def handle(self):
        self.request.recv(64)
        self.request.sendall(b"DB OK\n")

if __name__ == "__main__":
    with socketserver.TCPServer(("127.0.0.1", 3306), Handler) as srv:
        srv.serve_forever()
