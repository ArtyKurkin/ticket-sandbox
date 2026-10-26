"""Strict bounded runner decoder; no runner-supplied verdict is trusted."""
import base64
import json
from trusted_checker_runtime.live_contract import LIVE_POLICY
from trusted_checker_runtime.profiles import require


def decode(raw, target_ipv4):
    require(type(raw) is bytes and 0 < len(raw) <= 4096, 'runner_output_invalid')
    def pairs(items):
        require(len(items) == len(dict(items)), 'runner_duplicate_key')
        return dict(items)
    try:
        data = json.loads(raw, object_pairs_hook=pairs)
        require(type(data) is dict and set(data) == {'protocol_version', 'policy_id', 'policy_version', 'target_ipv4',
                                                   'status', 'body_b64', 'complete', 'transport'}, 'runner_schema_invalid')
        require(type(data['protocol_version']) is int and data['protocol_version'] == 2 and
                type(data['policy_version']) is int and data['policy_version'] == LIVE_POLICY.version and
                data['policy_id'] == LIVE_POLICY.policy_id and data['target_ipv4'] == target_ipv4 and
                type(data['complete']) is bool and data['transport'] in ('none', 'timeout', 'uncertain', 'refused'),
                'runner_identity_or_version_invalid')
        require(type(data['body_b64']) is str, 'runner_body_invalid')
        body = base64.b64decode(data['body_b64'], validate=True)
        require(len(body) <= 1025, 'runner_body_invalid')
        if data['transport'] == 'none':
            require(type(data['status']) is int and 100 <= data['status'] <= 599, 'runner_status_invalid')
        else:
            require(data['status'] is None and body == b'' and data['complete'] is False, 'runner_transport_invalid')
        return data, body
    except (ValueError, TypeError, UnicodeError):
        from trusted_checker_runtime.profiles import Denied
        raise Denied('runner_protocol_invalid') from None
