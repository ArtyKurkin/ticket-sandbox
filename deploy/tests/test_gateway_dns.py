"""Opt-in real nginx/Docker DNS regression test in a unique disposable project.

RUN_GATEWAY_DNS_TESTS=1 python -m unittest discover -s deploy/tests -p test_gateway_dns.py -v
Requires Docker Compose and PyYAML. Existing containers are only inspected.
"""

import base64
import http.client
import ipaddress
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import tempfile
import time
import unittest
import uuid


ROOT = Path(__file__).resolve().parents[2]
NGINX_CONFIG = ROOT / "deploy/nginx/docker/default.conf"


@unittest.skipUnless(os.environ.get("RUN_GATEWAY_DNS_TESTS") == "1", "opt-in Docker lab")
class GatewayDNSRecreationTests(unittest.TestCase):
    def docker(self, *args):
        result = subprocess.run(
            ["docker", *args], capture_output=True, text=True, timeout=120,
        )
        if result.returncode:
            raise AssertionError(f"docker {args}: {result.stderr}\n{result.stdout}")
        if args[0] == "exec" and args[-1] in ("-t", "-v"):
            return result.stderr.strip()
        return result.stdout.strip()

    def compose(self, *args):
        return self.docker("compose", "-p", self.project, "-f", str(self.compose_path), *args)

    def inspect(self, name):
        return json.loads(self.docker("inspect", name))[0]

    def identity(self, name):
        data = self.inspect(name)
        return (data["Id"], data["Image"], data["State"]["StartedAt"], data["RestartCount"])

    def nginx_processes(self, gateway):
        return [line for line in self.docker("top", gateway, "-eo", "pid,args").splitlines()
                if "nginx:" in line]

    def wait_for(self, operation, description, timeout=45):
        deadline = time.monotonic() + timeout
        last = None
        while time.monotonic() < deadline:
            try:
                last = operation()
                if last:
                    return last
            except (OSError, http.client.HTTPException, AssertionError) as exc:
                last = exc
            time.sleep(0.5)
        self.fail(f"Timed out waiting for {description}: {last}")

    def request(self, path, *, secure=True, cookie=True, method="GET", body=None):
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=3)
        headers = {"Host": "training.fixture:8443", "X-Forwarded-For": "192.0.2.10"}
        if secure:
            headers["X-Forwarded-Proto"] = "https"
        if cookie:
            headers["Cookie"] = "sessionid=fixture"
        try:
            connection.request(method, path, body=body, headers=headers)
            response = connection.getresponse()
            return response.status, dict(response.getheaders()), response.read()
        finally:
            connection.close()

    def assert_routes(self, generation):
        status, _, body = self.request("/healthz/")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["generation"], generation)
        status, headers, _ = self.request("/healthz/", secure=False)
        self.assertEqual(status, 301)
        self.assertEqual(headers["Location"], "https://training.fixture:8443/healthz/")
        status, headers, _ = self.request("/redirect/")
        self.assertEqual(status, 302)
        self.assertEqual(headers["Location"], "http://training.fixture/redirected/?x=1")
        path = "/echo/a%2Fb/?q=x%2Fy&repeat=1&repeat=2"
        status, _, body = self.request(path, method="POST", body="payload=hello")
        self.assertEqual(status, 200)
        data = json.loads(body)
        self.assertEqual((data["path"], data["method"], data["body"]), (path, "POST", "payload=hello"))
        self.assertEqual(data["headers"]["Host"], "training.fixture:8443")
        self.assertEqual(data["headers"]["X-Forwarded-Proto"], "https")
        self.assertTrue(data["headers"]["X-Forwarded-For"].startswith("192.0.2.10, "))
        self.assertTrue(data["headers"]["X-Real-IP"])
        for path in ("/terminal-auth/", "/terminal-auth/nested", "/terminal-broker-auth/", "/_terminal_auth"):
            self.assertEqual(self.request(path)[0], 404, path)
        self.assertEqual(self.request("/terminal/42/ws", cookie=False)[0], 403)
        path = "/terminal/42/data?arg=x%2Fy"
        status, _, body = self.request(path, method="POST", body="terminal-payload")
        self.assertEqual(status, 200)
        data = json.loads(body)
        self.assertEqual((data["path"], data["method"], data["body"]), (path, "POST", "terminal-payload"))
        self.assertEqual(data["headers"]["Host"], "training.fixture:8443")
        self.assertEqual(data["headers"]["X-Forwarded-Proto"], "https")
        self.assertEqual(data["headers"]["Connection"], "close")
        self.assertEqual(data["headers"]["Authorization"], "Basic Zml4dHVyZTpzZWNyZXQ=")
        auth = json.loads(self.request("/_fixture_auth_seen")[2])
        self.assertEqual((auth["path"], auth["method"], auth["body"]), ("/terminal-auth/", "GET", ""))
        self.assertEqual(auth["generation"], generation)
        self.assertEqual(auth["headers"]["X-Original-URI"], path)
        self.assertEqual(auth["headers"]["Host"], "training.fixture:8443")
        self.assertEqual(auth["headers"]["Cookie"], "sessionid=fixture")
        self.assertEqual(auth["headers"]["X-Forwarded-Proto"], "https")

    def open_websocket(self):
        sock = socket.create_connection(("127.0.0.1", self.port), timeout=3)
        self.addCleanup(sock.close)
        key = base64.b64encode(b"fixture-key-12345").decode()
        sock.sendall((
            "GET /terminal/42/ws?token=fixture HTTP/1.1\r\n"
            "Host: training.fixture:8443\r\nCookie: sessionid=fixture\r\n"
            "X-Forwarded-Proto: https\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
            f"Sec-WebSocket-Version: 13\r\nSec-WebSocket-Key: {key}\r\n\r\n"
        ).encode())
        headers = b""
        while not headers.endswith(b"\r\n\r\n"):
            chunk = sock.recv(1)
            self.assertTrue(chunk, headers)
            headers += chunk
        self.assertIn(b"101 Switching Protocols", headers)
        self.assertIn(b"Upgrade: websocket", headers)
        self.assertIn(b"Connection: upgrade", headers)
        return sock

    def assert_websocket_echo(self, sock):
        payload = b"terminal still works"
        mask = b"mask"
        sock.sendall(bytes([0x81, 0x80 | len(payload)]) + mask + bytes(
            value ^ mask[i % 4] for i, value in enumerate(payload)
        ))
        expected = bytes([0x81, len(payload)]) + payload
        actual = b""
        while len(actual) < len(expected):
            chunk = sock.recv(len(expected) - len(actual))
            self.assertTrue(chunk)
            actual += chunk
        self.assertEqual(actual, expected)

    def test_web_recreation_updates_dns_without_gateway_reload(self):
        import yaml

        # Copy only image + healthcheck from production Compose, never its names,
        # networks, env files, volumes or application dependencies.
        source = yaml.safe_load((ROOT / "docker-compose.yml").read_text())["services"]["gateway"]
        existing = {name: self.identity(name) for name in self.docker("ps", "-q").splitlines()}
        self.project = "gateway-dns-" + uuid.uuid4().hex[:12]
        network = self.project + "-network"
        with tempfile.TemporaryDirectory(prefix=self.project + "-") as directory:
            directory = Path(directory)
            self.compose_path = directory / "compose.json"
            shutil.copy(NGINX_CONFIG, directory / "default.conf")
            shutil.copy(Path(__file__).parent / "fixtures/gateway_backend.py", directory / "backend.py")
            self.docker("network", "create", "--label", f"gateway-dns-test={self.project}", network)
            try:
                subnet = json.loads(self.docker("network", "inspect", network))[0]["IPAM"]["Config"][0]["Subnet"]
                addresses = ipaddress.ip_network(subnet)
                old_ip, new_ip = str(addresses[10]), str(addresses[11])
                peer = {
                    "image": os.environ.get("GATEWAY_TEST_WEB_IMAGE", "python:3.13-alpine"),
                    "entrypoint": ["python", "/fixture/backend.py"], "command": [],
                    "volumes": [f"{directory / 'backend.py'}:/fixture/backend.py:ro"],
                }
                config = {
                    "services": {
                        "web": {**peer, "environment": {"GENERATION": "before"},
                                "networks": {"fixture": {"ipv4_address": old_ip}}},
                        "terminal-peer": {**peer, "networks": ["fixture"]},
                        "gateway": {
                            "image": source["image"], "healthcheck": source["healthcheck"],
                            "volumes": [f"{directory / 'default.conf'}:/etc/nginx/conf.d/default.conf:ro"],
                            "ports": ["127.0.0.1::80"], "networks": ["fixture"],
                        },
                    },
                    "networks": {"fixture": {"external": True, "name": network}},
                }
                self.compose_path.write_text(json.dumps(config))
                self.compose("up", "-d")
                gateway = self.compose("ps", "-q", "gateway")
                terminal = self.compose("ps", "-q", "terminal-peer")
                self.port = int(self.inspect(gateway)["NetworkSettings"]["Ports"]["80/tcp"][0]["HostPort"])
                self.wait_for(lambda: self.request("/healthz/")[0] == 200, "initial HTTP 200")
                self.wait_for(lambda: self.inspect(gateway)["State"]["Health"]["Status"] == "healthy", "initial healthy")
                print(self.docker("exec", gateway, "nginx", "-v"), flush=True)
                print(self.docker("exec", gateway, "nginx", "-t"), flush=True)
                self.assert_routes("before")
                websocket = self.open_websocket()
                self.assert_websocket_echo(websocket)
                gateway_identity = self.identity(gateway)
                terminal_identity = self.identity(terminal)
                # Docker top contains host PIDs, including workers: unchanged PIDs
                # prove that no reload or automatic worker replacement occurred.
                nginx_processes = self.nginx_processes(gateway)
                self.assertTrue(nginx_processes)
                old_web = self.compose("ps", "-q", "web")
                config["services"]["web"]["networks"]["fixture"]["ipv4_address"] = new_ip
                config["services"]["web"]["environment"]["GENERATION"] = "after"
                self.compose_path.write_text(json.dumps(config))
                started = time.monotonic()
                self.compose("up", "-d", "--no-deps", "--force-recreate", "web")
                web = self.compose("ps", "-q", "web")
                self.assertNotEqual(old_web, web)
                actual_ip = self.inspect(web)["NetworkSettings"]["Networks"][network]["IPAddress"]
                self.assertEqual(actual_ip, new_ip)
                self.wait_for(lambda: self.request("/healthz/")[0] == 200, "DNS recovery")
                recovered = time.monotonic() - started
                self.assert_routes("after")
                self.assert_websocket_echo(websocket)
                self.assert_websocket_echo(self.open_websocket())
                self.wait_for(lambda: self.inspect(gateway)["State"]["Health"]["Status"] == "healthy", "healthy after recreation")
                self.assertEqual(self.identity(gateway), gateway_identity)
                self.assertEqual(self.identity(terminal), terminal_identity)
                self.assertEqual(self.nginx_processes(gateway), nginx_processes)
                print(f"PASS: Web {old_ip} -> {new_ip}; HTTP recovered in {recovered:.1f}s; "
                      "Gateway healthy, nginx PIDs unchanged, old/new WebSocket echo OK", flush=True)
            finally:
                try:
                    # This project has a random name and no persistent volumes.
                    if self.compose_path.exists():
                        self.compose("down", "--timeout", "2")
                finally:
                    self.docker("network", "rm", network)
                    for name, identity in existing.items():
                        self.assertEqual(self.identity(name), identity, "Existing container changed")
                    print(f"Unchanged pre-existing containers: {len(existing)}", flush=True)
