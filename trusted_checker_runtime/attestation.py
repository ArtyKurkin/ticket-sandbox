"""Authenticated local receipt boundary, not Docker/host cryptographic attestation.

Signing keys are injected by trusted installation code, never loaded from an
approval/request, persisted in the journal, or sent to the uncredentialed runner.
Only tests provide a signing implementation in this stage.
"""

from dataclasses import asdict, dataclass, field
import hashlib
import hmac
import json

from .contracts import (CleanupConfirmation, CreateResponse, CreateTrace, DaemonObservation,
                        EgressEvidence, EgressValidation, IdentityObservation, NetworkEvidence,
                        ProbeResponse, RunnerObservation, RuntimeApproval, atom, full_id, scope)
from .profiles import require


ROLES = {RuntimeApproval: "operator", DaemonObservation: "adapter", CreateResponse: "adapter",
         IdentityObservation: "adapter", NetworkEvidence: "adapter", RunnerObservation: "adapter",
         ProbeResponse: "adapter", EgressEvidence: "egress", EgressValidation: "validator", CleanupConfirmation: "recovery"}
ROLES[CreateTrace] = 'recovery'


def _safe(value):
    if type(value) is bytes:
        return {"byte_count": len(value), "sha256": hashlib.sha256(value).hexdigest()}
    if isinstance(value, dict):
        return {key: _safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_safe(item) for item in value]
    return value


def signing_bytes(payload, signer):
    require(type(payload) in ROLES, "receipt_type_not_supported")
    return json.dumps({"domain": "tc-runtime-boundary-v1", "type": type(payload).__name__,
                       "signer": signer, "payload": _safe(asdict(payload))},
                      sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


@dataclass(frozen=True)
class Attestation:
    payload: RuntimeApproval | DaemonObservation | CreateResponse | CreateTrace | IdentityObservation | NetworkEvidence | EgressEvidence | EgressValidation | RunnerObservation | ProbeResponse | CleanupConfirmation
    signer: str
    signature: str

    def __post_init__(self):
        require(type(self.payload) in ROLES, "receipt_type_not_supported")
        self.payload.__post_init__()
        atom(self.signer, ROLES[type(self.payload)]+":")
        full_id(self.signature)

    @property
    def digest(self):
        return hashlib.sha256(signing_bytes(self.payload, self.signer)+self.signature.encode()).hexdigest()


@dataclass(frozen=True)
class SignerGrant:
    principal: str
    role: str
    scopes: tuple[str, ...]
    key: bytes = field(repr=False)

    def __post_init__(self):
        require(self.role in ("operator", "adapter", "egress", "validator", "recovery"), "signer_role_invalid")
        atom(self.principal, self.role+":")
        require(type(self.key) is bytes and len(self.key) >= 32, "signer_key_invalid")
        require(type(self.scopes) is tuple and 0 < len(self.scopes) <= 8, "signer_scope_invalid")
        for value in self.scopes:
            scope(value)


class ReceiptVerifier:
    def __init__(self, grants):
        self._grants = {}
        keys = set()
        for grant in grants:
            require(type(grant) is SignerGrant, "signer_grant_required")
            grant.__post_init__()
            require(grant.principal not in self._grants and grant.key not in keys, "signer_key_separation_required")
            keys.add(grant.key)
            self._grants[grant.principal] = grant

    def authorize_operator(self, principal):
        grant = self._grants.get(principal)
        require(grant is not None and grant.role == "operator", "operator_not_authorized")

    def verify(self, receipt, expected_type, expected_scope):
        require(type(receipt) is Attestation and type(receipt.payload) is expected_type, "receipt_contract_invalid")
        receipt.__post_init__()
        grant = self._grants.get(receipt.signer)
        require(grant is not None and grant.role == ROLES[expected_type] and
                expected_scope in grant.scopes and receipt.payload.scope == expected_scope, "receipt_signer_not_authorized")
        signature = hmac.new(grant.key, signing_bytes(receipt.payload, receipt.signer), hashlib.sha256).hexdigest()
        require(hmac.compare_digest(signature, receipt.signature), "receipt_signature_invalid")
        if expected_type is RuntimeApproval:
            require(receipt.signer == receipt.payload.operator_principal, "approval_operator_mismatch")
        return receipt.payload
