"""Default-OFF, explicit local Docker SDK adapter. Never discovers a daemon.

read_attempt is a TRUSTED orchestrator read port: it must authorize user/task,
return the current pending TechnicalCheckExecution, and its exact environment.
This module never imports Django or writes CheckRun/Ledger/academic state.
"""
from dataclasses import asdict, dataclass, field
from contextlib import ExitStack
import ipaddress
import json
import os
from pathlib import Path
import re
import select
import struct
import tempfile
import threading
import time
from uuid import uuid4

from docker.errors import NotFound
from docker.types import LogConfig
from requests.exceptions import Timeout as RequestTimeout

from . import worker

RUN_SECONDS = 5.0
API_SECONDS = 1.0
CLEANUP_SECONDS = 2.0
ENTRY = ["/usr/local/bin/python", "-I", "-S", "-B", "/checker/worker.py"]
NETWORK_OPTIONS = {"com.docker.network.bridge.gateway_mode_ipv4": "isolated"}
UNKNOWN = {
    "disabled", "busy", "authorization_unknown", "replay", "stale_execution",
    "daemon_mismatch", "runtime_changed", "network_unapproved", "unsafe_target",
    "target_unavailable", "image_unavailable", "worker_profile_invalid",
    "worker_unavailable", "stream_invalid", "output_bounds", "verifier_result_invalid",
    "timeout", "cleanup_unknown", "artifact_unavailable",
}


class Refused(Exception):
    pass


def require(condition, reason):
    if not condition:
        raise Refused(reason)


@dataclass(frozen=True)
class Execution:
    attempt_id: int
    user_id: int
    environment_uuid: str
    run_id: str
    ordinal: int
    container_id: str
    daemon_id: str
    started_at: str
    restart_count: int
    pid: int
    network_id: str
    endpoint_id: str
    ip: str

    def __post_init__(self):
        worker.validate({"policy": worker.POLICY, "execution_uuid": "00000000-0000-0000-0000-000000000001", "runtime": asdict(self)})


