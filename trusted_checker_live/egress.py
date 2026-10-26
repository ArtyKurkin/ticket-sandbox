"""Render-only nftables design + independent readback/active-evidence validator.

Never applies firewall, creates namespaces, or synthesizes active probe success.
An external approved namespace probe provider is mandatory for live release.
"""
from dataclasses import dataclass
import json
import re
import subprocess
from uuid import uuid4
from trusted_checker_runtime.contracts import EgressEvidence, EgressValidation, Phase
from trusted_checker_runtime.live_contract import LIVE_PREFLIGHT_CASES, live_matrix_digest
from trusted_checker_runtime.profiles import EGRESS_CASES, require, rules_digest
from trusted_checker_shadow.policy import digest
from trusted_checker_runtime.journal import body


@dataclass(frozen=True)
class PortBinding:
    interface: str
    ifindex: int
    container_id: str
    endpoint_id: str
    mac: str
    ipv4: str

    def __post_init__(self):
        from trusted_checker_runtime.contracts import full_id
        require(type(self.interface) is str and re.fullmatch(r'veth[a-zA-Z0-9]{1,10}', self.interface) and
                type(self.ifindex) is int and self.ifindex > 0 and
                re.fullmatch(r'02:[0-9a-f]{2}(?::[0-9a-f]{2}){4}', self.mac), 'port_binding_invalid')
        full_id(self.container_id); full_id(self.endpoint_id)


def match(left, value, op='=='):
    return {'match': {'op': op, 'left': left, 'right': value}}


def payload(protocol, field):
    return {'payload': {'protocol': protocol, 'field': field}}


def compile_rules(approval, ports=()):
    """Native nft JSON transaction TEMPLATE; default drop on ALL bridge paths.

    A dedicated host with no other bridges is required. inet routing/host paths
    are separately denied. br_netfilter must be off (independently verified).
    """
    commands = []
    for family, hooks in (('bridge', ('prerouting', 'input', 'forward', 'output')),
                           ('inet', ('input', 'forward', 'output'))):
        commands.append({'add': {'table': {'family': family, 'name': 'tc_shadow'}}})
        for hook in hooks:
            commands.append({'add': {'chain': {'family': family, 'table': 'tc_shadow', 'name': hook,
                'type': 'filter', 'hook': hook, 'prio': -310, 'policy': 'drop' if family == 'bridge' else 'accept'}}})
    def rule(family, chain, expr):
        commands.append({'add': {'rule': {'family': family, 'table': 'tc_shadow', 'chain': chain, 'expr': expr}}})
    for hook in ('input', 'forward'):
        rule('inet', hook, [match({'meta': {'key': 'iifname'}}, 'tcsh0'), {'drop': None}])
    for hook in ('output', 'forward'):
        rule('inet', hook, [match({'meta': {'key': 'oifname'}}, 'tcsh0'), {'drop': None}])
    require(len(ports) in (0, 2), 'bootstrap_or_exact_two_ports_required')
    if ports:
        target, runner = ports
        for port, ip in ((target, approval.network.target_ipv4), (runner, approval.network.runner_ipv4)):
            port.__post_init__()
            require(port.ipv4 == ip, 'port_ip_mismatch')
        require(target.interface != runner.interface and target.ifindex != runner.ifindex and target.mac != runner.mac,
                'port_alias_rejected')
        # Bind Ethernet/IP sender identity to an independently resolved physical
        # ingress port. No matching IP or MAC alone grants admission.
        for source, dest, response in ((runner, target, False), (target, runner, True)):
            ingress = [match({'meta': {'key': 'iifname'}}, source.interface),
                       match(payload('ether', 'saddr'), source.mac)]
            tcp = ingress + [match(payload('ether', 'daddr'), dest.mac),
                match(payload('ip', 'saddr'), source.ipv4), match(payload('ip', 'daddr'), dest.ipv4),
                match({'&': [payload('ip', 'frag-off'), 16383]}, 0), match({'meta': {'key': 'l4proto'}}, 'tcp'),
                match(payload('tcp', 'sport' if response else 'dport'), 8080)]
            if response:
                tcp += [match({'ct': {'key': 'state'}}, 'established')]
            for hook in ('prerouting', 'forward'):
                expr = tcp + ([match({'meta': {'key': 'oifname'}}, dest.interface)] if hook == 'forward' else [])
                rule('bridge', hook, expr+[{'accept': None}])
            for operation in ('request', 'reply'):
                arp = ingress + [match(payload('arp', 'operation'), operation),
                    match(payload('arp', 'saddr ether'), source.mac),
                    match(payload('arp', 'saddr ip'), source.ipv4), match(payload('arp', 'daddr ip'), dest.ipv4)]
                for hook in ('prerouting', 'forward'):
                    expr = arp+([match({'meta': {'key': 'oifname'}}, dest.interface)] if hook == 'forward' else [])
                    rule('bridge', hook, expr+[{'accept': None}])
    return {'nftables': commands}


def canonical_readback(readback):
    """Compare complete table structure; do not trust a digest supplied by enforcer."""
    require(type(readback) is dict and set(readback) == {'nftables'}, 'nft_readback_invalid')
    objects = []
    for item in readback['nftables']:
        require(type(item) is dict and len(item) == 1, 'nft_readback_invalid')
        if 'metainfo' in item:
            continue
        item = item.get('add', item)
        require(set(item) <= {'table', 'chain', 'rule'} and len(item) == 1, 'unexpected_nft_object')
        kind = next(iter(item))
        data = {k:v for k,v in item[kind].items() if k not in ('handle', 'index', 'position', 'use')}
        objects.append({kind: data})
    return objects


