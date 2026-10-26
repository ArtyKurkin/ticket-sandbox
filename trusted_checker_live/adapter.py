"""Specialized dormant raw SDK adapter; no generic/user-selected operations."""
import time
from uuid import uuid4
from trusted_checker_runtime.boundary import capture_create_response
from trusted_checker_runtime.contracts import (CreateIntent, DaemonObservation, IdentityObservation,
    NetworkEvidence, Phase, ProbeResponse, Resource, RunnerObservation, TargetSnapshot)
from trusted_checker_runtime.journal import body
from trusted_checker_runtime.profiles import Denied, require
from trusted_checker_shadow.policy import digest
from .protocol import decode
from .spec import launch_spec, normalize, approved_mac
from .transport import ExplicitUnixEndpoint, observe_linux_peer, open_explicit_api

SDK_OPERATIONS = frozenset(('info', 'inspect_image', 'inspect_network', 'create_host_config',
    'create_container', 'inspect_container', 'start', 'attach_socket', 'logs', 'wait', 'remove_owned_raw'))


class TrustedDockerAdapter:
    def __init__(self, authority, approval_uuid, endpoint, signer, *, api_factory=open_explicit_api,
                 witness_reader=observe_linux_peer, monotonic=time.monotonic):
        require(type(endpoint) is ExplicitUnixEndpoint, 'explicit_endpoint_required')
        self.authority, self.endpoint, self.signer = authority, endpoint, signer
        self.approval_uuid = approval_uuid
        self._api_factory, self._witness_reader = api_factory, witness_reader
        self.monotonic = monotonic
        self._api = None
        self._budgets = {}
        self._protocols = {}
        # No client/connection created here. Even constructing the composition is safe.

    def approval(self, launch=True):
        # Network v3 currently has only a sealed mock host/capture boundary.
        # No fixture receipt may unlock the real transport, including witness
        # reads which would otherwise connect before _client(). Recovery needs
        # a separately approved physical boundary too. Hostile Python callers
        # are outside the TCB; this guard prevents supported-path activation.
        require(self._api_factory is not open_explicit_api, 'physical_network_boundary_not_accepted')
        a = self.authority
        with a.journal.transaction() as db:
            approval = a._approval(db, self.approval_uuid)
            require(approval.authority_mode == 'live_runtime_v2', 'live_approval_required')
            require(a.journal.live, 'live_journal_required')
            require((approval.daemon.endpoint_reference, approval.daemon.endpoint_config_digest) ==
                    (self.endpoint.reference, self.endpoint.digest), 'endpoint_approval_mismatch')
            if launch:
                a._current(db, approval, a._now(db))
        return approval

    def context(self, identifier, resource, launch=True):
        a = self.authority
        approval = self.approval(launch)
        with a.journal.transaction() as db:
            row, intent, selected = a._object(db, a._kind(resource), identifier)
            require(selected == approval, 'foreign_runtime_object')
            if launch:
                a._current(db, selected, a._now(db), row)
            return dict(row), intent, approval

    def owned(self, identifier, resource):
        a = self.authority
        row, intent, approval = self.context(identifier, resource, False)
        with a.journal.transaction() as db:
            owned = a._ownership(db, resource, identifier)
        return row, intent, approval, owned

    def _client(self, launch=True):
        self.approval(launch)  # OFF checked before factory, including retries.
        if self._api is None:
            self._api = self._api_factory(self.endpoint)
        return self._api

    def _call(self, method, *args, intent=None, recovery=False, fenced=False, **kwargs):
        require(type(method) is str and method in SDK_OPERATIONS, 'sdk_operation_not_allowed')
        api = self._api if fenced else self._client(not recovery)
        require(api is not None, 'client_not_admitted')
        if fenced:
            require(not self.authority.journal.stop_requested(), 'live_stop_latched')
        seconds = 3.0
        if intent is not None and not recovery:
            budget = self._budgets.setdefault(intent.intent_uuid, self.monotonic()+max(0, intent.deadline-self.authority.clock()))
            seconds = min(seconds, intent.deadline-self.authority.clock(), budget-self.monotonic())
            require(seconds > 0, 'runtime_deadline_exceeded')
        api.timeout = seconds
        try:
            return getattr(api, method)(*args, **kwargs)
        except Exception:
            raise Denied('docker_operation_unknown') from None

    def daemon(self, context, *, intent=None, recovery=False):
        approval = self.approval(not recovery)
        try:
            observed = self._witness_reader(self.endpoint)
            require(observed == self.endpoint.witness, 'daemon_session_changed')
            info = self._call('info', intent=intent, recovery=recovery)
            require(info['ID'] == approval.daemon.daemon_id, 'daemon_id_mismatch')
        except (KeyError, OSError, ValueError):
            raise Denied('daemon_identity_unconfirmed') from None
        return self.signer.sign(DaemonObservation(str(uuid4()), context, approval.scope,
                                                approval.daemon, self.authority.clock()))

    def create(self, intent):
        require(type(intent) is CreateIntent, 'issued_intent_required')
        _, issued, approval = self.context(intent.intent_uuid, intent.resource)
        require(issued == intent, 'intent_not_issued')
        a = self.authority
        # Identity/API reads precede mutation fence, never precede ownership AFTER response.
        daemon = self.daemon(intent.intent_uuid, intent=intent)
        image = self._call('inspect_image', intent.image_id, intent=intent)
        require(image.get('Id') == intent.image_id and not image.get('Config', {}).get('Volumes'), 'image_unapproved')
        if intent.resource == Resource.RUNNER:
            require(image.get('Config', {}).get('Labels', {}).get('tc-shadow.checker-source') == approval.checker_source_digest,
                    'runner_source_image_binding_unconfirmed')
        network = self._call('inspect_network', approval.network.network_id, intent=intent)
        require(network.get('Id') == approval.network.network_id and network.get('Name') == approval.network.network_name and
                network.get('Internal') is True and network.get('Driver') == 'bridge' and network.get('EnableIPv6') is False,
                'create_network_unapproved')
        permit = a.begin_create(intent, daemon)
        spec = launch_spec(approval, intent)
        host = self._call('create_host_config', intent=intent, **spec.pop('host'))
        # Static numeric endpoint allocation is fixed by approved topology.
        ipv4 = approval.network.runner_ipv4 if intent.resource == Resource.RUNNER else approval.network.target_ipv4
        networking = {approval.network.network_id: {'IPAMConfig': {'IPv4Address': ipv4}, 'MacAddress': approved_mac(ipv4)}}
        raw = None
        failure = None
        try:
            with a.create_fence(permit):
                raw = self._call('create_container', host_config=host, networking_config=networking, intent=intent, fenced=True, **spec)
        except BaseException as error:
            failure = error
        if raw is not None:
            # No SDK get, inspect, reload, log or diagnostic between raw response
            # and this durable ownership attempt. Late/failed fence still records Id.
            signed = self.signer.sign(capture_create_response(intent, permit, raw, daemon=approval.daemon,
                                        receipt_uuid=str(uuid4()), observed_at=a.clock()))
            a.record_create_response(permit, signed)
        else:
            a.quarantine(intent.intent_uuid, intent.resource)
        if failure is not None or raw is None:
            raise Denied('create_outcome_unconfirmed') from None
        return signed

    def start_target(self, provisioning_uuid):
        _, intent, approval, owned = self.owned(provisioning_uuid, Resource.TARGET)
        daemon = self.daemon(provisioning_uuid, intent=intent)
        self.inspect_owned(provisioning_uuid, Resource.TARGET)  # Exact created config before initial start.
        with self.authority.target_start_fence(provisioning_uuid, daemon):
            self._call('start', owned['receipt']['container_id'], intent=intent, fenced=True)

    def inspect_owned(self, identifier, resource, *, recovery=False, budget_intent=None):
        _, intent, approval, owned = self.owned(identifier, resource)
        budget = budget_intent or (intent if resource == Resource.RUNNER else None)
        self.daemon(identifier, intent=budget, recovery=recovery)
        attrs = self._call('inspect_container', owned['receipt']['container_id'], intent=budget, recovery=recovery)
        require(attrs.get('Id') == owned['receipt']['container_id'], 'container_id_substitution')
        config, endpoint = normalize(approval, intent, attrs)
        return intent, approval, attrs, config, endpoint

    def observe_target(self, enrollment, context_uuid, phase):
        budget = self.authority.runner_create_intent(context_uuid) if context_uuid != enrollment.provisioning_uuid else None
        intent, approval, attrs, config, ep = self.inspect_owned(enrollment.provisioning_uuid, Resource.TARGET, budget_intent=budget)
        require(ep is not None, 'target_endpoint_missing')
        s = attrs['State']
        snapshot = TargetSnapshot(intent.attempt, intent.runtime_binding_uuid, intent.generation_uuid, approval.daemon,
            attrs['Id'], attrs['Image'], s['StartedAt'], attrs['RestartCount'], s['Running'],
            s.get('Paused', False), s.get('Restarting', False), s.get('Dead', False), (ep,), config, approval.policy_digest)
        return self.signer.sign(IdentityObservation(str(uuid4()), context_uuid, approval.scope,
                                                   self.authority.clock(), phase, snapshot))

    def observe_initial_target(self, provisioning_uuid):
        # Same observation port before an enrollment exists, using only owned intent.
        from types import SimpleNamespace
        return self.observe_target(SimpleNamespace(provisioning_uuid=provisioning_uuid), provisioning_uuid, Phase.ENROLL)

    def observe_owned_runner(self, run_uuid):
        intent, approval, attrs, config, ep = self.inspect_owned(run_uuid, Resource.RUNNER)
        s = attrs['State']
        return self.signer.sign(RunnerObservation(str(uuid4()), run_uuid, approval.scope, self.authority.clock(),
            approval.daemon, attrs['Id'], attrs['Image'], config, s['Status'],
            None if s['Status'] == 'created' else s['StartedAt'], attrs['RestartCount'], ep,
            s.get('Paused', False), s.get('Restarting', False), s.get('Dead', False),
            s.get('ExitCode') if s['Status'] == 'exited' else None))

    def observe_network(self, context_uuid, phase, target, runner=None):
        approval = self.approval()
        self.daemon(context_uuid)
        net = self._call('inspect_network', approval.network.network_id)
        import ipaddress
        ipam = net.get('IPAM', {}).get('Config') or []
        require(net.get('Id') == approval.network.network_id and net.get('Name') == approval.network.network_name and
                net.get('Driver') == 'bridge' and net.get('Internal') is True and net.get('EnableIPv6') is False and
                len(ipam) == 1 and ipam[0].get('Subnet') == approval.network.subnet and
                ipam[0].get('Gateway') == str(ipaddress.IPv4Network(approval.network.subnet).network_address+1) and
                net.get('Options', {}).get('com.docker.network.bridge.name') == 'tcsh0', 'network_unapproved')
        endpoints = target.endpoints + ((runner.endpoint,) if runner is not None and runner.endpoint is not None else ())
        actual = net.get('Containers') or {}
        require(set(actual) == {ep.container_id for ep in endpoints}, 'network_membership_mismatch')
        for ep in endpoints:
            record = actual[ep.container_id]
            require(record['EndpointID'] == ep.endpoint_id and record['IPv4Address'].split('/')[0] == ep.ipv4,
                    'network_endpoint_mismatch')
        return self.signer.sign(NetworkEvidence(str(uuid4()), context_uuid, approval.scope, self.authority.clock(),
            phase, approval.daemon, approval.network.digest, True, 'bridge', endpoints))

    def start_runner(self, permit):
        _, intent, _, owned = self.owned(permit.run_uuid, Resource.RUNNER)
        self.daemon(permit.run_uuid, intent=intent)
        with self.authority.start_fence(permit):
            self._call('start', owned['receipt']['container_id'], intent=intent, fenced=True)

    def release_and_collect(self, run_uuid, enrollment):
        a = self.authority
        _, intent, approval, owned = self.owned(run_uuid, Resource.RUNNER)
        with a.journal.transaction() as db:
            row, _, selected = a._object(db, 'run', run_uuid)
            a._current(db, selected, a._now(db), row)
            require(row['phase'] == 'probe_ready' and not a._document_exists(db, 'probe_release', run_uuid), 'probe_release_consumed')
            a.journal.put(db, 'probe_release', run_uuid, {'owned_id': owned['receipt']['container_id']})
        channel = self._call('attach_socket', owned['receipt']['container_id'],
                             params={'stdin': 1, 'stdout': 0, 'stderr': 0, 'stream': 1}, intent=intent)
        try:
            sock = getattr(channel, '_sock', channel)
            sock.settimeout(min(3.0, intent.deadline-a.clock()))
            sock.sendall(b'PROBE\n')
        except Exception:
            raise Denied('probe_release_unknown') from None
        finally:
            channel.close()
        chunks = self._call('logs', owned['receipt']['container_id'], stdout=True, stderr=False, stream=True,
                            follow=True, tail='all', intent=intent)
        raw = bytearray()
        try:
            for chunk in chunks:
                self.context(run_uuid, Resource.RUNNER)
                require(type(chunk) is bytes and len(raw)+len(chunk) <= 4096, 'runner_output_limit')
                raw.extend(chunk)
                if b'\n' in raw:
                    require(raw.count(b'\n') == 1 and raw.endswith(b'\n'), 'runner_protocol_extra_output')
                    break
        finally:
            close = getattr(chunks, 'close', None)
            if close:
                close()
        data, response = decode(bytes(raw), approval.network.target_ipv4)
        self._protocols[run_uuid] = digest(data)  # Memory only; no arbitrary body digest in evidence.
        return self.signer.sign(ProbeResponse(str(uuid4()), run_uuid, approval.scope, a.clock(),
            owned['receipt']['container_id'], approval.runner_image_id, approval.checker_source_digest,
            digest(body(enrollment.target)), approval.policy_digest, data['status'] or 200, response,
            data['complete'], data['transport']))

    def finish_runner(self, run_uuid):
        a = self.authority
        row, intent, _, owned = self.owned(run_uuid, Resource.RUNNER)
        require(row['phase'] == 'publish_checked', 'finish_not_authorized')
        with a.journal.transaction() as db:
            require(not a._document_exists(db, 'finish_dispatch', run_uuid), 'finish_already_dispatched')
            a.journal.put(db, 'finish_dispatch', run_uuid, {'exact_id': owned['receipt']['container_id']})
        channel = self._call('attach_socket', owned['receipt']['container_id'],
                             params={'stdin': 1, 'stdout': 0, 'stderr': 0, 'stream': 1}, intent=intent)
        try:
            sock = getattr(channel, '_sock', channel)
            sock.settimeout(min(3.0, intent.deadline-a.clock()))
            sock.sendall(b'FINISH\n')
        finally:
            channel.close()
        finished = self._call('wait', owned['receipt']['container_id'], timeout=min(3.0, intent.deadline-a.clock()), intent=intent)
        require(finished.get('StatusCode') == 0, 'runner_exit_unknown')
        # Validate the COMPLETE final output, not just the first streaming line.
        chunks = self._call('logs', owned['receipt']['container_id'], stdout=True, stderr=False, stream=True, tail='all', intent=intent)
        raw = bytearray()
        try:
            for chunk in chunks:
                require(type(chunk) is bytes and len(raw)+len(chunk) <= 4096, 'runner_output_limit')
                raw.extend(chunk)
        finally:
            close = getattr(chunks, 'close', None)
            if close: close()
        data, response = decode(bytes(raw), self.approval().network.target_ipv4)
        require(digest(data) == self._protocols.get(run_uuid), 'runner_output_changed_or_process_restarted')
        a.record_runner_finished(run_uuid, self.observe_owned_runner(run_uuid))
        self._protocols.pop(run_uuid, None)

    def close(self):
        if self._api is not None:
            self._api.close()
