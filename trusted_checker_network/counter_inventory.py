"""Extended inventory DATA contract. No host reads or continuity attestation."""
from dataclasses import asdict, dataclass
import ipaddress

from trusted_checker_runtime.contracts import full_id, stamp, uid
from trusted_checker_runtime.profiles import require
from trusted_checker_shadow.policy import digest
from .contracts import NetworkBinding


REQUIREMENTS = (
    'dedicated_vm_no_foreign_socket_holders',
    'only_reviewed_daemon_and_installer_can_mutate_network',
    'all_trusted_writers_serialized_until_publication',
    'runner_target_drop_all_caps_nnp_no_host_socket_mounts',
    'no_inherited_external_network_fds',
    'no_unreviewed_userns_setns_or_privileged_helper_access',
    'protected_host_binaries_keys_journal_and_review',
    'invalidate_on_boot_daemon_config_permission_or_writer_drift',
)


@dataclass(frozen=True)
class ControlModel:
    review_digest: str
    writer_epoch_uuid: str
    writers: tuple[str, ...]
    requirements: tuple = REQUIREMENTS
    basis: str = 'offline_review_fixture_only'

    def __post_init__(self):
        full_id(self.review_digest); uid(self.writer_epoch_uuid)
        require(type(self.writers) is tuple and self.writers == ('daemon:fixture', 'installer:fixture') and
                type(self.requirements) is tuple and self.requirements == REQUIREMENTS and
                self.basis == 'offline_review_fixture_only', 'counter_control_model_invalid')


@dataclass(frozen=True)
class Paths:
    """Canonical complete arrays, including loopback, all route tables and RPDB.

    Interface: name,index,kind,master,peer,MAC,addresses.
    Route: family,table,prefix,type,device,gateway. Rule: family,priority,table.
    Attachments: kind,device,program/object identity (empty in this profile).
    """
    role: str
    netns_inode: int
    interfaces: tuple
    routes: tuple
    policy_rules: tuple
    attachments: tuple = ()

    def __post_init__(self):
        require(self.role in ('host', 'target', 'runner') and type(self.netns_inode) is int and
                self.netns_inode > 0, 'counter_namespace_invalid')
        for value, width, limit in ((self.interfaces, 7, 16), (self.routes, 6, 32),
                                    (self.policy_rules, 3, 16), (self.attachments, 3, 16)):
            require(type(value) is tuple and len(value) <= limit and
                    all(type(row) is tuple and len(row) == width for row in value), 'counter_inventory_shape')
        # Exact comparison against generated layout also checks every scalar type.


def expected_paths(binding, subnet):
    require(type(binding) is NetworkBinding, 'counter_binding_required')
    binding.__post_init__()
    network = ipaddress.IPv4Network(subnet, strict=True)
    require(all(ipaddress.IPv4Address(n.ipv4) in network for n in (binding.target, binding.runner)),
            'counter_subnet_mismatch')
    lo = ('lo', 1, 'loopback', 0, 0, '00:00:00:00:00:00', ('127.0.0.1/8', '::1/128'))
    rules = tuple((family, priority, table) for family in (4, 6)
                  for priority, table in ((0, 255), (32766, 254), (32767, 253)))
    def routes(ip, dev):
        return ((4, 254, str(network), 'unicast', dev, ''),
                (4, 255, ip+'/32', 'local', dev, ''),
                (4, 255, '127.0.0.0/8', 'local', 'lo', ''),
                (6, 255, '::1/128', 'local', 'lo', ''))
    host = Paths('host', binding.host_netns_inode,
        (lo, (binding.bridge_name, binding.bridge_ifindex, 'bridge', 0, 0, binding.bridge_mac,
               (binding.gateway_ipv4+'/'+str(network.prefixlen),)),
         *((n.interface, n.ifindex, 'veth', binding.bridge_ifindex, n.peer_ifindex, '', ())
           for n in (binding.target, binding.runner))), routes(binding.gateway_ipv4, binding.bridge_name), rules)
    peers = tuple(Paths(role, n.netns_inode,
        (lo, ('eth0', n.peer_ifindex, 'veth', 0, n.ifindex, n.mac, (n.ipv4+'/'+str(network.prefixlen),))),
        routes(n.ipv4, 'eth0'), rules) for role, n in (('target', binding.target), ('runner', binding.runner)))
    return (host, *peers)


@dataclass(frozen=True)
class TopologyObservation:
    context_uuid: str
    scope: str
    binding_digest: str
    writer_epoch_uuid: str
    review_digest: str
    observed_at: float
    binding: NetworkBinding
    paths: tuple[Paths, ...]
    unaccounted_writers: tuple = ()
    external_network_fds: tuple = ()
    br_netfilter: bool = False
    forwarding: bool = False
    origin: str = 'offline_counter_fixture'

    def __post_init__(self):
        uid(self.context_uuid); uid(self.writer_epoch_uuid)
        full_id(self.binding_digest); full_id(self.review_digest); stamp(self.observed_at)
        require(type(self.binding) is NetworkBinding, 'counter_observed_binding_required')
        self.binding.__post_init__()
        require(self.binding_digest == self.binding.digest, 'counter_observed_binding_digest')
        require(type(self.paths) is tuple and len(self.paths) == 3 and all(type(p) is Paths for p in self.paths)
                and self.origin == 'offline_counter_fixture', 'counter_topology_contract')
        for p in self.paths: p.__post_init__()
        require(type(self.unaccounted_writers) is tuple and type(self.external_network_fds) is tuple and
                type(self.br_netfilter) is bool and type(self.forwarding) is bool, 'counter_topology_flags')


def check_topology(observation, approval):
    require(type(observation) is TopologyObservation, 'counter_topology_required')
    observation.__post_init__()
    model = approval.control
    require(observation.context_uuid == approval.context_uuid and observation.scope == approval.scope and
            observation.binding_digest == approval.binding.digest and observation.binding == approval.binding and
            observation.writer_epoch_uuid == model.writer_epoch_uuid and
            observation.review_digest == model.review_digest and not observation.unaccounted_writers and
            not observation.external_network_fds and observation.br_netfilter is False and
            observation.forwarding is False, 'counter_topology_unproven')
    # Canonical JSON preserves bool/int distinction and disallows scalar coercion.
    require(digest([asdict(p) for p in observation.paths]) == digest(
            [asdict(p) for p in expected_paths(approval.binding, approval.runtime.network.subnet)]),
            'counter_unexpected_network_path')