def activation_template(approval, ports):
    """Render an ATOMIC replacement of known bootstrap tables; never apply it."""
    require(len(ports) == 2, 'live_endpoints_required')
    deletes = [{'delete': {'table': {'family': family, 'name': 'tc_shadow'}}} for family in ('bridge', 'inet')]
    return {'nftables': deletes+compile_rules(approval, ports)['nftables']}


class ReadOnlyNftReader:
    """Explicit read-only host port, never called on import and never applies rules."""
    def read(self):
        objects = []
        for family in ('bridge', 'inet'):
            result = subprocess.run(['/usr/sbin/nft', '-j', 'list', 'table', family, 'tc_shadow'],
                                    capture_output=True, check=False, timeout=3)
            require(result.returncode == 0 and len(result.stdout) <= 65536, 'nft_readback_unavailable')
            objects.extend(json.loads(result.stdout)['nftables'])
        return {'nftables': objects}


class IndependentNetworkValidator:
    """Reader and host observer must be independently installed under validator TCB.

    observer returns actual bridge/interface/sysctl/namespace inventory; active
    probe evidence must be collected by a separately reviewed host namespace
    helper. No default active provider exists: absence is a hard release blocker.
    """
    def __init__(self, reader, host_observer, signer, clock, *, active_provider=None):
        self.reader, self.host, self.signer, self.clock = reader, host_observer, signer, clock
        self.active_provider = active_provider

    def check(self, approval, context, phase, target, runner):
        preflight = phase in (Phase.ENROLL, Phase.BEFORE_CREATE, Phase.BEFORE_START)
        inventory = self.host.snapshot(approval, target, runner)
        require(set(inventory) == {'network_id', 'bridge', 'ports', 'bridge_names', 'br_netfilter', 'observed_at', 'daemon'} and
                inventory['network_id'] == approval.network.network_id and inventory['bridge'] == 'tcsh0' and
                inventory['bridge_names'] == ('tcsh0',) and inventory['br_netfilter'] is False and
                inventory['daemon'] == approval.daemon and 0 <= self.clock()-inventory['observed_at'] <= 3,
                'host_topology_unverified')
        ports = inventory['ports']
        expected = target.endpoints + ((runner.endpoint,) if runner is not None and runner.endpoint is not None else ())
        require({(p.container_id, p.endpoint_id, p.ipv4) for p in ports} ==
                {(p.container_id, p.endpoint_id, p.ipv4) for p in expected} and len(ports) == len(expected),
                'host_extra_or_foreign_port')
        active_ports = ()
        if not preflight:
            require(len(ports) == 2 and runner is not None and runner.endpoint is not None, 'live_endpoints_required')
            active_ports = tuple(next(p for p in ports if p.container_id == ep.container_id) for ep in expected)
        expected_rules = compile_rules(approval, active_ports)
        actual = self.reader.read()
        require(canonical_readback(actual) == canonical_readback(expected_rules), 'installed_rules_differ')
        cases = LIVE_PREFLIGHT_CASES if preflight else EGRESS_CASES
        active_digest = None
        if not preflight:
            require(self.active_provider is not None, 'active_namespace_validator_not_installed')
            observations = self.active_provider.measure(approval, target, runner, active_ports)
            require(type(observations) is tuple and tuple(o['case'] for o in observations) == EGRESS_CASES,
                    'negative_matrix_incomplete')
            for observation in observations:
                require(set(observation) == {'case', 'verified', 'namespace_binding', 'capture_digest', 'observed_at'} and
                        observation['verified'] is True and observation['namespace_binding'] == digest(body(runner)) and
                        0 <= self.clock()-observation['observed_at'] <= 3, 'active_probe_unconfirmed')
                from trusted_checker_runtime.contracts import full_id
                full_id(observation['capture_digest'])
            active_digest = digest(observations)
        return {'rules': digest(canonical_readback(actual)), 'inventory': digest(body(inventory)),
                'active': active_digest, 'cases': cases, 'matrix': live_matrix_digest(approval.network, phase)}

    def attest(self, approval, context, phase, target, runner, enforcement):
        checked = self.check(approval, context, phase, target, runner)
        return self.signer.sign(EgressValidation(str(uuid4()), context, approval.scope, self.clock(), phase,
            enforcement.digest, checked['matrix'], checked['cases']))


class InstalledEgressEnforcer:
    """Attests readback, never executes nft/iptables or trusts Internal=true."""
    def __init__(self, checker, signer, clock):
        self.checker, self.signer, self.clock = checker, signer, clock

    def attest(self, approval, context, phase, target, runner):
        checked = self.checker.check(approval, context, phase, target, runner)
        runner_id = None if phase in (Phase.ENROLL, Phase.BEFORE_CREATE) else runner.container_id
        return self.signer.sign(EgressEvidence(str(uuid4()), context, approval.scope, self.clock(), phase,
            digest(body(target)), runner_id, approval.daemon, approval.network.digest,
            approval.network.enforcement_reference, rules_digest(approval.network), digest(checked), True, True, True, True))
