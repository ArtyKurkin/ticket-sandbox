"""Role-separated fixture authentication. No runtime receipt/signing service."""
from dataclasses import asdict, dataclass, field
import hashlib
import hmac
import json

from trusted_checker_runtime.contracts import atom, scope
from trusted_checker_runtime.profiles import require
from .counter_contracts import CounterApproval, CounterEvidence, PacketFixture, ReadbackFixture
from .counter_inventory import TopologyObservation

TYPES = {'approval': (CounterApproval, 'operator'), 'readback': (ReadbackFixture, 'reader'),
         'packets': (PacketFixture, 'packet'), 'topology': (TopologyObservation, 'observer'),
         'evidence': (CounterEvidence, 'validator')}


@dataclass(frozen=True)
class FixturePrincipal:
    name: str
    role: str
    scope: str
    key: bytes = field(repr=False)

    def __post_init__(self):
        require(self.role in ('operator', 'reader', 'packet', 'observer', 'validator'), 'counter_role_invalid')
        atom(self.name, self.role+':'); scope(self.scope)
        require(type(self.key) is bytes and len(self.key) >= 32, 'counter_key_invalid')


@dataclass(frozen=True)
class SignedCounter:
    kind: str
    principal: str
    payload: object
    signature: str


def canonical(kind, principal, payload):
    require(kind in TYPES and type(payload) is TYPES[kind][0], 'counter_domain_rejected')
    def encode(value):
        if type(value) is bytes: return {'size': len(value), 'sha256': hashlib.sha256(value).hexdigest()}
        if type(value) is dict: return {k: encode(v) for k,v in value.items()}
        if type(value) in (list, tuple): return [encode(v) for v in value]
        return value
    return json.dumps({'domain': 'tc-nft-counter-probe-v1-offline', 'kind': kind, 'principal': principal,
                       'payload': encode(asdict(payload))}, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


class FixtureAuthenticator:
    def __init__(self, principals):
        self.principals = {}; keys = set()
        for p in principals:
            require(type(p) is FixturePrincipal, 'counter_fixture_principal_required'); p.__post_init__()
            require(p.name not in self.principals and p.key not in keys, 'counter_key_separation_required')
            self.principals[p.name] = p; keys.add(p.key)

    def verify(self, signed, kind, scope):
        require(kind in TYPES and type(signed) is SignedCounter and signed.kind == kind and
                type(signed.payload) is TYPES[kind][0], 'counter_domain_rejected')
        p = self.principals.get(signed.principal)
        require(p is not None and p.role == TYPES[kind][1] and p.scope == signed.payload.scope == scope,
                'counter_signer_rejected')
        signed.payload.__post_init__()
        require(type(signed.signature) is str and hmac.compare_digest(signed.signature,
                hmac.new(p.key, canonical(kind, p.name, signed.payload), hashlib.sha256).hexdigest()),
                'counter_forged_receipt')
        if kind == 'approval': require(signed.payload.operator == p.name, 'counter_operator_mismatch')
        return signed.payload
