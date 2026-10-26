"""Only fixed task/runner Docker parameters, plus strict inspect normalization."""
import ipaddress
from trusted_checker_runtime.contracts import RuntimeConfig, Resource, Endpoint, expected_config
from trusted_checker_runtime.live_contract import LIVE_RUNNER, LIVE_TARGET, live_environment
from trusted_checker_runtime.profiles import require
from trusted_checker_shadow.policy import digest


def approved_mac(ipv4):
    return '02:42:'+':'.join(f'{value:02x}' for value in ipaddress.IPv4Address(ipv4).packed)


def launch_spec(approval, intent):
    runner = intent.resource == Resource.RUNNER
    p = LIVE_RUNNER if runner else LIVE_TARGET
    return dict(image=intent.image_id, name='tc-shadow-'+('runner-' if runner else 'target-')+intent.intent_uuid,
        entrypoint=list(p.entrypoint), command=list(p.command), user=p.user,
        environment=list(live_environment(approval, runner)), working_dir='/scratch' if runner else '',
        stdin_open=runner, tty=False, detach=True, use_config_proxy=False,
        labels={'tc-shadow.intent': intent.intent_uuid, 'tc-shadow.scope': approval.scope,
                'tc-shadow.domain': intent.resource.value, 'tc-shadow.binding': intent.runtime_binding_uuid,
                'tc-shadow.generation': intent.generation_uuid},
        host=dict(network_mode=approval.network.network_id, read_only=p.read_only, privileged=False,
            cap_drop=['ALL'], cap_add=[], security_opt=['no-new-privileges:true'],
            pid_mode='', ipc_mode='private', mem_limit=approval.limits.runner_memory if runner else approval.limits.target_memory,
            memswap_limit=approval.limits.runner_memory if runner else approval.limits.target_memory,
            nano_cpus=approval.limits.runner_cpu_nanos if runner else approval.limits.target_cpu_nanos,
            pids_limit=approval.limits.runner_pids if runner else approval.limits.target_pids,
            tmpfs=dict(p.tmpfs), log_config={'Type': 'json-file', 'Config': {'max-size': '16k', 'max-file': '1'}},
            restart_policy={'Name': 'no'}, init=False, publish_all_ports=False))


def normalize(approval, intent, attrs):
    """Inspect is an observation of an already owned ID, never adoption evidence."""
    try:
        h, c, state = attrs['HostConfig'], attrs['Config'], attrs['State']
        spec = launch_spec(approval, intent)
        env = c.get('Env') or []
        require(type(env) is list and len(env) <= 16 and len(env) == len(set(e.split('=',1)[0] for e in env)),
                'environment_invalid')
        require(not c.get('Volumes') and not h.get('Binds') and not h.get('VolumesFrom') and
                not h.get('Devices') and not h.get('DeviceRequests') and not h.get('PortBindings') and
                not h.get('PublishAllPorts') and not h.get('ExtraHosts') and not h.get('Links') and
                not h.get('Dns') and not h.get('DnsSearch') and not h.get('DnsOptions') and
                not h.get('Sysctls') and not h.get('CgroupParent') and not h.get('UsernsMode') and
                not h.get('UTSMode') and not h.get('AutoRemove') and not h.get('Init') and
                h.get('RestartPolicy', {}).get('Name') in ('no', '') and
                h.get('MemorySwap') == spec['host']['memswap_limit'], 'unexpected_runtime_option')
        require(all(c.get('Labels', {}).get(k) == v for k,v in spec['labels'].items()), 'labels_inconsistent')
        require(h.get('SecurityOpt') == ['no-new-privileges:true'], 'security_options_invalid')
        mounts = attrs.get('Mounts', [])
        require(all(m.get('Type') == 'tmpfs' and m.get('Destination') in spec['host']['tmpfs'] for m in mounts),
                'mount_not_allowed')
        net = attrs['NetworkSettings']['Networks']
        require(type(net) is dict and len(net) == 1 and set(net) <= {approval.network.network_id, approval.network.network_name},
                'extra_network_attachment')
        config = RuntimeConfig(c['User'], h['ReadonlyRootfs'], h['Privileged'], tuple(h.get('CapDrop') or ()),
            tuple(h.get('CapAdd') or ()), 'no-new-privileges:true' in h['SecurityOpt'],
            'private' if h.get('PidMode', '') == '' else 'host',
            'private' if h.get('IpcMode') in ('', 'private') else 'host',
            0, False, digest(tuple(sorted((h.get('Tmpfs') or {}).items()))),
            digest({'entrypoint': c.get('Entrypoint') or [], 'command': c.get('Cmd') or []}),
            h['NanoCpus'], h['Memory'], h['PidsLimit'], h['NetworkMode'],
            16384 if h.get('LogConfig') == spec['host']['log_config'] else 0, 4096,
            network_count=len(net), environment_digest=digest(tuple(sorted(env))), log_files=1,
            stdin_open=c.get('OpenStdin', False), tty=c.get('Tty', False), working_dir=c.get('WorkingDir') or '')
        require(config == expected_config(approval, intent.resource), 'runtime_profile_mismatch')
        require(attrs['Image'] == intent.image_id, 'image_mismatch')
        endpoint = next(iter(net.values()))
        if state['Status'] == 'created':
            require(not state['Running'] and state['Pid'] == 0 and endpoint.get('EndpointID', '') == '' and
                    endpoint.get('IPAddress', '') == '' and endpoint.get('NetworkID', '') in ('', approval.network.network_id)
                    and str(state.get('StartedAt', '')).startswith('0001-01-01'), 'created_state_invalid')
            ep = None
        elif endpoint.get('EndpointID') or endpoint.get('IPAddress'):
            require(endpoint.get('MacAddress') == approved_mac(approval.network.runner_ipv4 if intent.resource == Resource.RUNNER
                                                             else approval.network.target_ipv4), 'endpoint_mac_changed')
            ep = Endpoint(attrs['Id'], endpoint['NetworkID'], endpoint['EndpointID'], endpoint['IPAddress'])
        else:
            require(state['Status'] == 'exited' and not state['Running'] and state['Pid'] == 0 and
                    endpoint.get('NetworkID') == approval.network.network_id, 'endpoint_unproven')
            ep = None
        require(state['Status'] in ('created', 'running', 'exited') and
                (state['Status'] != 'running' or state['Running'] is True and state['Pid'] > 0), 'runtime_state_invalid')
        return config, ep
    except (KeyError, TypeError, ValueError, AttributeError):
        from trusted_checker_runtime.profiles import Denied
        raise Denied('runtime_inspect_invalid') from None
