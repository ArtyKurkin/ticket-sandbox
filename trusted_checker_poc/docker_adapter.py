"""Dormant real adapter. Never discovers Docker or provisions a daemon.

Construct only with an operator-verified, dedicated daemon and synthetic network.
No tests in this task connect to Docker. Approval is not cryptographic attestation.
"""
from dataclasses import dataclass
import ipaddress
import json
import re

from .contracts import AdapterError, Outcome, Runner, Target, full_id
from .diagnostics import PrepareTrace


@dataclass(frozen=True)
class DedicatedDaemonApproval:
    daemon_id: str
    network_id: str
    scope: str
    isolation_evidence: str


@dataclass(frozen=True)
class Plan:
    policy: object
    target: Target
    run_id: str
    challenge: str
    intent: dict | None = None
    lifecycle: object | None = None


def intent_labels(intent):
    return {'tc-poc.intent': intent['intent_id'], 'tc-poc.generation': intent['generation'],
            'tc-poc.token': intent['token'], 'tc-poc.integration': intent['integration_id']}


def launch_spec(plan):
    p = plan.policy
    spec = dict(image=p.runner_image_id, name=f'tc-poc-runner-{plan.run_id}',
                entrypoint=['/usr/local/bin/python','-I','/checker/runner.py'], command=[],
                environment={'POC_TARGET_IPV4':plan.target.ipv4,'POC_CHALLENGE':plan.challenge},
                network=plan.target.network_id, user='10001:10001', read_only=True,
                cap_drop=['ALL'], cap_add=[], privileged=False, security_opt=['no-new-privileges:true'],
                mem_limit=p.memory_bytes, nano_cpus=p.cpu_nanos, pids_limit=p.pids,
                tmpfs={'/scratch':'rw,noexec,nosuid,nodev,size=1m,uid=10001,gid=10001,mode=0700'},
                working_dir='/scratch', stdin_open=False, tty=False,
                labels={'tc-poc.scope':plan.target.scope,'tc-poc.role':'runner','tc-poc.run':plan.run_id},
                log_config={'Type':'json-file','Config':{'max-size':'16k','max-file':'1'}})
    if plan.intent:
        spec['labels'].update(intent_labels(plan.intent))
    return spec


