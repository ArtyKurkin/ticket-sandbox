"""Strict supplied-JSON parser; does not execute nft or query a kernel."""
from copy import deepcopy
import json

from trusted_checker_runtime.profiles import require, Denied
from .counter_contracts import CounterApproval, CounterValue, MAXIMUM, ReadbackFixture
from .counter_rules import compile_counter_rules
from trusted_checker_shadow.policy import digest


def parse_json(raw):
    require(type(raw) is str and len(raw.encode()) <= 262144, 'counter_readback_invalid')
    def pairs(items):
        result = {}
        for k,v in items:
            require(k not in result, 'counter_readback_invalid'); result[k] = v
        return result
    try:
        return json.loads(raw, object_pairs_hook=pairs,
                          parse_float=lambda _: require(False, 'counter_readback_invalid'),
                          parse_constant=lambda _: require(False, 'counter_readback_invalid'))
    except (ValueError, TypeError, RecursionError): raise Denied('counter_readback_invalid') from None


def validate_readback(observation, approval):
    require(type(observation) is ReadbackFixture and type(approval) is CounterApproval, 'counter_readback_invalid')
    observation.__post_init__()
    require(observation.context_uuid == approval.context_uuid and observation.approval_digest == approval.digest and
            observation.scope == approval.scope and observation.install_epoch_uuid == approval.install_epoch_uuid and
            observation.generation == approval.install_generation, 'counter_generation_changed')
    recipe = compile_counter_rules(approval.approval_uuid, approval.runtime, approval.binding, approval.context_uuid)
    expected = json.loads(recipe.json)['nftables']
    raw = parse_json(observation.json)
    require(type(raw) is dict and set(raw) == {'nftables'} and type(raw['nftables']) is list and
            len(raw['nftables']) == len(expected), 'counter_readback_invalid')
    specs = {s.object_index: s for s in recipe.counters}; values = []
    for index,(item,command) in enumerate(zip(raw['nftables'], expected)):
        kind, want = next(iter(command['add'].items()))
        require(type(item) is dict and set(item) == {kind} and type(item[kind]) is dict,
                'counter_readback_invalid')
        actual = deepcopy(item[kind])
        require(type(actual.get('handle')) is int and actual.pop('handle') == approval.object_handles[index],
                'counter_readback_invalid')
        if index in specs:
            s = specs[index]
            require(type(actual.get('expr')) is list and len(actual['expr']) == len(want['expr']), 'counter_readback_invalid')
            c = actual['expr'][s.expression_index]
            require(type(c) is dict and set(c) == {'counter'} and type(c['counter']) is dict and
                    set(c['counter']) == {'packets', 'bytes'}, 'counter_readback_invalid')
            p, b = c['counter']['packets'], c['counter']['bytes']
            require(type(p) is int and type(b) is int and 0 <= p <= MAXIMUM and 0 <= b <= MAXIMUM,
                    'counter_reset_or_wrap')
            values.append(CounterValue(s.identity, want['family'], want['table'], want['chain'],
                                       approval.object_handles[index], s.expression_index, p, b))
            actual['expr'][s.expression_index] = {'counter': {'packets': 0, 'bytes': 0}}
        # Typed canonical comparison rejects bool-as-int, extra keys, unknown
        # expressions, moved/shared/named counters and match/verdict mutations.
        require(digest(actual) == digest(want), 'counter_readback_invalid')
    require(len({v.identity for v in values}) == len(values), 'counter_readback_invalid')
    return tuple(values)
