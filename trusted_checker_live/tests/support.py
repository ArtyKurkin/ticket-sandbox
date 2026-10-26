from dataclasses import replace
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
from docker.types import HostConfig
from trusted_checker_runtime.tests.support import Lab, uuid
from trusted_checker_runtime.contracts import Resource, ProvisionRequest, RunRequest
from trusted_checker_runtime.journal import RuntimeJournal
from trusted_checker_runtime.live_contract import LIVE_POLICY, LIVE_RUNNER, LIVE_TARGET
from trusted_checker_runtime.profiles import EGRESS_CASES
from trusted_checker_shadow.policy import digest
from trusted_checker_runtime.journal import body
from trusted_checker_live.adapter import TrustedDockerAdapter
from trusted_checker_live.composition import LiveRuntime
from trusted_checker_live.egress import (IndependentNetworkValidator, InstalledEgressEnforcer, PortBinding, compile_rules)
from trusted_checker_live.recovery import ExactCleanup
from trusted_checker_live.runner import packet
from trusted_checker_live.signing import LocalSigner
from trusted_checker_live.transport import DaemonWitness, ExplicitUnixEndpoint


class MockAPI:
    """SDK-shaped in-memory boundary. Never constructs a Docker client."""
    def __init__(self, lab):
        self.lab, self.calls, self.objects = lab, [], {}
        self.timeout = 3.0
        self.creates = self.starts = self.removes = 0
        self.raw_hook = None
        self.firewall_active = False
        self.http = packet(lab.network.target_ipv4, transport='refused')
        self.released = False

    def info(self):
        self.calls.append('info'); return {'ID': self.lab.daemon.daemon_id}

    def inspect_image(self, identifier):
        self.calls.append('image'); return {'Id': identifier, 'Config': {'Labels':
            {'tc-shadow.checker-source': self.lab.approval.checker_source_digest}}}

    def create_host_config(self, **kwargs):
        config = HostConfig(version='1.45', **kwargs)
        config.setdefault('Privileged', False)
        config.setdefault('ReadonlyRootfs', False)
        return config

    def create_container(self, **kwargs):
        self.calls.append('raw_create'); self.creates += 1
        target = kwargs['labels']['tc-shadow.domain'] == Resource.TARGET.value
        identifier = self.lab.target_id if target else format(self.creates, '064x')
        config = {'User': kwargs['user'], 'Env': kwargs['environment'], 'Entrypoint': kwargs['entrypoint'],
                  'Cmd': kwargs['command'], 'WorkingDir': kwargs['working_dir'], 'Labels': kwargs['labels'],
                  'Tty': kwargs['tty'], 'OpenStdin': kwargs['stdin_open']}
        self.objects[identifier] = {'Id': identifier, 'Image': kwargs['image'], 'Config': config,
            'HostConfig': kwargs['host_config'], 'Mounts': [], 'RestartCount': 0,
            'State': {'Status': 'created', 'Running': False, 'Paused': False, 'Restarting': False, 'Dead': False,
                      'Pid': 0, 'StartedAt': '0001-01-01T00:00:00Z'},
            'NetworkSettings': {'Networks': {self.lab.network.network_name:
                {'NetworkID': '', 'EndpointID': '', 'IPAddress': ''}}}}
        response = {'Id': identifier, 'Warnings': []}
        if self.raw_hook:
            return self.raw_hook(response)
        return response

    def inspect_container(self, identifier):
        self.calls.append('inspect:'+identifier)
        return self.objects[identifier]

    def start(self, identifier):
        self.calls.append('start:'+identifier); self.starts += 1
        attrs = self.objects[identifier]
        target = attrs['Config']['Labels']['tc-shadow.domain'] == Resource.TARGET.value
        attrs['State'].update(Status='running', Running=True, Pid=111 if target else 112, StartedAt=self.lab.clock.docker())
        ep = next(iter(attrs['NetworkSettings']['Networks'].values()))
        ep.update(NetworkID=self.lab.network.network_id, EndpointID=('f' if target else '9')*64,
                  IPAddress=self.lab.network.target_ipv4 if target else self.lab.network.runner_ipv4,
                  MacAddress='02:42:ac:1e:00:02' if target else '02:42:ac:1e:00:03')
        if not target:
            # EXPLICIT TEST FIXTURE simulates an independently approved installer.
            self.firewall_active = True

    def inspect_network(self, identifier):
        self.calls.append('network')
        from ipaddress import IPv4Network
        containers = {}
        for key, obj in self.objects.items():
            ep = next(iter(obj['NetworkSettings']['Networks'].values()))
            if ep['EndpointID']:
                containers[key] = {'EndpointID': ep['EndpointID'], 'IPv4Address': ep['IPAddress']+'/24'}
        return {'Id': identifier, 'Name': self.lab.network.network_name, 'Driver': 'bridge', 'Internal': True,
                'EnableIPv6': False, 'IPAM': {'Config': [{'Subnet': self.lab.network.subnet,
                'Gateway': str(IPv4Network(self.lab.network.subnet).network_address+1)}]},
                'Options': {'com.docker.network.bridge.name': 'tcsh0'}, 'Containers': containers}

    def attach_socket(self, identifier, params):
        self.calls.append('attach')
        def send(raw):
            assert raw in (b'PROBE\n', b'FINISH\n')
            if raw == b'PROBE\n': self.released = True
        return SimpleNamespace(settimeout=lambda t: None, sendall=send, close=lambda: None)

    def wait(self, identifier, timeout):
        self.calls.append('wait'); assert self.released
        self.objects[identifier]['State'].update(Status='exited', Running=False, Pid=0, ExitCode=0)
        return {'StatusCode': 0}

    def logs(self, identifier, **kwargs):
        self.calls.append('logs')
        return iter([json.dumps(self.http).encode()])

    def remove_container(self, identifier, **kwargs):
        self.calls.append('remove:'+identifier); self.removes += 1
        target = self.objects[identifier]['Config']['Labels']['tc-shadow.domain'] == Resource.TARGET.value
        del self.objects[identifier]
        if not target:
            self.firewall_active = False

    def remove_owned_raw(self, identifier):
        self.remove_container(identifier, force=True, v=False)
        return 204

    def close(self):
        pass


