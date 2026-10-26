"""Versioned physical approval, distinct from all mock/live-v2 receipts."""
from dataclasses import dataclass,asdict,field
import hashlib
import hmac
import json
from trusted_checker_runtime.contracts import uid,stamp,full_id,atom
from trusted_checker_runtime.profiles import require,fixed
from trusted_checker_network.contracts import NetworkBinding
from trusted_checker_shadow.policy import digest


@dataclass(frozen=True)
class PhysicalProfile:
    profile_id: str = 'physical-linux-network-v4-review'
    version: int = 4
    execution_mode: str = 'physical_boundary_review_required'
    kernel_series: tuple = ('6.8','6.12')
    nft_series: tuple = ('1.0.9','1.1.0','1.1.1')
    max_output: int = 262144
    packet_limit: int = 256
    frame_limit: int = 128
    capture_seconds: float = 2.0
    operation_seconds: float = 3.0
    physical_default: bool = False
    packet_templates: str = 'header_nonce_peer_arp_v4'

    def __post_init__(self):fixed(self)
    @property
    def digest(self):return digest(asdict(self))


PROFILE=PhysicalProfile()


@dataclass(frozen=True)
class PhysicalApproval:
    approval_uuid: str
    operator: str
    binding: NetworkBinding
    bootstrap_digest: str
    active_digest: str
    source_digest: str
    created_at: float
    expires_at: float
    dedicated_vm: bool
    permission: str = 'review_only'
    profile_digest: str = PROFILE.digest

    def __post_init__(self):
        uid(self.approval_uuid);atom(self.operator,'operator:')
        require(type(self.binding) is NetworkBinding,'physical_binding_required');self.binding.__post_init__()
        for value in (self.bootstrap_digest,self.active_digest,self.source_digest,self.profile_digest):full_id(value)
        stamp(self.created_at);stamp(self.expires_at)
        require(0<self.expires_at-self.created_at<=3600 and self.dedicated_vm is True and
                self.permission in ('review_only','readonly','install_and_collect') and self.profile_digest==PROFILE.digest,
                'physical_approval_invalid')
    @property
    def scope(self):return self.binding.scope
    @property
    def digest(self):return digest(asdict(self))


@dataclass(frozen=True)
class Principal:
    name: str
    role: str
    scope: str
    key: bytes = field(repr=False)
    def __post_init__(self):
        require(self.role in ('operator','observer','validator','collector'),'physical_role_invalid')
        atom(self.name,self.role+':')
        from trusted_checker_runtime.contracts import scope
        scope(self.scope)
        require(type(self.key) is bytes and len(self.key)>=32,'physical_key_invalid')


@dataclass(frozen=True)
class TransactionTrace:
    context_uuid: str
    approval_digest: str
    transaction_digest: str
    rules_digest: str
    host_boot_uuid: str
    binding_digest: str
    generation: int
    table_handles: tuple
    committed_at: float
    source: str
    origin: str
    scope: str
    def __post_init__(self):
        uid(self.context_uuid);uid(self.host_boot_uuid);stamp(self.committed_at)
        for value in (self.approval_digest,self.transaction_digest,self.rules_digest,self.binding_digest):full_id(value)
        require(type(self.generation) is int and self.generation>0 and type(self.table_handles) is tuple and
                len(self.table_handles)==2 and all(type(h) is int and h>0 for h in self.table_handles) and
                self.source=='independent_committed_netlink_transaction' and self.origin in
                ('physical_linux','offline_simulation'),'physical_transaction_trace_invalid')


@dataclass(frozen=True)
class Signed:
    kind: str
    principal: str
    payload: object
    signature: str


class Authenticator:
    """Installation keys only. No key/env/discovery/signing endpoint."""
    def __init__(self,principals):
        self.principals={};keys=set()
        for p in principals:
            require(type(p) is Principal,'physical_principal_required');p.__post_init__()
            require(p.name not in self.principals and p.key not in keys,'physical_role_separation_required')
            self.principals[p.name]=p;keys.add(p.key)
    @staticmethod
    def raw(kind,principal,payload):
        from .collector import CollectionReport
        require((kind,type(payload)) in (('approval',PhysicalApproval),('transaction',TransactionTrace),('capture',CollectionReport)),
                'physical_receipt_type_invalid')
        return json.dumps({'domain':'tc-physical-v4','kind':kind,'principal':principal,'payload':asdict(payload)},
                          sort_keys=True,separators=(',',':'),allow_nan=False).encode()
    def verify(self,signed,kind,payload_type):
        require(kind in ('approval','transaction','capture') and type(signed) is Signed and signed.kind==kind and type(signed.payload) is payload_type,
                'physical_receipt_contract_invalid')
        p=self.principals.get(signed.principal)
        require(p is not None and p.scope==signed.payload.scope and
                p.role=={'approval':'operator','transaction':'observer','capture':'collector'}[kind],'physical_signer_not_authorized')
        signed.payload.__post_init__()
        raw=self.raw(kind,p.name,signed.payload)
        require(type(signed.signature) is str and hmac.compare_digest(signed.signature,hmac.new(p.key,raw,hashlib.sha256).hexdigest()),
                'physical_signature_invalid')
        if kind=='approval':require(signed.payload.operator==p.name,'physical_operator_mismatch')
        return signed.payload
