"""Local signing port. Keys are explicitly injected; never read from requests/env."""
import hashlib
import hmac
from trusted_checker_runtime.attestation import Attestation, ROLES, SignerGrant, signing_bytes
from trusted_checker_runtime.profiles import require


class LocalSigner:
    def __init__(self, grant):
        require(type(grant) is SignerGrant, 'signer_installation_required')
        grant.__post_init__()
        self._grant = grant

    def sign(self, payload):
        grant = self._grant
        require(ROLES.get(type(payload)) == grant.role and payload.scope in grant.scopes, 'signer_scope_or_role_invalid')
        return Attestation(payload, grant.principal,
                           hmac.new(grant.key, signing_bytes(payload, grant.principal), hashlib.sha256).hexdigest())