class DockerAdapter:
    def __init__(self, client, approval):
        # client is an explicitly constructed, bounded-timeout SDK client. There
        # is intentionally no default socket / from_env / production discovery.
        if (not approval.daemon_id or not approval.isolation_evidence.strip() or
                not approval.scope.startswith('poc-') or not full_id(approval.network_id)):
            raise ValueError('dedicated_daemon_approval_required')
        self.client, self.approval = client, approval
        info = client.info()
        if info['ID'] != approval.daemon_id:
            raise ValueError('daemon_identity_mismatch')
        network = client.networks.get(approval.network_id).attrs
        if (network['Id'] != approval.network_id or not network['Internal'] or
                network.get('Labels',{}).get('tc-poc.scope') != approval.scope or
                not isinstance(network.get('Name'),str) or not network['Name']):
            raise ValueError('isolated_network_required')
        self.network_name = network['Name']

    def inspect_target(self, container_id):
        if not full_id(container_id):
            raise AdapterError('target_identity_invalid','identity')
        try:
            obj = self.client.containers.get(container_id)
            obj.reload()
            a = obj.attrs
        except Exception as error:
            from docker.errors import NotFound
            if isinstance(error,NotFound):
                raise AdapterError('target_unavailable','target_unavailable') from None
            raise AdapterError('docker_unavailable','infrastructure') from None
        labels = a['Config'].get('Labels') or {}
        networks = a['NetworkSettings']['Networks']
        endpoints = [n for n in networks.values() if n['NetworkID'] == self.approval.network_id]
        if (a['Id'] != container_id or labels.get('tc-poc.role') != 'target' or
                labels.get('tc-poc.scope') != self.approval.scope or len(networks) != 1 or len(endpoints) != 1 or
                not a['State']['Running'] or a['HostConfig'].get('Binds') or a.get('Mounts')):
            raise AdapterError('target_identity_mismatch','identity')
        target = Target(a['Id'],labels.get('tc-poc.generation',''),labels.get('tc-poc.owner',''),
                        labels.get('tc-poc.task',''), self.approval.network_id, endpoints[0]['IPAddress'],
                        a['State']['StartedAt'],a['RestartCount'],a['Image'],self.approval.scope)
        target.validate()
        return target

    def plan(self, policy, target, run_id, challenge):
        if target.network_id != self.approval.network_id or target.scope != self.approval.scope:
            raise AdapterError('target_scope_mismatch','identity')
        return Plan(policy,target,run_id,challenge)

    def _runner_config_valid(self, obj, plan):
        """Launch invariants shared by every lifecycle phase."""
        a, p = obj.attrs, plan.policy
        host, config = a['HostConfig'], a['Config']
        networks = a['NetworkSettings']['Networks']
        expected = launch_spec(plan)
        env = dict(item.split('=',1) for item in config.get('Env',[]))
        labels = config.get('Labels') or {}
        return (all(env.get(k) == v for k,v in expected['environment'].items()) and
                all(labels.get(k) == v for k,v in expected['labels'].items()) and
                not config.get('Tty') and not config.get('OpenStdin') and a['Image'] == p.runner_image_id and config['User'] == '10001:10001' and
                config['Entrypoint'] == ['/usr/local/bin/python','-I','/checker/runner.py'] and not config.get('Cmd') and
                host['ReadonlyRootfs'] is True and not host['Privileged'] and not host.get('Binds') and
                not host.get('VolumesFrom') and not host.get('CapAdd') and host.get('CapDrop') == ['ALL'] and
                host.get('PidMode','') == '' and host.get('IpcMode','private') in ('','private') and
                host.get('NetworkMode') == plan.target.network_id and
                config.get('WorkingDir') == '/scratch' and host.get('Tmpfs') == launch_spec(plan)['tmpfs'] and
                host['Memory'] == p.memory_bytes and host['NanoCpus'] == p.cpu_nanos and host['PidsLimit'] == p.pids and
                'no-new-privileges:true' in host.get('SecurityOpt',[]) and
                len(networks) == 1 and set(networks) <= {self.network_name,plan.target.network_id} and
                all(m['Type'] == 'tmpfs' and m['Destination'] == '/scratch' for m in a.get('Mounts',[])))

    def _runner_valid(self, obj, plan, *, phase, connection=None):
        """Created configuration is not evidence of an attached runtime endpoint.

        A finished runner may have lost its endpoint on normal Docker teardown;
        accept that only after observing a live connection for this same start.
        NetworkID must remain exact even in that terminal snapshot.
        """
        if phase not in ('pre_start','post_start','finished'):
            return False
        try:
            if not self._runner_config_valid(obj,plan):
                return False
            a = obj.attrs
            state = a['State']
            endpoint = next(iter(a['NetworkSettings']['Networks'].values()))
            if (not full_id(a['Id']) or a['RestartCount'] != 0 or
                    any(state.get(flag,False) for flag in ('Paused','Restarting','Dead'))):
                return False
            network_id = endpoint.get('NetworkID')
            endpoint_id = endpoint.get('EndpointID')
            address = endpoint.get('IPAddress')
            started_at = state.get('StartedAt','')
            never_started = isinstance(started_at,str) and re.fullmatch(
                r'0001-01-01T00:00:00(?:\.0+)?Z',started_at) is not None
            if phase == 'pre_start':
                return (state['Status'] == 'created' and state['Running'] is False and
                        state['Pid'] == 0 and never_started and
                        network_id in ('',plan.target.network_id) and
                        endpoint_id == '' and address == '')
            if network_id != plan.target.network_id or not started_at or never_started:
                return False
            if phase == 'finished':
                if (state['Status'] != 'exited' or state['Running'] is not False or state['Pid'] != 0 or
                        not connection or connection['container_id'] != a['Id'] or
                        connection['started_at'] != started_at or
                        connection['network_id'] != network_id):
                    return False
                if endpoint_id == '' and address == '':
                    return True  # Detach after a previously validated running endpoint.
                return (endpoint_id == connection['endpoint_id'] and address == connection['ipv4'])
            if state['Status'] != 'running' or state['Running'] is not True or state['Pid'] <= 0:
                return False
            ip = ipaddress.IPv4Address(address)
            return (full_id(endpoint_id) and
                    any(ip in ipaddress.IPv4Network(n) for n in
                        ('10.0.0.0/8','172.16.0.0/12','192.168.0.0/16')))
        except (KeyError,TypeError,ValueError,AttributeError):
            return False

    def prepare(self, plan):
        trace = plan.lifecycle.trace if plan.lifecycle else PrepareTrace(plan.run_id)
        trace.emit('before_create')
        try:
            spec = launch_spec(plan)
            if plan.lifecycle:
                # Capture the raw create response BEFORE the SDK's extra GET.
                # ContainerCollection.create() internally calls get(), which can
                # fail after create succeeded and discard the returned exact ID.
                host_fields = ('read_only','cap_drop','cap_add','privileged','security_opt',
                               'mem_limit','nano_cpus','pids_limit','tmpfs','log_config')
                host = self.client.api.create_host_config(network_mode=spec['network'],
                    **{key: spec[key] for key in host_fields})
                direct_fields = ('image','name','entrypoint','command','environment','user',
                                 'working_dir','stdin_open','tty','labels')
                plan.lifecycle.check()
                trace.emit('create_requested')
                response = self.client.api.create_container(host_config=host,
                    networking_config={spec['network']: None},
                    **{key: spec[key] for key in direct_fields})
                trace.stage = 'create_response_received'  # Memory only until ownership attempt.
                if type(response) is not dict:
                    trace.fail(None, code='response_type_invalid')
                    raise AdapterError('runner_prepare_unknown','unknown_execution')
                if 'Id' not in response:
                    trace.fail(None, code='response_id_missing')
                    raise AdapterError('runner_prepare_unknown','unknown_execution')
                if not full_id(response['Id']):
                    trace.fail(None, code='response_id_invalid')
                    raise AdapterError('runner_prepare_unknown','unknown_execution')
                plan.lifecycle.received(response['Id'])
                plan.lifecycle.check()  # Late create: ownership stored, no further execution.
                trace.emit('inspect_pending')
                obj = self.client.containers.get(response['Id'])
            else:
                trace.emit('create_requested')
                obj = self.client.containers.create(**spec)
                trace.has_exact_id = full_id(obj.id)
                trace.emit('create_response_received')
                trace.emit('inspect_pending')
            if plan.lifecycle:
                plan.lifecycle.check()
            obj.reload()
            if plan.lifecycle:
                plan.lifecycle.check()
            # Observation hook is diagnostic only; validation still gates start.
            self.observe_runner(obj, plan, 'pre_start')
            runner = Runner(obj.id,obj.attrs['Image'],plan.run_id,plan.target.scope,
                            self._runner_valid(obj,plan,phase='pre_start'))
            trace.emit('prepare_finished')
            return runner
        except AdapterError as error:
            trace.fail(error)
            raise
        except Exception as error:
            trace.fail(error)
            raise AdapterError('runner_prepare_unknown','unknown_execution') from None

    def run(self, plan, runner, remaining):
        if remaining <= 0:
            raise AdapterError('runner_deadline_exceeded','timeout')
        try:
            if plan.lifecycle:
                plan.lifecycle.check()
            obj = self.client.containers.get(runner.container_id)
            if plan.lifecycle:
                plan.lifecycle.check()
            obj.reload()
            if obj.id != runner.container_id or not self._runner_valid(obj,plan,phase='pre_start'):
                raise AdapterError('runner_identity_mismatch','integrity')
            self.observe_runner(obj, plan, 'starting')
            if plan.lifecycle:
                plan.lifecycle.start(obj.start)
                plan.lifecycle.check()
            else:
                obj.start()
            obj.reload()
            if obj.id != runner.container_id or not self._runner_valid(obj,plan,phase='post_start'):
                raise AdapterError('runner_identity_mismatch','integrity')
            self.observe_runner(obj, plan, 'post_start')
            if plan.lifecycle:
                plan.lifecycle.check()
            endpoint = next(iter(obj.attrs['NetworkSettings']['Networks'].values()))
            connection = dict(container_id=obj.id,started_at=obj.attrs['State']['StartedAt'],
                              network_id=endpoint['NetworkID'],endpoint_id=endpoint['EndpointID'],
                              ipv4=endpoint['IPAddress'])
            status = obj.wait(timeout=remaining)
            if plan.lifecycle:
                plan.lifecycle.check()
            if status.get('StatusCode') != 0:
                raise AdapterError('runner_crash','runner')
            raw = bytearray()
            for chunk in obj.logs(stdout=True,stderr=False,stream=True):
                if plan.lifecycle:
                    plan.lifecycle.check()
                raw.extend(chunk)
                if len(raw) > plan.policy.output_limit:
                    raise AdapterError('runner_output_limit','runner')
            if plan.lifecycle:
                plan.lifecycle.check()
            obj.reload()
            if obj.id != runner.container_id or not self._runner_valid(obj,plan,phase='finished',connection=connection):
                raise AdapterError('runner_identity_mismatch','integrity')
            self.observe_runner(obj, plan, 'finished')
            try:
                body = json.loads(raw)
            except (ValueError,UnicodeError):
                raise AdapterError('runner_protocol_invalid','runner') from None
            if set(body) != {'result','reason','evidence'} or not isinstance(body['evidence'],dict):
                raise AdapterError('runner_protocol_invalid','runner')
            return Outcome(**body)
        except AdapterError:
            raise
        except Exception:
            raise AdapterError('docker_or_runner_execution_unknown','unknown_execution') from None

    def observe_runner(self, obj, plan, phase):
        """Optional trusted diagnostics. Never substitutes for lifecycle validation."""

    def cleanup(self, runner):
        return self._cleanup(runner)

    def cleanup_owned(self, runner, intent, daemon_id):
        return self._cleanup(runner, intent=intent, daemon_id=daemon_id)

    def _cleanup(self, runner, *, intent=None, daemon_id=None):
        # Never list/prune, remove by name/label, or touch a target. Absence is
        # not silently confirmed here: an ambiguous API failure retains the lock.
        if not full_id(runner.container_id) or runner.scope != self.approval.scope:
            return False
        try:
            if daemon_id and (daemon_id != self.approval.daemon_id or self.client.info()['ID'] != daemon_id):
                return False
            obj = self.client.containers.get(runner.container_id)
            obj.reload()
            a = obj.attrs
            labels = a['Config'].get('Labels') or {}
            if (a['Id'] != runner.container_id or a['Image'] != runner.image_id or
                    labels.get('tc-poc.role') != 'runner' or labels.get('tc-poc.scope') != runner.scope or
                    labels.get('tc-poc.run') != runner.run_id):
                return False
            if intent and any(labels.get(key) != value for key,value in intent_labels(intent).items()):
                return False
            obj.remove(force=True)
            return True
        except Exception:
            return False
