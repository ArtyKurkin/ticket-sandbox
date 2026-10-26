"""Task-specific pilot profiles, independent of the synthetic PoC adapter."""

from dataclasses import asdict, dataclass
import ipaddress

from trusted_checker_shadow.policy import digest


class Denied(ValueError):
    """Constant error codes only; never API bodies or exception messages."""


def require(condition, reason):
    if not condition:
        raise Denied(reason)


@dataclass(frozen=True)
class Limits:
    target_cpu_nanos: int = 1_000_000_000
    target_memory: int = 768 * 1024 * 1024
    target_pids: int = 256
    runner_cpu_nanos: int = 250_000_000
    runner_memory: int = 64 * 1024 * 1024
    runner_pids: int = 32
    run_seconds: float = 8.0
    api_seconds: float = 3.0
    http_seconds: float = 2.0
    max_concurrent_runs: int = 1

    def __post_init__(self):
        fixed(self)


def fixed(value):
    for name, field in value.__dataclass_fields__.items():
        actual = getattr(value, name)
        require(type(actual) is type(field.default) and actual == field.default, "profile_immutable")


@dataclass(frozen=True)
class TargetProfile:
    profile_id: str = "service-bind-localhost-target-v1"
    user: str = "0:0"
    read_only: bool = False
    privileged: bool = False
    cap_drop: tuple = ("ALL",)
    no_new_privileges: bool = True
    pid_mode: str = "private"
    ipc_mode: str = "private"
    host_mounts: int = 0
    docker_socket: bool = False
    tmpfs: tuple = (("/tmp", "rw,noexec,nosuid,nodev,size=128m"),
                    ("/run", "rw,noexec,nosuid,nodev,size=64m"))
    entrypoint: tuple = ()
    command: tuple = ("/start.sh",)
    environment: tuple = ()
    editable_application: bool = True

    def __post_init__(self):
        fixed(self)

    @property
    def digest(self):
        return digest(asdict(self))


@dataclass(frozen=True)
class RunnerProfile:
    profile_id: str = "service-bind-localhost-runner-v1"
    user: str = "10001:10001"
    read_only: bool = True
    privileged: bool = False
    cap_drop: tuple = ("ALL",)
    no_new_privileges: bool = True
    pid_mode: str = "private"
    ipc_mode: str = "private"
    host_mounts: int = 0
    docker_socket: bool = False
    tmpfs: tuple = (("/scratch", "rw,noexec,nosuid,nodev,size=1m,uid=10001,gid=10001,mode=0700"),)
    entrypoint: tuple = ("/usr/local/bin/python", "-I", "/checker/service_bind_peer.py")
    command: tuple = ()
    environment: tuple = ()
    log_bytes: int = 16384
    log_files: int = 1
    protocol_bytes: int = 4096

    def __post_init__(self):
        fixed(self)

    @property
    def digest(self):
        return digest(asdict(self))


@dataclass(frozen=True)
class NetworkProfile:
    network_id: str
    network_name: str
    subnet: str
    target_ipv4: str
    runner_ipv4: str
    enforcement_reference: str
    profile_id: str = "service-bind-localhost-internal-egress-v1"
    internal: bool = True
    driver: str = "bridge"
    dedicated_daemon: bool = True
    target_port: int = 8080
    default_egress: str = "deny"
    enforcement: str = "host_nftables_bridge_v1"

    def __post_init__(self):
        import re
        require(type(self.network_id) is str and re.fullmatch(r"[0-9a-f]{64}", self.network_id) is not None,
                "network_id_invalid")
        require(type(self.network_name) is str and re.fullmatch(r"tc-shadow-pilot-[a-z0-9-]{1,30}", self.network_name)
                is not None, "network_name_not_allowed")
        require(type(self.enforcement_reference) is str and re.fullmatch(r"egress:[a-z0-9-]{1,40}", self.enforcement_reference)
                is not None, "egress_reference_invalid")
        try:
            net = ipaddress.IPv4Network(self.subnet, strict=True)
            target, runner = ipaddress.IPv4Address(self.target_ipv4), ipaddress.IPv4Address(self.runner_ipv4)
        except (ValueError, TypeError):
            raise Denied("network_address_invalid") from None
        require(24 <= net.prefixlen <= 28 and any(net.subnet_of(ipaddress.IPv4Network(base)) for base in
                ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16")), "network_subnet_invalid")
        require(target != runner and all(ip in net and ip not in (net.network_address, net.broadcast_address)
                for ip in (target, runner)) and str(target) == self.target_ipv4 and str(runner) == self.runner_ipv4,
                "network_endpoint_invalid")
        for name in ("profile_id", "internal", "driver", "dedicated_daemon", "target_port", "default_egress", "enforcement"):
            default = self.__dataclass_fields__[name].default
            require(type(getattr(self, name)) is type(default) and getattr(self, name) == default, "network_profile_immutable")

    @property
    def digest(self):
        return digest(asdict(self))


TARGET_PROFILE = TargetProfile()
RUNNER_PROFILE = RunnerProfile()
LIMITS = Limits()

EGRESS_CASES = ("allow_target_8080", "deny_other_target_ports", "deny_other_ipv4", "deny_host",
                "deny_metadata", "deny_db_redis_django", "deny_dns", "deny_ipv6", "deny_spoofing")


def rules_digest(network):
    return digest({"profile": asdict(network), "allow": [network.target_ipv4, 8080],
                   "default": "deny", "l2_anti_spoofing": True})


def matrix_digest(network):
    return digest({"network_profile": network.digest, "cases": EGRESS_CASES,
                   "method": "independent_host_rule_readback_and_active_peer_checks_v1"})
