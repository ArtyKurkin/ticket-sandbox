"""Fake Docker SDK only. No client discovery, daemon, sockets, or containers."""
import ast
from copy import deepcopy
from dataclasses import asdict, replace, FrozenInstanceError
import io
import json
from pathlib import Path
import struct
import tempfile
import threading
import unittest
from unittest.mock import patch
from uuid import uuid4

from docker.errors import NotFound
from docker.types import HostConfig

from . import adapter as a, worker


def fixture():
    policy = a.Policy("fake-daemon", "b" * 64, "11111111-1111-4111-8111-111111111111",
                      "172.30.250.0/28", "sha256:" + "f" * 64, "sha256:" + "e" * 64)
    execution = a.Execution(17, 9, "22222222-2222-4222-8222-222222222222",
                            "33333333-3333-4333-8333-333333333333", 1,
                            "a" * 64, "fake-daemon", "2026-10-22T09:00:00.123456789Z",
                            0, 4567, "b" * 64, "c" * 64, "172.30.250.2")
    return policy, execution


def frame(data, stream_id=1):
    return struct.pack("!B3sI", stream_id, b"\0\0\0", len(data)) + data


class Source:
    def __init__(self, execution):
        self.current = execution
        self.calls = 0

    def __call__(self, attempt_id):
        self.calls += 1
        if self.current is None or self.current.attempt_id != attempt_id:
            raise PermissionError("not an authorised current pending attempt")
        return self.current


class FakeAttach:
    def __init__(self):
        self.data = b""
        self.closed = False
        self.timeout = False

    def read(self, size):
        if self.timeout:
            raise TimeoutError
        if self.closed:
            raise ValueError("closed")
        # Fragmentation deliberately crosses Docker header and JSON boundaries.
        count = min(size, 7)
        result, self.data = self.data[:count], self.data[count:]
        return result

    def close(self):
        self.closed = True


