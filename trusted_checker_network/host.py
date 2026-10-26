"""Sealed mock-only host boundary. No subprocess, socket or Linux operations."""
from dataclasses import dataclass, replace
from copy import deepcopy
from trusted_checker_runtime.contracts import full_id, stamp, uid, scope
from trusted_checker_runtime.profiles import require
from .contracts import MODE
from .rules import rules_hash, exact_tables, transaction_for


@dataclass(frozen=True)
class ApplyAck:
    context_uuid: str
    scope: str
    binding_digest: str
    owner_uuid: str
    rules_digest: str
    generation: int
    observed_at: float
    tables: tuple[tuple[str,str],...]
    mode: str = MODE
    def __post_init__(self):
        uid(self.context_uuid); uid(self.owner_uuid); scope(self.scope)
        full_id(self.binding_digest); full_id(self.rules_digest); stamp(self.observed_at)
        require(type(self.generation) is int and self.generation > 0 and self.mode == MODE and
                type(self.tables) is tuple and len(self.tables) == 2, 'apply_ack_invalid')


@dataclass(frozen=True)
class Readback:
    context_uuid: str
    scope: str
    binding_digest: str
    owner_uuid: str
    generation: int
    rules_digest: str
    tables: tuple[tuple[str,str],...]
    observed_at: float
    mode: str = MODE
    def __post_init__(self):
        uid(self.context_uuid); scope(self.scope); uid(self.owner_uuid)
        full_id(self.binding_digest); full_id(self.rules_digest); stamp(self.observed_at)
        require(type(self.generation) is int and self.generation > 0 and self.mode == MODE, 'readback_invalid')


class MockNetworkHost:
    def __init__(self, snapshot, clock, host_signer):
        self.snapshot_value, self.clock, self.signer = snapshot, clock, host_signer
        self.rules = None; self.owner = None; self.generation = 0
        self.calls = []; self.trace = {}; self.on_apply = None; self.on_read = None; self.on_capture = None
        self.capture_factory = None
        self.transactions = []

    def snapshot(self):
        return replace(self.snapshot_value, observed_at=self.clock())

    def apply(self, transaction, approval, rules, expected_generation):
        require(self.generation == expected_generation and (self.owner is None if expected_generation == 0 else
                self.owner == approval.approval_uuid), 'foreign_or_changed_rules_ownership')
        self.calls.append((transaction, rules_hash(rules)))
        self.transactions.append(transaction_for(approval.approval_uuid,rules,replacing=expected_generation > 0))
        if self.on_apply: self.on_apply('before', self)
        # Simulated compare-and-apply linearization. A name collision or foreign
        # writer between dispatch and apply never permits replacement/deletion.
        require(self.generation == expected_generation and
                (self.owner is None and self.rules is None if expected_generation == 0 else
                 self.owner == approval.approval_uuid), 'atomic_rules_ownership_changed')
        anchor = ('host_boot_uuid','host_identity_digest','host_netns_inode','daemon','network_id',
                  'bridge_name','bridge_ifindex','bridge_mac')
        require(all(getattr(self.snapshot_value.binding,k)==getattr(approval.binding,k) for k in anchor),
                'atomic_host_identity_changed')
        if rules_hash(rules)==approval.active_digest:
            require(self.snapshot_value.binding==approval.binding,'atomic_physical_port_changed')
        self.rules = deepcopy(rules); self.owner = approval.approval_uuid; self.generation += 1
        ack = ApplyAck(transaction, approval.scope, approval.binding.digest, approval.approval_uuid,
            rules_hash(rules), self.generation, self.clock(), exact_tables(rules))
        signed = self.signer.sign('apply_ack',ack)
        self.trace[transaction] = signed  # Independent protected mock host transaction journal.
        if self.on_apply: self.on_apply('after',self)
        return signed

    def read(self):
        if self.on_read: self.on_read(self)
        return self.owner, self.generation, deepcopy(self.rules)

    def capture(self, approval, request):
        require(self.capture_factory is not None, 'capture_backend_missing')
        if self.on_capture: self.on_capture(self)
        return self.capture_factory(approval,request)


class IndependentReadback:
    def __init__(self, host, signer, verifier, clock):
        require(type(host) is MockNetworkHost, 'only_mock_host_permitted')
        self.host,self.signer,self.verifier,self.clock = host,signer,verifier,clock

    def verify(self, approval, transaction, expected_rules, expected_generation):
        owner,generation,rules = self.host.read()
        require(owner == approval.approval_uuid and generation == expected_generation and
                rules_hash(rules) == rules_hash(expected_rules) and exact_tables(rules) == exact_tables(expected_rules),
                'independent_rules_readback_mismatch')
        readback = Readback(transaction,approval.scope,approval.binding.digest,owner,generation,
                            rules_hash(rules),exact_tables(rules),self.clock())
        signed = self.signer.sign('readback',readback)
        return self.verifier.verify(signed,'readback',Readback,approval.scope)