class HostFixture:
    def __init__(self, lab):
        self.lab, self.ports = lab, ()

    def snapshot(self, approval, target, runner):
        self.ports = tuple(PortBinding('vethTarget' if ep.container_id == target.container_id else 'vethRunner',
            11 if ep.container_id == target.container_id else 12, ep.container_id, ep.endpoint_id,
            '02:42:ac:1e:00:02' if ep.container_id == target.container_id else '02:42:ac:1e:00:03', ep.ipv4)
            for ep in target.endpoints+((runner.endpoint,) if runner is not None and runner.endpoint else ()))
        return dict(network_id=approval.network.network_id, bridge='tcsh0', ports=self.ports,
                    bridge_names=('tcsh0',), br_netfilter=False, observed_at=self.lab.clock(), daemon=approval.daemon)


class RuleFixture:
    def __init__(self, lab, host):
        self.lab, self.host = lab, host

    def read(self):
        ports = self.host.ports if self.lab.api.firewall_active else ()
        return compile_rules(self.lab.approval, ports)


class ActiveFixture:
    def __init__(self, clock):
        self.clock = clock

    def measure(self, approval, target, runner, ports):
        return tuple(dict(case=case, verified=True, namespace_binding=digest(body(runner)),
                          capture_digest='a'*64, observed_at=self.clock()) for case in EGRESS_CASES)


class LiveLab(Lab):
    def __init__(self):
        super().__init__()
        witness = DaemonWitness(uuid(), 123, 0, 12345, 1, 456)
        self.endpoint = ExplicitUnixEndpoint('endpoint:unit', '/run/tc-shadow/docker.sock', witness)
        self.daemon = replace(self.daemon, endpoint_config_digest=self.endpoint.digest)
        self.approval = replace(self.approval, approval_uuid=uuid(), daemon=self.daemon, policy_id=LIVE_POLICY.policy_id,
            policy_version=2, policy_digest=LIVE_POLICY.digest, schema_version=2, authority_mode='live_runtime_v2',
            target_profile_digest=LIVE_TARGET.digest, runner_profile_digest=LIVE_RUNNER.digest)
        self.journal = RuntimeJournal(Path(self.tmp.name)/'live.runtime.sqlite3', live=True)
        self.authority = self.new_authority()
        self.authority.register_approval(self.sign(self.approval))
        self.api = MockAPI(self)
        self.factory = Mock(return_value=self.api)
        signer = lambda role: LocalSigner(next(g for g in self.grants if g.role == role))
        self.adapter = TrustedDockerAdapter(self.authority, self.approval.approval_uuid, self.endpoint, signer('adapter'),
                    api_factory=self.factory, witness_reader=lambda e: e.witness, monotonic=self.clock)
        enforcer_host, validator_host = HostFixture(self), HostFixture(self)
        self.enforcer_checker = IndependentNetworkValidator(RuleFixture(self, enforcer_host), enforcer_host,
                                    signer('egress'), self.clock, active_provider=ActiveFixture(self.clock))
        self.validator = IndependentNetworkValidator(RuleFixture(self, validator_host), validator_host,
                                    signer('validator'), self.clock, active_provider=ActiveFixture(self.clock))
        self.enforcer = InstalledEgressEnforcer(self.enforcer_checker, signer('egress'), self.clock)
        self.cleanup_agent = ExactCleanup(self.adapter, signer('recovery'))
        self.runtime = LiveRuntime(self.authority, self.adapter, self.enforcer, self.validator, self.cleanup_agent)

    def provision_live(self):
        self.authority.set_enabled(True)
        self.request = ProvisionRequest(uuid(), self.approval.approval_uuid, self.attempt)
        self.enrollment = self.runtime.provision_new(self.request)
        return self.enrollment

    def submit_live(self):
        self.run_request = RunRequest(uuid(), self.enrollment.enrollment_uuid, self.attempt, uuid())
        return self.runtime.submit(self.run_request, self.enrollment)