class FakeAPI:
    base_url = "http+docker://localhost"
    timeout = 1

    def __init__(self, policy, execution):
        p, e = policy, execution
        self.calls = []
        self.hooks = {}
        self.workers = {}
        self.stream = FakeAttach()
        self.reply = ("matched", "http_match")
        self.stream_transform = lambda data: data
        self.profile_transform = lambda obj: None
        self.create_lost = False
        self.remove_fails = False
        self.target = {
            "Id": e.container_id, "Image": p.target_image, "Name": "/disposable-target",
            "RestartCount": 0, "Mounts": [],
            "State": {"Status": "running", "Running": True, "StartedAt": e.started_at,
                      "Pid": e.pid, "Paused": False, "Restarting": False, "Dead": False},
            "Config": {"Labels": {
                "tc-mvp.scope": p.scope, "tc-mvp.role": "target",
                "tc-mvp.environment": e.environment_uuid, "ticket-sandbox.attempt": "17",
                "ticket-sandbox.queue": "l1", "ticket-sandbox.task": "service-bind-localhost"}},
            "HostConfig": {"Privileged": False, "Binds": None, "CapDrop": ["ALL"],
                           "CapAdd": None, "PidMode": "", "IpcMode": "private",
                           "NetworkMode": p.network_id, "SecurityOpt": ["no-new-privileges:true"]},
            "NetworkSettings": {"Networks": {"tc-mvp-" + p.scope: {
                "NetworkID": p.network_id, "EndpointID": e.endpoint_id, "IPAddress": e.ip}}},
        }
        self.network = {
            "Id": p.network_id, "Name": "tc-mvp-" + p.scope, "Driver": "bridge",
            "Internal": True, "EnableIPv6": False, "Attachable": False,
            "Options": dict(a.NETWORK_OPTIONS),
            "Labels": {"tc-mvp.scope": p.scope, "tc-mvp.role": "data"},
            "IPAM": {"Driver": "default", "Config": [{"Subnet": p.subnet}]},
            "Containers": {e.container_id: {"EndpointID": e.endpoint_id, "IPv4Address": e.ip + "/28"}},
        }

    def hit(self, method, value=None):
        self.calls.append((method, value))
        if method in self.hooks:
            self.hooks[method](self)

    def info(self):
        self.hit("info")
        return {"ID": "fake-daemon"}

    def inspect_container(self, identifier):
        self.hit("inspect", identifier)
        if identifier == self.target["Id"]:
            return deepcopy(self.target)
        for obj in self.workers.values():
            if identifier in (obj["Id"], obj["Name"].lstrip("/")):
                return deepcopy(obj)
        raise NotFound("synthetic not found")

    def inspect_network(self, identifier):
        self.hit("network", identifier)
        return deepcopy(self.network)

    def inspect_image(self, identifier):
        self.hit("image", identifier)
        return {"Id": identifier, "Config": {"Env": ["PATH=/usr/local/bin:/usr/bin:/bin"], "Volumes": None}}

    def create_host_config(self, **kwargs):
        self.hit("host_config")
        return HostConfig(version="1.45", **kwargs)  # Real installed SDK serializer.

    def create_container(self, **kwargs):
        self.hit("create")
        self.launch = deepcopy(kwargs)
        wid = "d" * 64
        obj = {
            "Id": wid, "Image": kwargs["image"], "Name": "/" + kwargs["name"],
            "RestartCount": 0, "Mounts": [], "HostConfig": deepcopy(kwargs["host_config"]),
            "State": {"Status": "created", "Running": False, "ExitCode": 0},
            "Config": {"Image": kwargs["image"], "Entrypoint": kwargs["entrypoint"],
                       "Cmd": [], "User": kwargs["user"], "OpenStdin": False, "Tty": False,
                       "Env": [k + "=" + v for k, v in kwargs["environment"].items()],
                       "Labels": kwargs["labels"]},
            "NetworkSettings": {"Networks": {kwargs["host_config"]["NetworkMode"]: {"NetworkID": ""}}},
        }
        # Engine inspect materializes False; SDK request omits this default.
        obj["HostConfig"].setdefault("AutoRemove", False)
        self.workers[wid] = obj
        self.profile_transform(obj)
        if self.create_lost:
            raise OSError("synthetic response lost after create")
        return {"Id": wid}

    def attach_socket(self, identifier, params):
        self.hit("attach", identifier)
        self.assert_attach = params
        return self.stream

    def start(self, identifier):
        self.hit("start", identifier)
        request = json.loads(self.launch["environment"]["TC_MVP_REQUEST"])
        reply = json.dumps({"binding": request, "http": self.reply[0], "reason": self.reply[1]}).encode()
        self.stream.data = self.stream_transform(frame(reply))
        self.workers[identifier]["State"].update(Status="running", Running=True)

    def wait(self, identifier, **kwargs):
        self.hit("wait", identifier)
        self.workers[identifier]["State"].update(Status="exited", Running=False)
        return {"StatusCode": 0}

    def remove_container(self, identifier, **kwargs):
        self.hit("remove", identifier)
        if self.remove_fails:
            raise OSError("synthetic cleanup failure")
        assert identifier != self.target["Id"]
        assert kwargs == {"force": True, "v": False}
        del self.workers[identifier]


class DockerPilotTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.policy, self.execution = fixture()
        self.source = Source(self.execution)
        self.api = FakeAPI(self.policy, self.execution)
        self.selector = patch.object(a.select, "select", lambda readers, *args: (readers, [], []))
        self.selector.start()
        self.addCleanup(self.selector.stop)

    def pilot(self, **kwargs):
        return a.DockerPilot(self.api, self.policy, self.source, self.directory.name, **kwargs)

    def observe(self):
        return self.pilot(enabled=True).observe(17)

    def test_default_off_and_authorisation_precede_all_docker_effects(self):
        self.assertEqual(self.pilot().observe(17).reason, "disabled")
        self.assertEqual(self.api.calls, [])
        self.assertEqual(self.source.calls, 0)
        self.source.current = None
        self.assertEqual(self.observe().reason, "authorization_unknown")
        self.assertEqual(self.api.calls, [])

    def test_positive_binding_profile_protected_artifact_and_owned_cleanup(self):
        result = self.observe()
        self.assertEqual(result.http, "matched")
        self.assertEqual(result.binding, self.execution)
        self.assertEqual((result.bind, result.process, result.network_isolation), ("unverified",) * 3)
        self.assertEqual(result.task_verdict, "unknown")
        self.assertFalse(result.academic_pass)
        self.assertEqual(self.api.workers, {})
        self.assertTrue(self.api.stream.closed)
        names = [method for method, _ in self.api.calls]
        self.assertLess(names.index("attach"), names.index("start"))
        self.assertEqual(self.api.launch["host_config"]["Memory"], 64 * 1024**2)
        self.assertEqual(self.api.launch["host_config"]["NetworkMode"], self.policy.network_id)
        self.assertEqual(self.api.launch["entrypoint"], a.ENTRY)
        artifact = Path(self.directory.name) / (self.execution.run_id + ".json")
        self.assertEqual(artifact.stat().st_mode & 0o777, 0o600)
        self.assertEqual(json.loads(artifact.read_bytes()), asdict(result))
        with self.assertRaises(FrozenInstanceError):
            result.http = "matched"
        with self.assertRaises((ValueError, TypeError)):
            replace(result, academic_pass=True)

    def test_fixed_http_mismatch_and_unknown_are_observations_not_task_pass(self):
        for pair in (("mismatch", "http_mismatch"), ("unknown", "endpoint_unavailable"), ("unknown", "timeout")):
            with self.subTest(pair=pair), tempfile.TemporaryDirectory() as directory:
                self.api.reply = pair
                result = a.DockerPilot(self.api, self.policy, self.source, directory, enabled=True).observe(17)
                self.assertEqual(result.http, pair[0])
                self.assertEqual(result.task_verdict, "failed" if pair[0] == "mismatch" else "unknown")
                self.assertFalse(result.academic_pass)

    def test_check_script_and_tool_spoofs_are_never_read_or_executed(self):
        self.api.trainee_files = {"/task/check.sh": "exit 0", "/usr/bin/curl": '{"passed":true}', "/usr/sbin/ip": "fake"}
        self.api.reply = ("mismatch", "http_mismatch")
        result = self.observe()
        self.assertEqual(result.http, "mismatch")
        self.assertFalse(any("exec" in method for method, _ in self.api.calls))
        self.assertEqual(self.api.trainee_files["/task/check.sh"], "exit 0")

    def test_target_unavailable_never_launches_worker(self):
        original = self.api.inspect_container
        def missing(identifier):
            if identifier == self.execution.container_id:
                raise NotFound("synthetic absent")
            return original(identifier)
        self.api.inspect_container = missing
        self.assertEqual(self.observe().reason, "target_unavailable")
        self.assertFalse(any(method == "create" for method, _ in self.api.calls))

    def test_restart_pid_and_endpoint_drift_discard_valid_worker_reply(self):
        for mutation in (
            lambda api: api.target.update(RestartCount=1),
            lambda api: api.target["State"].update(StartedAt="2026-10-22T09:01:00Z"),
            lambda api: api.target["State"].update(Pid=9999),
            lambda api: next(iter(api.target["NetworkSettings"]["Networks"].values())).update(IPAddress="172.30.250.3"),
            lambda api: next(iter(api.target["NetworkSettings"]["Networks"].values())).update(EndpointID="9" * 64),
        ):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as directory:
                api = FakeAPI(self.policy, self.execution)
                api.hooks["start"] = mutation
                result = a.DockerPilot(api, self.policy, self.source, directory, enabled=True).observe(17)
                self.assertEqual(result.http, "unknown")
                self.assertEqual(result.reason, "runtime_changed")
                self.assertIsNone(result.binding)
                self.assertEqual(api.workers, {})

    def test_stale_django_run_ordinal_environment_or_container_is_unknown(self):
        for key, value in (("run_id", str(uuid4())), ("ordinal", 2), ("environment_uuid", str(uuid4())), ("container_id", "8" * 64)):
            with self.subTest(key=key), tempfile.TemporaryDirectory() as directory:
                self.source.current = self.execution
                api = FakeAPI(self.policy, self.execution)
                api.hooks["start"] = lambda api: setattr(self.source, "current", replace(self.execution, **{key: value}))
                result = a.DockerPilot(api, self.policy, self.source, directory, enabled=True).observe(17)
                self.assertEqual(result.reason, "stale_execution")
                self.assertEqual(api.workers, {})

    def test_network_platform_extra_peer_or_unsafe_caps_refused(self):
        for mutation in (
            lambda api: api.network.update(Name="training-platform-runtime"),
            lambda api: api.network.update(Internal=False),
            lambda api: api.network.update(Options={}),
            lambda api: api.network["Containers"].update({"7" * 64: {}}),
            lambda api: api.target["HostConfig"].update(CapAdd=["NET_ADMIN"]),
            lambda api: api.target.update(Mounts=[{"Source": "/var/run/docker.sock"}]),
        ):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as directory:
                api = FakeAPI(self.policy, self.execution)
                mutation(api)
                result = a.DockerPilot(api, self.policy, self.source, directory, enabled=True).observe(17)
                self.assertEqual(result.http, "unknown")
                self.assertFalse(any(method == "create" for method, _ in api.calls))

    def test_daemon_identity_mismatch_and_unavailable_sdk_fail_closed(self):
        self.api.info = lambda: {"ID": "another-daemon"}
        self.assertEqual(self.observe().reason, "daemon_mismatch")
        self.assertFalse(self.api.workers)
        with tempfile.TemporaryDirectory() as directory:
            def unavailable():
                raise TimeoutError
            self.api.info = unavailable
            result = a.DockerPilot(self.api, self.policy, self.source, directory, enabled=True).observe(17)
            self.assertEqual(result.reason, "timeout")
            self.assertFalse(self.api.workers)

    def test_second_attempt_cannot_adopt_first_runtime(self):
        self.source.current = replace(self.execution, attempt_id=18, run_id=str(uuid4()))
        self.assertEqual(self.pilot(enabled=True).observe(18).reason, "runtime_changed")
        self.assertFalse(any(method == "create" for method, _ in self.api.calls))
        self.assertEqual(self.api.target["Config"]["Labels"]["ticket-sandbox.attempt"], "17")

    def test_persisted_claim_prevents_sequential_and_cross_instance_replay(self):
        self.assertEqual(self.observe().http, "matched")
        count = len(self.api.calls)
        self.assertEqual(self.observe().reason, "replay")
        self.assertEqual(len(self.api.calls), count)

    def test_concurrent_calls_have_one_worker_and_no_foreign_cleanup(self):
        entered, release = threading.Event(), threading.Event()
        self.api.hooks["start"] = lambda api: (entered.set(), release.wait(2))
        pilot = self.pilot(enabled=True)
        results = []
        thread = threading.Thread(target=lambda: results.append(pilot.observe(17)))
        thread.start()
        try:
            self.assertTrue(entered.wait(2))
            self.assertEqual(pilot.observe(17).reason, "busy")
            count = len(self.api.calls)
            self.assertEqual(self.observe().reason, "replay")
            self.assertEqual(len(self.api.calls), count)
            self.assertEqual(len(self.api.workers), 1)
        finally:
            release.set()
            thread.join(3)
        self.assertFalse(thread.is_alive())
        self.assertEqual(results[0].http, "matched")
        self.assertEqual(self.api.workers, {})

    def test_malformed_truncated_oversize_and_stderr_streams_refused(self):
        for raw in (frame(b"{"), frame(b"{}")[0:-1], b"\1\0", frame(b"x" * 4097),
                    frame(b"x" * 1025, 2), frame(b"oops", 3), frame(b"{}", 2)):
            with self.subTest(raw=raw[:10]), tempfile.TemporaryDirectory() as directory:
                api = FakeAPI(self.policy, self.execution)
                api.stream_transform = lambda data: raw
                result = a.DockerPilot(api, self.policy, self.source, directory, enabled=True).observe(17)
                self.assertEqual(result.http, "unknown")
                self.assertEqual(api.workers, {})

    def test_forged_and_previous_result_binding_is_not_accepted(self):
        def stale(data):
            obj = json.loads(data[8:])
            obj["binding"]["execution_uuid"] = str(uuid4())
            return frame(json.dumps(obj).encode())
        self.api.stream_transform = stale
        self.assertEqual(self.observe().reason, "verifier_result_invalid")
        self.assertEqual(self.api.workers, {})

    def test_timeout_cleans_owned_worker_and_never_target(self):
        self.api.stream.timeout = True
        result = self.observe()
        self.assertEqual((result.http, result.reason), ("unknown", "timeout"))
        self.assertEqual(self.api.workers, {})
        self.assertNotIn(("remove", self.execution.container_id), self.api.calls)

    def test_lost_create_response_recovers_only_own_exact_labelled_worker(self):
        self.api.create_lost = True
        self.assertEqual(self.observe().http, "unknown")
        self.assertEqual(self.api.workers, {})
        self.assertFalse(any(method == "start" for method, _ in self.api.calls))

    def test_profile_fault_cleanup_failure_and_foreign_labels_remain_unknown(self):
        for mutation, remaining in ((lambda obj: obj["HostConfig"].update(Privileged=True), False),
                                    (lambda obj: obj["Config"]["Labels"].update({"tc-mvp.execution": "foreign"}), True)):
            with self.subTest(remaining=remaining), tempfile.TemporaryDirectory() as directory:
                api = FakeAPI(self.policy, self.execution)
                api.profile_transform = mutation
                result = a.DockerPilot(api, self.policy, self.source, directory, enabled=True).observe(17)
                self.assertEqual(result.http, "unknown")
                self.assertEqual(bool(api.workers), remaining)
                self.assertFalse(any(method == "start" for method, _ in api.calls))
        self.api.remove_fails = True
        self.assertEqual(self.observe().reason, "cleanup_unknown")

    def test_change_during_cleanup_is_not_published_as_match(self):
        self.api.hooks["remove"] = lambda api: api.target.update(RestartCount=1)
        result = self.observe()
        self.assertEqual((result.http, result.reason), ("unknown", "runtime_changed"))
        self.assertEqual(self.api.workers, {})

    def test_late_artifact_write_cannot_publish_match(self):
        clock = [0.0]
        count = [0]
        fsync = a.os.fsync
        def late(fd):
            fsync(fd)
            count[0] += 1
            if count[0] == 2:
                clock[0] = a.RUN_SECONDS + 1
        with patch.object(a.time, "monotonic", lambda: clock[0]), patch.object(a.os, "fsync", late):
            result = self.observe()
        self.assertEqual((result.http, result.reason), ("unknown", "timeout"))
        artifact = Path(self.directory.name) / (self.execution.run_id + ".json")
        self.assertEqual(json.loads(artifact.read_bytes())["http"], "unknown")
        self.assertEqual(self.api.workers, {})

    def test_artifact_fsync_failure_preserves_unknown_claim(self):
        count = [0]
        fsync = a.os.fsync
        def fail_final(fd):
            count[0] += 1
            if count[0] == 2:
                raise OSError("synthetic storage failure")
            fsync(fd)
        with patch.object(a.os, "fsync", fail_final):
            result = self.observe()
        self.assertEqual((result.http, result.reason), ("unknown", "artifact_unavailable"))
        artifact = Path(self.directory.name) / (self.execution.run_id + ".json")
        self.assertEqual(json.loads(artifact.read_bytes())["http"], "unknown")
        self.assertEqual(list(Path(self.directory.name).iterdir()), [artifact])
        self.assertEqual(self.api.workers, {})

    def test_worker_id_substitution_never_grants_foreign_cleanup(self):
        original = self.api.inspect_container
        started = [False]
        self.api.hooks["start"] = lambda api: started.__setitem__(0, True)
        def wrong_reply(identifier):
            obj = original(identifier)
            if started[0] and identifier == "d" * 64:
                obj["Id"] = "8" * 64
            return obj
        self.api.inspect_container = wrong_reply
        result = self.observe()
        self.assertEqual((result.http, result.reason), ("unknown", "cleanup_unknown"))
        self.assertFalse(any(method == "remove" for method, _ in self.api.calls))

    def test_interrupt_does_owned_cleanup_and_claim_blocks_redispatch(self):
        def interrupt(api):
            raise KeyboardInterrupt
        self.api.hooks["start"] = interrupt
        with self.assertRaises(KeyboardInterrupt):
            self.observe()
        self.assertEqual(self.api.workers, {})
        count = len(self.api.calls)
        self.assertEqual(self.observe().reason, "replay")
        self.assertEqual(len(self.api.calls), count)

    def test_image_worker_reuses_fixed_probe_and_rejects_extra_commands(self):
        request = {"policy": worker.POLICY, "execution_uuid": str(uuid4()), "runtime": asdict(self.execution)}
        output = io.BytesIO()
        probe_calls = []
        def probe(ip, port):
            probe_calls.append((ip, port))
            return "matched", "http_match"
        with patch.dict(worker.os.environ, {"TC_MVP_REQUEST": json.dumps(request)}), \
                patch.object(worker.runpy, "run_path", return_value={"probe": probe}), \
                patch.object(worker.sys, "stdout", type("Output", (), {"buffer": output})()):
            self.assertEqual(worker.main(), 0)
        self.assertEqual(probe_calls, [(self.execution.ip, 8080)])
        self.assertEqual(json.loads(output.getvalue())["binding"], request)
        for key in ("command", "port", "url", "image"):
            with self.subTest(key=key), self.assertRaises(ValueError):
                worker.validate(dict(request, **{key: "untrusted"}))

    def test_reused_http_probe_with_fake_tcp_body_status_and_prepared_json(self):
        from .. import verifier
        request = {"policy": worker.POLICY, "execution_uuid": str(uuid4()), "runtime": asdict(self.execution)}
        for status, body, expected in ((200, verifier.BODY, "matched"), (503, verifier.BODY, "mismatch"),
                                        (200, b"wrong", "mismatch"), (200, b'{"http":"matched"}', "mismatch")):
            response = f"HTTP/1.0 {status} Test\r\nContent-Length: {len(body)}\r\n\r\n".encode() + body
            calls = []
            class FakeTCP:
                def __init__(self, *args):
                    self.remaining = response
                def __enter__(self):
                    return self
                def __exit__(self, *args):
                    pass
                def settimeout(self, value):
                    self.timeout = value
                def connect(self, address):
                    calls.append(address)
                def sendall(self, data):
                    calls.append(data)
                def recv(self, size):
                    chunk, self.remaining = self.remaining[:size], self.remaining[size:]
                    return chunk
            output = io.BytesIO()
            with self.subTest(status=status, body=body), \
                    patch.dict(worker.os.environ, {"TC_MVP_REQUEST": json.dumps(request)}), \
                    patch.object(worker.runpy, "run_path", return_value={"probe": verifier.probe}), \
                    patch.object(verifier.socket, "socket", FakeTCP), \
                    patch.object(worker.sys, "stdout", type("Output", (), {"buffer": output})()):
                self.assertEqual(worker.main(), 0)
                self.assertEqual(json.loads(output.getvalue())["http"], expected)
                self.assertEqual(calls[0], (self.execution.ip, 8080))
                self.assertTrue(calls[1].startswith(b"GET / HTTP/1.0\r\n"))

    def test_no_django_writers_or_native_v2_paths_in_production_modules(self):
        for module in (a, worker):
            source = Path(module.__file__).read_text()
            tree = ast.parse(source)
            imports = [node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)]
            self.assertFalse(any(name.startswith(("django", "sandbox", "trusted_checker_")) for name in imports))
            self.assertNotIn("exec_run(", source)
            self.assertNotIn("from_env(", source)


if __name__ == "__main__":
    unittest.main()
