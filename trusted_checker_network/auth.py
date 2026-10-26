"""A separate proof domain. No live runtime EgressValidation can be signed here."""
from dataclasses import asdict, dataclass, field
import hashlib
import hmac
import json
from trusted_checker_runtime.profiles import require


def payload_types():
    from .contracts import NetworkApproval,InstallReceipt
    from .host import ApplyAck,Readback
    from .collector import Capture,MatrixReceipt
    return {'approval':NetworkApproval,'install':InstallReceipt,'apply_ack':ApplyAck,'readback':Readback,
            'capture':Capture,'matrix':MatrixReceipt}


@dataclass(frozen=True)
class Principal:
    name: str
    role: str
    scope: str
    key: bytes = field(repr=False)

    def __post_init__(self):
        from trusted_checker_runtime.contracts import atom, scope
        require(self.role in ('operator', 'installer', 'capture', 'validator', 'host'), 'network_role_invalid')
        atom(self.name, self.role+':'); scope(self.scope)
        require(type(self.key) is bytes and len(self.key) >= 32, 'network_key_invalid')


@dataclass(frozen=True)
class Signed:
    kind: str
    principal: str
    scope: str
    payload: object
    signature: str


def canonical(kind, principal, scope, payload):
    def safe(value):
        if type(value) is bytes: return {'bytes': len(value), 'digest': hashlib.sha256(value).hexdigest()}
        if isinstance(value, dict): return {k:safe(v) for k,v in value.items()}
        if isinstance(value, (tuple, list)): return [safe(v) for v in value]
        return value
    return json.dumps({'domain':'tc-network-mock-v3', 'kind':kind, 'principal':principal, 'scope':scope,
                       'payload':safe(asdict(payload))}, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


class NetworkSigner:
    def __init__(self, principal):
        require(type(principal) is Principal, 'installed_network_signer_required')
        principal.__post_init__(); self.principal = principal

    def sign(self, kind, payload):
        role = {'approval':'operator','install':'installer','capture':'capture','matrix':'validator','apply_ack':'host','readback':'validator'}
        require(kind in role and type(payload) is payload_types()[kind] and role[kind] == self.principal.role and payload.scope == self.principal.scope,
                'network_signer_not_authorized')
        payload.__post_init__()
        raw = canonical(kind, self.principal.name, self.principal.scope, payload)
        return Signed(kind, self.principal.name, self.principal.scope, payload,
                      hmac.new(self.principal.key, raw, hashlib.sha256).hexdigest())


class NetworkVerifier:
    def __init__(self, principals):
        self.principals = {}
        keys = set()
        for p in principals:
            p.__post_init__()
            require(p.name not in self.principals and p.key not in keys, 'independent_network_keys_required')
            self.principals[p.name] = p; keys.add(p.key)

    def verify(self, signed, kind, payload_type, scope):
        require(kind in payload_types() and payload_type is payload_types()[kind] and
                type(signed) is Signed and signed.kind == kind and type(signed.payload) is payload_type and
                signed.scope == scope and signed.payload.scope == scope, 'network_receipt_contract_invalid')
        role = {'approval':'operator','install':'installer','capture':'capture','matrix':'validator','apply_ack':'host','readback':'validator'}[kind]
        p = self.principals.get(signed.principal)
        require(p is not None and p.role == role and p.scope == scope, 'network_principal_not_authorized')
        signed.payload.__post_init__()
        raw = canonical(kind, signed.principal, signed.scope, signed.payload)
        require(type(signed.signature) is str and hmac.compare_digest(
            signed.signature, hmac.new(p.key, raw, hashlib.sha256).hexdigest()), 'forged_network_receipt')
        return signed.payload
