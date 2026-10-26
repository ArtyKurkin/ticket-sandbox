"""Independent READ-ONLY Linux topology correlation, using host binaries only.

No setns in the calling process, target mount/PID namespace, task filesystem,
Docker exec, firewall mutation, generic command or discovered endpoint is used.
"""
import json
from pathlib import Path
import subprocess
from trusted_checker_runtime.profiles import Denied, require
from .egress import PortBinding
from .transport import observe_linux_peer


class LinuxHostInventory:
    def __init__(self, api, endpoint, clock, *, witness_reader=observe_linux_peer):
        self.api, self.endpoint, self.clock, self.witness_reader = api, endpoint, clock, witness_reader

    def _container(self, approval, observed, bridge_ports):
        self.api.timeout = 3.0
        attrs = self.api.inspect_container(observed.container_id)
        state = attrs['State']
        expected_start = observed.started_at
        expected_endpoints = observed.endpoints if hasattr(observed, 'endpoints') else ((observed.endpoint,) if observed.endpoint else ())
        if not expected_endpoints:
            require(state['Status'] == 'created', 'validator_created_runner_changed')
            return None
        # No post-exit namespace assumption. The probe/result/finalize handshake
        # keeps the runner alive through independent active checks; final exit
        # configuration is validated separately before terminal publication.
        require(state['Running'] is True and state['Status'] == 'running' and state['StartedAt'] == expected_start and
                attrs['RestartCount'] == observed.restart_count and attrs['Id'] == observed.container_id and
                not any(state.get(k) for k in ('Paused', 'Restarting', 'Dead')), 'live_namespace_unavailable')
        pid = state['Pid']
        require(type(pid) is int and pid > 1, 'validator_pid_invalid')
        namespace = Path('/proc')/str(pid)/'ns/net'
        before = namespace.stat().st_ino
        started = (Path('/proc')/str(pid)/'stat').read_text().rsplit(')', 1)[1].split()[19]
        result = subprocess.run(['/usr/bin/nsenter', '--net='+str(namespace), '/usr/sbin/ip', '-j', '-d', 'link', 'show'],
            cwd='/', env={'PATH': '/usr/sbin:/usr/bin:/sbin:/bin'}, capture_output=True, timeout=3, check=False)
        require(result.returncode == 0 and len(result.stdout) <= 65536, 'validator_link_read_failed')
        links = [item for item in json.loads(result.stdout) if item['ifname'] != 'lo']
        require(len(links) == 1, 'validator_extra_namespace_interface')
        peer = links[0]
        host_port = next((p for p in bridge_ports if int((p/'ifindex').read_text()) == peer['link_index']), None)
        require(host_port is not None and int((host_port/'iflink').read_text()) == peer['ifindex'], 'veth_peer_unproven')
        endpoints = attrs['NetworkSettings']['Networks']
        require(len(endpoints) == 1, 'validator_extra_network')
        ep = next(iter(endpoints.values()))
        expected = expected_endpoints[0]
        require(ep['NetworkID'] == approval.network.network_id and ep['EndpointID'] == expected.endpoint_id and
                ep['IPAddress'] == expected.ipv4 and ep['MacAddress'] == peer['address'], 'validator_endpoint_mismatch')
        require(namespace.stat().st_ino == before and
                (Path('/proc')/str(pid)/'stat').read_text().rsplit(')',1)[1].split()[19] == started,
                'validator_namespace_generation_changed')
        after = self.api.inspect_container(observed.container_id)
        require(after['State'] == state and after['NetworkSettings'] == attrs['NetworkSettings'] and
                after['RestartCount'] == attrs['RestartCount'], 'validator_runtime_changed')
        return PortBinding(host_port.name, peer['link_index'], observed.container_id, expected.endpoint_id,
                           peer['address'], expected.ipv4)

    def snapshot(self, approval, target, runner):
        try:
            require(self.endpoint.digest == approval.daemon.endpoint_config_digest and
                    self.witness_reader(self.endpoint) == self.endpoint.witness, 'validator_daemon_session_changed')
            self.api.timeout = 3.0
            require(self.api.info()['ID'] == approval.daemon.daemon_id, 'validator_daemon_id_mismatch')
            net = Path('/sys/class/net')
            bridges = tuple(sorted(p.name for p in net.iterdir() if (p/'bridge').is_dir()))
            port_paths = tuple((net/'tcsh0/brif').iterdir())
            resolved = tuple(p.resolve() for p in port_paths)
            ports = tuple(p for p in (self._container(approval, target, resolved),
                    self._container(approval, runner, resolved) if runner is not None else None) if p is not None)
            require({p.interface for p in ports} == {p.name for p in port_paths}, 'validator_unowned_bridge_port')
            checks = [Path('/proc/sys/net/bridge')/name for name in
                      ('bridge-nf-call-iptables', 'bridge-nf-call-ip6tables', 'bridge-nf-call-arptables')]
            br_netfilter = any(p.exists() and p.read_text().strip() != '0' for p in checks)
            require(self.witness_reader(self.endpoint) == self.endpoint.witness, 'validator_daemon_session_changed')
            return dict(network_id=approval.network.network_id, bridge='tcsh0', ports=ports, bridge_names=bridges,
                        br_netfilter=br_netfilter, observed_at=self.clock(), daemon=approval.daemon)
        except (OSError, KeyError, ValueError, TypeError, subprocess.SubprocessError):
            raise Denied('host_inventory_unconfirmed') from None
