import base64
import hashlib
import json
from pathlib import Path
import socket
import subprocess
import sys
from unittest import TestCase
from unittest.mock import Mock, patch
from trusted_checker_live import runner
from trusted_checker_live.protocol import decode
from trusted_checker_live.egress import compile_rules, canonical_readback, PortBinding
from trusted_checker_runtime.live_contract import LIVE_POLICY
from trusted_checker_runtime.contracts import Phase
from trusted_checker_runtime.profiles import Denied
from .support import LiveLab


class WireSocket:
    def __init__(self, data=b'', fault=None, clock=None):
        self.data, self.fault, self.clock, self.sent, self.connects = data, fault, clock, [], []
        self.closed = False

    def settimeout(self, value):
        assert 0 < value <= 2

    def connect(self, endpoint):
        self.connects.append(endpoint)
        if self.fault:
            raise self.fault

    def sendall(self, raw):
        self.sent.append(raw)

    def recv(self, count):
        data, self.data = self.data[:count], self.data[count:]
        if self.clock: self.clock.advance(.01)
        return data

    def close(self):
        self.closed = True


class RunnerTests(TestCase):
    def probe(self, wire):
        factory = Mock(return_value=wire)
        with patch.object(socket, 'getaddrinfo', side_effect=AssertionError('DNS forbidden')):
            result = runner.probe('172.30.0.2', socket_factory=factory)
        factory.assert_called_once_with(socket.AF_INET, socket.SOCK_STREAM)
        self.assertEqual(wire.connects, [('172.30.0.2', 8080)])
        self.assertTrue(wire.closed)
        return result

    def test_actual_task_http10_content_length_wire(self):
        body = b'APP OK: customer service is running\n'
        wire = WireSocket(b'HTTP/1.0 200 OK\r\nContent-Length: '+str(len(body)).encode()+b'\r\n\r\n'+body)
        data = self.probe(wire)
        self.assertEqual(base64.b64decode(data['body_b64']), body)
        self.assertTrue(data['complete'])
        self.assertEqual(wire.sent, [b'GET / HTTP/1.0\r\nHost: 172.30.0.2:8080\r\nConnection: close\r\n\r\n'])

    def test_http_redirect_not_followed(self):
        wire = WireSocket(b'HTTP/1.0 302 Found\r\nLocation: http://169.254.169.254/\r\nContent-Length: 0\r\n\r\n')
        self.assertEqual(self.probe(wire)['status'], 302)
        self.assertEqual(len(wire.connects), 1)

    def test_body_limit_and_incomplete_length(self):
        result = self.probe(WireSocket(b'HTTP/1.0 200 OK\r\nContent-Length: 999999\r\n\r\n'+b'x'*4000))
        self.assertEqual(len(base64.b64decode(result['body_b64'])), 1025)
        result = self.probe(WireSocket(b'HTTP/1.0 200 OK\r\nContent-Length: 50\r\n\r\nshort'))
        self.assertFalse(result['complete'])

    def test_malformed_framing_header_flood_and_chunked_unknown(self):
        wires = [b'WRONG\r\n\r\n', b'x'*9000, b'HTTP/1.0 200 OK\r\nContent-Length: 2\r\nContent-Length: 1\r\n\r\nxx',
                 b'HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n0\r\n\r\n',
                 b'HTTP/1.0 200 OK\r\n Folded: nope\r\n\r\n']
        for raw in wires:
            with self.subTest(length=len(raw)):
                self.assertEqual(self.probe(WireSocket(raw))['transport'], 'uncertain')

    def test_transport_timeout_refusal_and_error(self):
        for fault, expected in ((TimeoutError(), 'timeout'), (ConnectionRefusedError(), 'refused'), (OSError(), 'uncertain')):
            with self.subTest(expected=expected):
                self.assertEqual(self.probe(WireSocket(fault=fault))['transport'], expected)

    def test_absolute_deadline_bounds_slow_header(self):
        from trusted_checker_runtime.tests.support import Clock
        clock = Clock()
        wire = WireSocket(b'HTTP/1.0 200 OK\r\nX: '+b'x'*5000, clock=clock)
        data = runner.probe('172.30.0.2', socket_factory=lambda *args: wire, clock=clock)
        self.assertEqual(data['transport'], 'timeout')
        self.assertTrue(wire.closed)

    def test_reject_hostname_ipv6_url_public_and_noncanonical_ip(self):
        for value in ('localhost', '::1', 'http://172.30.0.2', '8.8.8.8', '172.030.0.2'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                runner.probe(value, socket_factory=lambda *args: self.fail('socket before numeric validation'))

    def test_protocol_extra_keys_versions_duplicates_and_incomplete_json(self):
        valid = runner.packet('172.30.0.2', 200, b'APP OK: customer service is running', True, 'none')
        self.assertEqual(decode(json.dumps(valid).encode(), '172.30.0.2')[1], b'APP OK: customer service is running')
        malformed = [b'{}', b'{', b'x'*4097, b'{"protocol_version":2,"protocol_version":2}',
                     json.dumps({**valid, 'result': 'passed'}).encode(),
                     json.dumps({**valid, 'policy_version': True}).encode(),
                     json.dumps({**valid, 'target_ipv4': '172.30.0.8'}).encode(),
                     json.dumps({**valid, 'body_b64': '???'}).encode(),
                     json.dumps({**valid, 'complete': 'yes'}).encode()]
        for raw in malformed:
            with self.subTest(length=len(raw)), self.assertRaises(Denied):
                decode(raw, '172.30.0.2')

    def test_release_handshake_not_delay_and_invalid_input_does_not_probe(self):
        with patch.object(runner.select, 'select', return_value=([0], [], [])), \
             patch.object(runner.os, 'read', side_effect=[bytes([b]) for b in b'PROBE\n']):
            self.assertTrue(runner.await_release(0))
        with patch.object(runner.select, 'select', return_value=([0], [], [])), \
             patch.object(runner.os, 'read', side_effect=[b'X', b'\n']):
            self.assertFalse(runner.await_release(0))

    def test_artifact_source_digest_and_pinned_base_requirement(self):
        from trusted_checker_live.artifacts import source_manifest
        root = Path(runner.__file__).parent
        manifest = source_manifest()
        self.assertEqual(manifest['files']['runner.py'], hashlib.sha256((root/'runner.py').read_bytes()).hexdigest())
        self.assertEqual(manifest['policy_digest'], LIVE_POLICY.digest)
        dockerfile = (root/'Runner.Dockerfile').read_text()
        self.assertIn('@sha256:', dockerfile)
        self.assertIn('sha256sum -c -', dockerfile)
        self.assertIn('USER 10001:10001', dockerfile)


class NetworkAndIsolationTests(TestCase):
    def setUp(self):
        self.x = LiveLab()
        self.addCleanup(self.x.close)

    def test_bootstrap_global_bridge_drop_and_inet_host_route_denial(self):
        rules = canonical_readback(compile_rules(self.x.approval))
        chains = [r['chain'] for r in rules if 'chain' in r]
        self.assertEqual({c['hook'] for c in chains if c['family'] == 'bridge'}, {'prerouting','forward','input','output'})
        self.assertTrue(all(c['policy'] == 'drop' for c in chains if c['family'] == 'bridge'))
        self.assertFalse(any('accept' in json.dumps(r) for r in rules if 'rule' in r and r['rule']['family'] == 'bridge'))
        self.assertIn('tcsh0', json.dumps(rules))

    def test_active_rules_only_exact_ports_ipv4_arp_and_8080(self):
        x = self.x
        ports = (PortBinding('vethTarget', 11, x.target_id, 'f'*64, '02:42:ac:1e:00:02', x.network.target_ipv4),
                 PortBinding('vethRunner', 12, 'e'*64, '9'*64, '02:42:ac:1e:00:03', x.network.runner_ipv4))
        encoded = json.dumps(compile_rules(x.approval, ports))
        self.assertIn('8080', encoded)
        self.assertIn('saddr ether', encoded)
        self.assertIn('established', encoded)
        self.assertIn('16383', encoded)  # Fragments rejected; DF bit allowed.
        self.assertNotIn('53', encoded)
        with self.assertRaises(Denied): compile_rules(x.approval, (ports[0], ports[0]))

    def test_preflight_evidence_explicitly_differs_from_active_matrix(self):
        x = self.x
        x.provision_live()
        identity = x.adapter.observe_target(x.enrollment, x.enrollment.provisioning_uuid, Phase.ENROLL)
        signed = x.enforcer.attest(x.approval, x.enrollment.provisioning_uuid, Phase.ENROLL, identity.payload.target, None)
        validated = x.validator.attest(x.approval, x.enrollment.provisioning_uuid, Phase.ENROLL, identity.payload.target, None, signed)
        self.assertEqual(validated.payload.passed_cases, ('bootstrap_default_deny', 'rules_readback_verified', 'topology_bound'))
        with self.assertRaises(Denied):
            x.validator.check(x.approval, x.enrollment.provisioning_uuid, Phase.BEFORE_PROBE, identity.payload.target, None)

    def test_false_active_case_and_foreign_host_interface_block_probe(self):
        x = self.x
        x.provision_live()
        original = x.validator.active_provider.measure
        def bad(*args):
            observations = list(original(*args)); observations[3]['verified'] = False
            return tuple(observations)
        x.validator.active_provider.measure = bad
        self.assertEqual(x.submit_live()['terminal']['result'], 'unknown')
        self.assertFalse(x.api.released)

    def test_br_netfilter_or_extra_bridge_invalidates_topology(self):
        x = self.x
        x.provision_live()
        original = x.validator.host.snapshot
        x.validator.host.snapshot = lambda *args: {**original(*args), 'br_netfilter': True}
        self.assertEqual(x.submit_live()['terminal']['result'], 'unknown')
        self.assertEqual(x.api.creates, 1)

    def test_imports_have_no_sdk_constructor_network_or_process_side_effects(self):
        script = '''
from unittest.mock import patch
import socket,subprocess,importlib,sys
with patch.object(socket,'socket',side_effect=AssertionError('socket forbidden')), patch.object(subprocess,'Popen',side_effect=AssertionError('process forbidden')):
 for name in ('adapter','transport','runner','protocol','signing','spec','egress','recovery','composition','artifacts','host_inventory','interfaces'):
  importlib.import_module('trusted_checker_live.'+name)
assert 'docker' not in sys.modules and 'django' not in sys.modules
'''
        result = subprocess.run([sys.executable, '-B', '-c', script], cwd=Path(__file__).resolve().parents[2],
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_sdk_endpoint_constructor_has_no_docker_config_discovery(self):
        from trusted_checker_live.transport import open_explicit_api
        import docker.api.client
        with patch.object(docker.api.client.config, 'load_general_config', side_effect=AssertionError('config discovery')), \
             patch.object(socket, 'socket', side_effect=AssertionError('connection forbidden')):
            api = open_explicit_api(self.x.endpoint)
            try:
                self.assertFalse(api.trust_env)
                self.assertEqual(api.timeout, 3.0)
                self.assertEqual(api._version, '1.45')
                self.assertEqual(set(api.adapters), {'http+docker://'})
            finally: api.close()

    def test_host_inventory_enters_only_network_namespace_with_host_binary(self):
        from types import SimpleNamespace
        from trusted_checker_live.host_inventory import LinuxHostInventory
        x = self.x
        x.provision_live()
        observed = x.enrollment.target
        attrs = x.api.objects[x.target_id]
        endpoint = next(iter(attrs['NetworkSettings']['Networks'].values()))
        endpoint['MacAddress'] = '02:42:ac:1e:00:02'
        port = Path(x.tmp.name)/'vethTarget'
        port.mkdir(); (port/'ifindex').write_text('11'); (port/'iflink').write_text('5')
        class ProcPath:
            def __init__(self, name): self.name = str(name)
            def __truediv__(self, other): return ProcPath(self.name+'/'+str(other))
            def __str__(self): return self.name
            def stat(self): return SimpleNamespace(st_ino=123)
            def read_text(self): return '111 (daemon) '+' '.join(['0']*19+['123'])
        links = [{'ifname':'lo'}, {'ifname':'eth0','ifindex':5,'link_index':11,'address': endpoint['MacAddress']}]
        reader = LinuxHostInventory(x.api, x.endpoint, x.clock, witness_reader=lambda ep: ep.witness)
        with patch('trusted_checker_live.host_inventory.Path', ProcPath), \
             patch('trusted_checker_live.host_inventory.subprocess.run', return_value=SimpleNamespace(
                 returncode=0, stdout=json.dumps(links).encode())) as command:
            binding = reader._container(x.approval, observed, (port,))
        self.assertEqual(binding.interface, 'vethTarget')
        args = command.call_args.args[0]
        self.assertEqual(args[:3], ['/usr/bin/nsenter', '--net=/proc/111/ns/net', '/usr/sbin/ip'])
        self.assertFalse(any('--mount' in arg or '--pid' in arg for arg in args))
