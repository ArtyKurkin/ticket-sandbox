"""Separate render-only counter recipe. No installer or arbitrary rules input."""
from copy import deepcopy
from dataclasses import asdict, dataclass, replace
import json
import struct

from trusted_checker_runtime.contracts import RuntimeApproval, uid
from trusted_checker_runtime.profiles import require
from trusted_checker_shadow.policy import digest
from .contracts import NetworkBinding
from .packets import plan, checksum
from .rules import approved_rules


@dataclass(frozen=True)
class CounterSpec:
    identity: str
    object_index: int
    expression_index: int
    purpose: str
    probe_index: int = -1


@dataclass(frozen=True)
class Recipe:
    json: str
    counters: tuple[CounterSpec, ...]

    @property
    def digest(self): return digest({'method': 'nft_counter_probe_v1', 'rules': json.loads(self.json),
                                     'counters': [asdict(c) for c in self.counters]})


def sample_plan(binding, context):
    """Reuse finite v3 headers; bind UDP probes to a 96-bit context token."""
    result = []
    for p in plan(binding, context):
        raw = p.frame; offset = 18 if raw[12:14] == b'\x81\x00' else 14
        if raw[offset] >> 4 == 4 and raw[offset+9] == 17:
            ip = bytearray(raw[offset:offset+20]); udp = bytearray(raw[offset+20:])
            udp.extend(bytes.fromhex(p.probe_id[:24])); udp[4:6] = struct.pack('!H', len(udp)); udp[6:8] = b'\0\0'
            udp[6:8] = struct.pack('!H', checksum(bytes(ip[12:20])+struct.pack('!BBH', 0, 17, len(udp))+bytes(udp)) or 65535)
            ip[2:4] = struct.pack('!H', 20+len(udp)); ip[10:12] = b'\0\0'; ip[10:12] = struct.pack('!H', checksum(bytes(ip)))
            p = replace(p, frame=raw[:offset]+bytes(ip)+bytes(udp))
        result.append(p)
    return tuple(result)


def compile_counter_rules(identifier, runtime, binding, context, *, active=True):
    uid(identifier); uid(context)
    require(type(runtime) is RuntimeApproval and type(binding) is NetworkBinding and type(active) is bool,
            'counter_recipe_inputs')
    runtime.__post_init__(); binding.__post_init__()
    require(binding.runtime_approval_digest == runtime.digest and binding.daemon == runtime.daemon and
            binding.network_id == runtime.network.network_id and binding.scope == runtime.scope and
            binding.target.ipv4 == runtime.network.target_ipv4 and binding.runner.ipv4 == runtime.network.runner_ipv4,
            'counter_runtime_binding_mismatch')
    commands = deepcopy(approved_rules(identifier, runtime, binding, active=active)['nftables'])
    table = 'tcc1_'+identifier.replace('-', '')
    for c in commands:
        obj = next(iter(c['add'].values()))
        if 'name' in obj and obj['name'].startswith('tc3_'): obj['name'] = table
        if 'table' in obj: obj['table'] = table
    specs = []
    def append_counter(rule, purpose, probe=-1):
        i = len(rule['expr'])-1
        rule['expr'].insert(i, {'counter': {'packets': 0, 'bytes': 0}})
        # Filled from final command ordering below, never from a supplied name.
        return (rule, i, purpose, probe)
    pending = []
    for c in commands:
        if 'rule' in c['add']:
            rule = c['add']['rule']
            purpose = 'allow' if rule['expr'][-1] == {'accept': None} else 'guard_drop'
            pending.append(append_counter(rule, purpose))
    if active:
        # Diagnostics only add terminal drops and non-verdict ingress counts.
        # Full header match is chunked to <=128-bit raw payload comparisons.
        # Native parser/normalization is deliberately NOT accepted by this offline foundation.
        extra = []
        for index, probe in enumerate(sample_plan(binding, context)):
            expr = [{'match': {'op': '==', 'left': {'meta': {'key': 'iif'}}, 'right': binding.runner.ifindex}}]
            for start in range(0, len(probe.frame), 16):
                part = probe.frame[start:start+16]
                expr.append({'match': {'op': '==', 'left': {'payload': {'base': 'll', 'offset': start*8,
                            'len': len(part)*8}}, 'right': '0x'+part.hex()}})
            rule = {'family': 'bridge', 'table': table, 'chain': 'prerouting',
                    'expr': expr+[{'counter': {'packets': 0, 'bytes': 0}}]}
            pending.append((rule, len(expr), 'ingress', index)); extra.append({'add': {'rule': rule}})
            if index:
                rule = {'family': 'bridge', 'table': table, 'chain': 'prerouting',
                        'expr': deepcopy(expr)+[{'counter': {'packets': 0, 'bytes': 0}}, {'drop': None}]}
                pending.append((rule, len(expr), 'terminal_drop', index)); extra.append({'add': {'rule': rule}})
        first = next(i for i,c in enumerate(commands) if 'rule' in c['add'])
        commands[first:first] = extra
    # Explicit final drops account for fallthrough; original policies remain.
    for hook in ('prerouting', 'input', 'forward', 'output'):
        rule = {'family': 'bridge', 'table': table, 'chain': hook,
                'expr': [{'counter': {'packets': 0, 'bytes': 0}}, {'drop': None}]}
        commands.append({'add': {'rule': rule}}); pending.append((rule, 0, 'fallback_drop', -1))
    for index,c in enumerate(commands):
        if 'rule' not in c['add']: continue
        rule = c['add']['rule']
        item = next(p for p in pending if p[0] is rule)
        specs.append(CounterSpec(digest({'context': context, 'index': index, 'position': item[1], 'purpose': item[2]}),
                                 index, item[1], item[2], item[3]))
    return Recipe(json.dumps({'nftables': commands}, sort_keys=True, separators=(',', ':')), tuple(specs))