@dataclass(frozen=True)
class Policy:
    daemon_id: str
    network_id: str
    scope: str
    subnet: str
    target_image: str
    verifier_image: str

    def __post_init__(self):
        worker.uuid(self.scope)
        require(worker.full_id(self.network_id), "network_unapproved")
        require(type(self.daemon_id) is str and re.fullmatch(r"[A-Za-z0-9:._-]{1,128}", self.daemon_id), "daemon_mismatch")
        for image in (self.target_image, self.verifier_image):
            require(type(image) is str and re.fullmatch(r"sha256:[0-9a-f]{64}", image), "image_unavailable")
        network = ipaddress.IPv4Network(self.subnet)
        require(network.num_addresses <= 64 and any(network.subnet_of(ipaddress.IPv4Network(n)) for n in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16")), "network_unapproved")


@dataclass(frozen=True)
class Observation:
    http: str
    reason: str
    binding: Execution | None
    execution_uuid: str
    verifier_image: str
    worker_id: str | None = None
    policy: str = field(default=worker.POLICY, init=False)
    bind: str = field(default="unverified", init=False)
    process: str = field(default="unverified", init=False)
    network_isolation: str = field(default="unverified", init=False)
    academic_pass: bool = field(default=False, init=False)
    task_verdict: str = field(default="unknown", init=False)

    def __post_init__(self):
        require((self.http, self.reason) in worker.REASONS or (self.http == "unknown" and self.reason in UNKNOWN), "verifier_result_invalid")
        object.__setattr__(self, "task_verdict", "failed" if self.http == "mismatch" else "unknown")


def _read_attach(stream, deadline):
    """Docker's standard 8-byte non-TTY framing; no custom helper protocol."""
    def read_exact(size, eof_ok=False):
        data = bytearray()
        while len(data) < size:
            left = deadline - time.monotonic()
            require(left > 0, "timeout")
            require(select.select([stream], [], [], left)[0], "timeout")
            chunk = stream.read(min(512, size - len(data)))
            require(type(chunk) is bytes and len(chunk) <= size - len(data), "stream_invalid")
            if not chunk:
                require(eof_ok and not data, "stream_invalid")
                return None
            data.extend(chunk)
        return bytes(data)

    buffers = {1: bytearray(), 2: bytearray()}
    caps = {1: worker.STDOUT_LIMIT, 2: worker.STDERR_LIMIT}
    for _ in range(64):
        header = read_exact(8, eof_ok=True)
        if header is None:
            return bytes(buffers[1]), bytes(buffers[2])
        stream_id, reserved, size = struct.unpack("!B3sI", header)
        require(stream_id in buffers and reserved == b"\0\0\0", "stream_invalid")
        require(size <= caps[stream_id] - len(buffers[stream_id]), "output_bounds")
        if size:
            buffers[stream_id].extend(read_exact(size))
    raise Refused("output_bounds")


class DockerPilot:
    def __init__(self, api, policy, read_attempt, artifact_dir, *, enabled=False):
        require(type(policy) is Policy and type(enabled) is bool, "authorization_unknown")
        self.api, self.policy, self.read_attempt = api, policy, read_attempt
        self.artifact_dir = Path(artifact_dir)
        self.enabled = enabled
        self._lock = threading.Lock()

    def _call(self, method, *args, **kwargs):
        left = self.deadline - time.monotonic()
        require(left > 0, "timeout")
        self.api.timeout = min(API_SECONDS, left)
        result = method(*args, **kwargs)
        # Caller records handles before its next deadline check, including create.
        return result

    def _network(self, execution, worker_id=None):
        a = self._call(self.api.inspect_network, self.policy.network_id)
        expected = {execution.container_id}
        if worker_id:
            expected.add(worker_id)
        require(a["Id"] == self.policy.network_id and a["Name"] == "tc-mvp-" + self.policy.scope
                and a["Driver"] == "bridge" and a["Internal"] is True
                and a.get("EnableIPv6") is False and not a.get("Ingress")
                and not a.get("Attachable") and a["Options"] == NETWORK_OPTIONS
                and a["Labels"].get("tc-mvp.scope") == self.policy.scope
                and a["Labels"].get("tc-mvp.role") == "data", "network_unapproved")
        require(a["IPAM"]["Driver"] == "default" and len(a["IPAM"]["Config"]) == 1
                and a["IPAM"]["Config"][0]["Subnet"] == self.policy.subnet, "network_unapproved")
        members = a.get("Containers", {})
        require(execution.container_id in members and set(members) <= expected, "network_unapproved")
        peer = members[execution.container_id]
        address = ipaddress.IPv4Interface(peer["IPv4Address"])
        require(peer["EndpointID"] == execution.endpoint_id and str(address.ip) == execution.ip
                and str(address.network) == self.policy.subnet, "network_unapproved")

    def _target(self, execution):
        try:
            a = self._call(self.api.inspect_container, execution.container_id)
        except NotFound:
            raise Refused("target_unavailable") from None
        p, h, c, s = self.policy, a["HostConfig"], a["Config"], a["State"]
        require(a["Id"] == execution.container_id and a["Image"] == p.target_image
                and s["Running"] is True and s["Status"] == "running"
                and not any(s.get(k) for k in ("Paused", "Restarting", "Dead", "OOMKilled"))
                and s["StartedAt"] == execution.started_at and type(s["Pid"]) is int and s["Pid"] == execution.pid
                and type(a["RestartCount"]) is int and a["RestartCount"] == execution.restart_count, "runtime_changed")
        require(not h.get("Privileged") and not h.get("Binds") and not a.get("Mounts")
                and not h.get("VolumesFrom") and not h.get("Devices") and not h.get("CapAdd")
                and h.get("CapDrop") == ["ALL"] and not h.get("PidMode")
                and h.get("IpcMode", "private") == "private" and not h.get("PortBindings") and not h.get("PublishAllPorts")
                and h["NetworkMode"] == p.network_id
                and h.get("SecurityOpt") in (["no-new-privileges"], ["no-new-privileges:true"])
                and not h.get("DeviceRequests") and not h.get("UTSMode"), "unsafe_target")
        labels = c.get("Labels") or {}
        require(all(labels.get(k) == v for k, v in {
            "tc-mvp.scope": p.scope, "tc-mvp.role": "target",
            "tc-mvp.environment": execution.environment_uuid,
            "ticket-sandbox.attempt": str(execution.attempt_id),
            "ticket-sandbox.queue": "l1", "ticket-sandbox.task": "service-bind-localhost",
        }.items()), "runtime_changed")
        networks = a["NetworkSettings"]["Networks"]
        require(len(networks) == 1, "runtime_changed")
        endpoint = next(iter(networks.values()))
        require(endpoint["NetworkID"] == p.network_id and endpoint["EndpointID"] == execution.endpoint_id
                and endpoint["IPAddress"] == execution.ip, "runtime_changed")

    def _owned(self, a, execution, execution_uuid, name):
        labels = a["Config"].get("Labels") or {}
        return (worker.full_id(a["Id"]) and a["Id"] != execution.container_id
                and a["Name"] == "/" + name and a["Image"] == self.policy.verifier_image
                and all(labels.get(k) == v for k, v in self._labels(execution, execution_uuid).items()))

    def _labels(self, execution, execution_uuid):
        return {"tc-mvp.scope": self.policy.scope, "tc-mvp.role": "verifier",
                "tc-mvp.run": execution.run_id, "tc-mvp.execution": execution_uuid}

    def _profile(self, a, execution, execution_uuid, name, env):
        c, h = a["Config"], a["HostConfig"]
        actual_env = dict(item.split("=", 1) for item in c["Env"])
        require(self._owned(a, execution, execution_uuid, name)
                and c["Image"] == self.policy.verifier_image and c["Entrypoint"] == ENTRY
                and not c.get("Cmd") and c["User"] == "65532:65532"
                and not c.get("Tty") and not c.get("OpenStdin")
                and actual_env == env and len(c["Env"]) == len(env)
                and h["ReadonlyRootfs"] is True and not h.get("Privileged")
                and not h.get("Binds") and not a.get("Mounts") and not h.get("VolumesFrom")
                and not h.get("Devices") and not h.get("CapAdd") and h["CapDrop"] == ["ALL"]
                and not h.get("PidMode") and h.get("IpcMode") == "private"
                and not h.get("PortBindings") and not h.get("PublishAllPorts")
                and h["NetworkMode"] == self.policy.network_id
                and h["SecurityOpt"] in (["no-new-privileges"], ["no-new-privileges:true"])
                and not h.get("DeviceRequests") and not h.get("UTSMode")
                and h["Memory"] == 64 * 1024**2 and h["PidsLimit"] == 16 and h["NanoCpus"] == 250_000_000
                and h["RestartPolicy"]["Name"] == "no" and h["AutoRemove"] is False
                and h["LogConfig"]["Type"] == "none" and type(a["RestartCount"]) is int and a["RestartCount"] == 0,
                "worker_profile_invalid")
        networks = a["NetworkSettings"]["Networks"]
        # Before start / after exit Docker may retain an unpopulated endpoint.
        # HostConfig pins the network; no live worker endpoint claim is issued.
        require(len(networks) == 1 and set(networks) <= {self.policy.network_id, "tc-mvp-" + self.policy.scope}
                and next(iter(networks.values()))["NetworkID"] in ("", self.policy.network_id),
                "worker_profile_invalid")

    def observe(self, attempt_id):
        execution_uuid = str(uuid4())
        if not self._lock.acquire(blocking=False):
            return Observation("unknown", "busy", None, execution_uuid, self.policy.verifier_image)
        try:
            try:
                return self._run(attempt_id, execution_uuid)
            except Exception:
                return Observation("unknown", "worker_unavailable", None, execution_uuid, self.policy.verifier_image)
        finally:
            self._lock.release()

    def _run(self, attempt_id, execution_uuid):
        with ExitStack() as resources:
            return self._execute(attempt_id, execution_uuid, resources)

    def _execute(self, attempt_id, execution_uuid, resources):
        state, reason = "unknown", "disabled"
        execution = binding = None
        claim = stream = None
        worker_id = None
        create_attempted = False
        cleanup_ok = True
        name = None
        self.deadline = time.monotonic() + RUN_SECONDS
        evidence_deadline = self.deadline
        try:
            if not self.enabled:
                raise Refused("disabled")
            require(type(attempt_id) is int and 0 < attempt_id < 2**63, "authorization_unknown")
            try:
                execution = self.read_attempt(attempt_id)
            except Exception:
                raise Refused("authorization_unknown") from None
            require(type(execution) is Execution and execution.attempt_id == attempt_id, "authorization_unknown")
            p = self.policy
            require(execution.daemon_id == p.daemon_id and execution.network_id == p.network_id, "stale_execution")
            network = ipaddress.IPv4Network(p.subnet)
            require(ipaddress.IPv4Address(execution.ip) in network.hosts(), "network_unapproved")
            # Protected diagnostic artifact doubles as a simple O_EXCL run claim.
            directory = self.artifact_dir.stat()
            require(not self.artifact_dir.is_symlink() and directory.st_uid == os.geteuid()
                    and directory.st_mode & 0o077 == 0, "artifact_unavailable")
            try:
                fd = os.open(self.artifact_dir / (execution.run_id + ".json"),
                             os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            except FileExistsError:
                raise Refused("replay") from None
            claim = resources.enter_context(os.fdopen(fd, "wb"))
            claim.write(json.dumps({"http": "unknown", "reason": "in_progress", "academic_pass": False,
                                    "runtime": asdict(execution), "execution_uuid": execution_uuid}).encode())
            claim.flush()
            os.fsync(claim.fileno())
            require(getattr(self.api, "base_url", "") == "http+docker://localhost", "worker_unavailable")
            require(self._call(self.api.info)["ID"] == p.daemon_id, "daemon_mismatch")
            self._target(execution)
            self._network(execution)
            image = self._call(self.api.inspect_image, p.verifier_image)
            require(image["Id"] == p.verifier_image and not image["Config"].get("Volumes"), "image_unavailable")
            env = dict(item.split("=", 1) for item in image["Config"].get("Env", []))
            require(not any(k.startswith(("LD_", "DYLD_")) or k in ("PYTHONPATH", "PYTHONHOME") for k in env), "image_unavailable")
            request = worker.validate({"policy": worker.POLICY, "execution_uuid": execution_uuid, "runtime": asdict(execution)})
            env.update({"LANG": "C", "LC_ALL": "C", "TC_MVP_REQUEST": json.dumps(request, separators=(",", ":"))})
            host = self.api.create_host_config(
                network_mode=p.network_id, read_only=True, cap_drop=["ALL"], cap_add=[],
                privileged=False, security_opt=["no-new-privileges:true"], ipc_mode="private",
                mem_limit=64 * 1024**2, pids_limit=16, nano_cpus=250_000_000,
                restart_policy={"Name": "no"}, auto_remove=False,
                log_config=LogConfig(type="none"),
            )
            name = "tc-mvp-check-" + execution.run_id
            create_attempted = True
            created = self._call(self.api.create_container, image=p.verifier_image, name=name,
                                 entrypoint=ENTRY, command=[], user="65532:65532", environment=env,
                                 stdin_open=False, tty=False, host_config=host,
                                 labels=self._labels(execution, execution_uuid))
            worker_id = created["Id"]
            require(worker.full_id(worker_id) and worker_id != execution.container_id, "worker_unavailable")
            a = self._call(self.api.inspect_container, worker_id)
            require(a["Id"] == worker_id, "worker_profile_invalid")
            self._profile(a, execution, execution_uuid, name, env)
            require(a["State"]["Status"] == "created", "worker_unavailable")
            require(self.read_attempt(attempt_id) == execution, "stale_execution")
            stream = self._call(self.api.attach_socket, worker_id,
                                params={"stdout": 1, "stderr": 1, "stream": 1, "logs": 0})
            self._call(self.api.start, worker_id)
            stdout, stderr = _read_attach(stream, self.deadline)
            require(not stderr, "verifier_result_invalid")
            waited = self._call(self.api.wait, worker_id, timeout=min(API_SECONDS, max(0.001, self.deadline - time.monotonic())), condition="not-running")
            require(type(waited["StatusCode"]) is int and waited["StatusCode"] == 0 and not waited.get("Error"), "worker_unavailable")
            a = self._call(self.api.inspect_container, worker_id)
            require(a["Id"] == worker_id, "worker_profile_invalid")
            self._profile(a, execution, execution_uuid, name, env)
            require(a["State"]["Status"] == "exited" and a["State"]["Running"] is False
                    and type(a["State"]["ExitCode"]) is int and a["State"]["ExitCode"] == 0
                    and not a["State"].get("OOMKilled"), "worker_unavailable")
            reply = worker.decode(stdout, worker.STDOUT_LIMIT)
            require(type(reply) is dict and set(reply) == {"binding", "http", "reason"}
                    and reply["binding"] == request, "verifier_result_invalid")
            worker.validate(reply["binding"])
            require((reply["http"], reply["reason"]) in worker.REASONS, "verifier_result_invalid")
            self._target(execution)
            self._network(execution, worker_id)
            require(self._call(self.api.info)["ID"] == p.daemon_id, "daemon_mismatch")
            require(self.read_attempt(attempt_id) == execution, "stale_execution")
            state, reason, binding = reply["http"], reply["reason"], execution
        except Refused as error:
            state, reason = "unknown", str(error) if str(error) in UNKNOWN else "worker_unavailable"
        except (TimeoutError, RequestTimeout):
            state, reason = "unknown", "timeout"
        except Exception:
            state, reason = "unknown", "worker_unavailable"
        finally:
            if stream is not None:
                try:
                    stream.close()
                except Exception:
                    cleanup_ok = False
            if create_attempted:
                try:
                    self.deadline = time.monotonic() + CLEANUP_SECONDS
                    try:
                        # Name lookup ONLY recovers our create's lost response;
                        # target lookup always uses its pinned full Docker ID.
                        a = self._call(self.api.inspect_container, worker_id or name)
                    except NotFound:
                        a = None
                        # A create request may still be in flight after a lost
                        # response; absence on one read is not cleanup proof.
                        if worker_id is None:
                            cleanup_ok = False
                    if a is not None:
                        require(self._owned(a, execution, execution_uuid, name)
                                and (worker_id is None or a["Id"] == worker_id), "cleanup_unknown")
                        worker_id = a["Id"]
                        self._call(self.api.remove_container, worker_id, force=True, v=False)
                        try:
                            self._call(self.api.inspect_container, worker_id)
                        except NotFound:
                            pass
                        else:
                            raise Refused("cleanup_unknown")
                except Exception:
                    cleanup_ok = False
        if not cleanup_ok:
            state, reason, binding = "unknown", "cleanup_unknown", None
        elif binding is not None:
            try:
                self.deadline = evidence_deadline
                self._target(execution)
                self._network(execution)
                require(self._call(self.api.info)["ID"] == self.policy.daemon_id, "daemon_mismatch")
                require(self.read_attempt(attempt_id) == execution, "stale_execution")
                require(time.monotonic() < evidence_deadline, "timeout")
            except Refused as error:
                state, reason, binding = "unknown", str(error) if str(error) in UNKNOWN else "worker_unavailable", None
            except Exception:
                state, reason, binding = "unknown", "stale_execution", None
        result = Observation(state, reason, binding, execution_uuid, self.policy.verifier_image, worker_id)
        if claim is not None:
            temporary = None
            try:
                def save(file, value):
                    encoded = json.dumps(asdict(value), separators=(",", ":")).encode()
                    require(len(encoded) <= 8192, "artifact_unavailable")
                    file.seek(0)
                    file.write(encoded)
                    file.truncate()
                    file.flush()
                    os.fsync(file.fileno())
                with tempfile.NamedTemporaryFile(dir=self.artifact_dir, prefix=execution.run_id + ".", delete=False) as completed:
                    temporary = Path(completed.name)
                    save(completed, result)
                    if result.binding is not None and time.monotonic() >= evidence_deadline:
                        result = Observation("unknown", "timeout", None, execution_uuid, self.policy.verifier_image, worker_id)
                        save(completed, result)
                # In-progress claim remains unknown if writing/fsync fails.
                os.replace(temporary, self.artifact_dir / (execution.run_id + ".json"))
                temporary = None
            except Exception:
                result = Observation("unknown", "artifact_unavailable", None, execution_uuid, self.policy.verifier_image, worker_id)
            finally:
                if temporary is not None:
                    try:
                        temporary.unlink(missing_ok=True)
                    except OSError:
                        result = Observation("unknown", "artifact_unavailable", None, execution_uuid, self.policy.verifier_image, worker_id)
        return result
