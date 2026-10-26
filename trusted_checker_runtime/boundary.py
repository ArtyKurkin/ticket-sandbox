"""Pure capture of a future RAW create response, before diagnostic/inspect I/O.

This does not invoke Docker or prove origin. Only the separately authenticated
adapter can sign this envelope, and the authority checks the persisted dispatch.
"""

from trusted_checker_shadow.policy import digest
from .contracts import CreateIntent, CreateResponse, DaemonIdentity, DispatchPermit, full_id
from .journal import body
from .profiles import require


def capture_create_response(intent, permit, raw_response, *, daemon, receipt_uuid, observed_at):
    require(type(intent) is CreateIntent and type(permit) is DispatchPermit and type(daemon) is DaemonIdentity,
            "create_capture_contract_invalid")
    intent.__post_init__()
    permit.__post_init__()
    require((permit.intent_uuid, permit.resource, permit.intent_digest, daemon) ==
            (intent.intent_uuid, intent.resource, digest(body(intent)), intent.daemon), "create_capture_binding_mismatch")
    require(type(raw_response) is dict and 'Id' in raw_response and
            set(raw_response) <= {'Id', 'Warnings'}, "raw_create_response_invalid")
    # Only exact Docker Id is accepted. No name, inspect, label or alternate key.
    full_id(raw_response['Id'])
    warnings = raw_response.get('Warnings')
    require(warnings is None or type(warnings) is list and len(warnings) <= 16
            and all(type(item) is str and len(item) <= 4096 for item in warnings), "raw_create_response_invalid")
    return CreateResponse(receipt_uuid, intent.intent_uuid, intent.scope, daemon, observed_at,
        permit.permit_uuid, intent.resource, permit.intent_digest, raw_response['Id'], intent.image_id)
