"""Closed network proof domain; no conversion to a live Docker authorization."""
from dataclasses import asdict, dataclass
import ipaddress
from trusted_checker_runtime.contracts import DaemonIdentity, atom, full_id, scope, stamp, uid
from trusted_checker_runtime.profiles import fixed, require
from trusted_checker_shadow.policy import digest

MODE = 'offline_network_mock_v3'
CASES = ('allow_target_8080', 'deny_other_target_ports', 'deny_other_ipv4', 'deny_host',
         'deny_metadata', 'deny_db_redis_django', 'deny_dns', 'deny_ipv6', 'deny_spoofing', 'deny_extra_attachment')


def private_ip(value):
    try:
        ip = ipaddress.IPv4Address(value)
        require(str(ip) == value and any(ip in ipaddress.IPv4Network(n) for n in
                ('10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16')), 'private_ipv4_required')
    except (ValueError, TypeError):
        require(False, 'private_ipv4_required')


@dataclass(frozen=True)
class NamespaceIdentity:
    container_id: str
    pid: int
    process_start_ticks: int
    netns_inode: int
    docker_started_at: str
    restart_count: int
    endpoint_id: str
    interface: str
    ifindex: int
    peer_ifindex: int
    mac: str
    ipv4: str

    def __post_init__(self):
        from trusted_checker_runtime.contracts import docker_time
        import re
        full_id(self.container_id); full_id(self.endpoint_id)
        docker_time(self.docker_started_at)
        require(all(type(n) is int and n > 0 for n in (self.pid, self.process_start_ticks, self.netns_inode,
                self.ifindex, self.peer_ifindex)) and self.pid > 1 and self.restart_count == 0 and
                type(self.restart_count) is int, 'namespace_identity_invalid')
        require(re.fullmatch(r'veth[a-zA-Z0-9]{1,10}', self.interface) and
                re.fullmatch(r'02:[0-9a-f]{2}(?::[0-9a-f]{2}){4}', self.mac), 'physical_port_invalid')
        private_ip(self.ipv4)


@dataclass(frozen=True)
class NetworkBinding:
    host_boot_uuid: str
    host_identity_digest: str
    host_netns_inode: int
    daemon: DaemonIdentity
    scope: str
    runtime_approval_digest: str
    runtime_binding_uuid: str
    generation_uuid: str
    network_id: str
    bridge_name: str
    bridge_ifindex: int
    bridge_mac: str
    target: NamespaceIdentity
    runner: NamespaceIdentity
    gateway_ipv4: str
    other_ipv4: str
    db_ipv4: str
    redis_ipv4: str
    django_ipv4: str

    def __post_init__(self):
        uid(self.host_boot_uuid); full_id(self.host_identity_digest)
        full_id(self.runtime_approval_digest); uid(self.runtime_binding_uuid); uid(self.generation_uuid)
        full_id(self.network_id); scope(self.scope)
        require(type(self.daemon) is DaemonIdentity and self.bridge_name == 'tcsh0' and
                type(self.bridge_ifindex) is int and self.bridge_ifindex > 0 and
                type(self.host_netns_inode) is int and self.host_netns_inode > 0, 'host_binding_invalid')
        self.daemon.__post_init__()
        require(type(self.target) is NamespaceIdentity and type(self.runner) is NamespaceIdentity, 'namespace_required')
        self.target.__post_init__(); self.runner.__post_init__()
        require(self.target.container_id != self.runner.container_id and self.target.netns_inode != self.runner.netns_inode
                and self.target.ifindex != self.runner.ifindex and self.target.interface != self.runner.interface
                and self.target.mac != self.runner.mac, 'namespace_alias_rejected')
        import re
        require(re.fullmatch(r'(?:[0-9a-f]{2}:){5}[0-9a-f]{2}', self.bridge_mac), 'bridge_mac_invalid')
        ips = (self.target.ipv4, self.runner.ipv4, self.gateway_ipv4, self.other_ipv4,
               self.db_ipv4, self.redis_ipv4, self.django_ipv4)
        for value in ips: private_ip(value)
        require(len(set(ips)) == len(ips), 'negative_endpoint_alias_rejected')

    @property
    def digest(self):
        return digest(asdict(self))


@dataclass(frozen=True)
class NetworkPolicy:
    policy_id: str = 'dedicated-host-network-v3'
    version: int = 3
    mode: str = MODE
    dedicated_host_required: bool = True
    bridge_priority: int = 0
    inet_priority: int = -310
    packet_limit: int = 256
    frame_bytes: int = 128
    window_seconds: float = 0.1
    observation_age: float = 3.0
    apply_seconds: float = 1.0
    matrix_seconds: float = 2.0

    def __post_init__(self): fixed(self)

    @property
    def digest(self): return digest(asdict(self))


POLICY = NetworkPolicy()


@dataclass(frozen=True)
class NetworkApproval:
    approval_uuid: str
    operator: str
    binding: NetworkBinding
    bootstrap_digest: str
    active_digest: str
    created_at: float
    expires_at: float
    policy_digest: str = POLICY.digest
    mode: str = MODE

    def __post_init__(self):
        uid(self.approval_uuid); atom(self.operator, 'operator:')
        require(type(self.binding) is NetworkBinding, 'network_binding_required')
        self.binding.__post_init__()
        for value in (self.bootstrap_digest, self.active_digest, self.policy_digest): full_id(value)
        stamp(self.created_at); stamp(self.expires_at)
        require(0 < self.expires_at-self.created_at <= 3600 and self.policy_digest == POLICY.digest and self.mode == MODE,
                'network_approval_invalid')

    @property
    def scope(self): return self.binding.scope


@dataclass(frozen=True)
class HostSnapshot:
    binding: NetworkBinding
    bridge_names: tuple[str, ...]
    physical_ports: tuple[str, ...]
    runner_interfaces: tuple[int, ...]
    target_interfaces: tuple[int, ...]
    netlink_sequence_start: int
    netlink_sequence_end: int
    netlink_lost: int
    observed_at: float
    foreign_bridge_hooks: bool = False
    br_netfilter: bool = False
    bridge_conntrack: bool = True

    def __post_init__(self):
        require(type(self.binding) is NetworkBinding and self.bridge_names == ('tcsh0',) and
                self.physical_ports == (self.binding.target.interface, self.binding.runner.interface) and
                self.runner_interfaces == (self.binding.runner.peer_ifindex,) and
                self.target_interfaces == (self.binding.target.peer_ifindex,), 'unapproved_topology')
        require(all(type(n) is int and n >= 0 for n in (self.netlink_sequence_start, self.netlink_sequence_end, self.netlink_lost))
                and self.netlink_sequence_end >= self.netlink_sequence_start and type(self.foreign_bridge_hooks) is bool,
                'netlink_evidence_invalid')
        require(self.br_netfilter is False and self.bridge_conntrack is True,'kernel_network_profile_unproven')
        stamp(self.observed_at)


@dataclass(frozen=True)
class InstallReceipt:
    receipt_uuid: str
    context_uuid: str
    scope: str
    binding_digest: str
    operation: str
    transaction_uuid: str
    rules_digest: str
    generation: int
    observed_at: float
    mode: str = MODE

    def __post_init__(self):
        uid(self.receipt_uuid); uid(self.context_uuid); uid(self.transaction_uuid); scope(self.scope)
        full_id(self.binding_digest); full_id(self.rules_digest); stamp(self.observed_at)
        require(self.operation in ('bootstrap', 'active', 'rollback') and type(self.generation) is int and
                self.generation > 0 and self.mode == MODE, 'install_receipt_invalid')
