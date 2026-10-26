"""Operator-only install algorithm; exact MockNetworkHost is the sole backend."""
from dataclasses import asdict
import json
import time
from uuid import uuid4
from trusted_checker_runtime.profiles import require, Denied
from trusted_checker_shadow.policy import digest
from .contracts import NetworkApproval, InstallReceipt, POLICY
from .host import MockNetworkHost, ApplyAck, IndependentReadback
from .rules import rules_hash, exact_tables, approved_rules
from .store import NetworkStore, normalize


class TrustedRulesInstaller:
    def __init__(self, store, host, reader, signer, verifier, operator, clock, *, monotonic=time.monotonic):
        require(type(store) is NetworkStore and type(host) is MockNetworkHost and type(reader) is IndependentReadback,
                'mock_only_install_boundary')
        require(reader.host is host and signer.principal.role == 'installer' and
                reader.signer.principal.name != signer.principal.name, 'independent_readback_required')
        self.store,self.host,self.reader,self.signer,self.verifier = store,host,reader,signer,verifier
        self.operator,self.clock = operator,clock
        self.monotonic = monotonic

    def register(self, signed, bootstrap, active, runtime_approval):
        from trusted_checker_runtime.contracts import RuntimeApproval
        approval = self.verifier.verify(signed,'approval',NetworkApproval,signed.scope)
        require(type(runtime_approval) is RuntimeApproval and runtime_approval.schema_version == 2 and
                runtime_approval.digest == approval.binding.runtime_approval_digest and
                runtime_approval.daemon == approval.binding.daemon and runtime_approval.scope == approval.scope and
                runtime_approval.network.network_id == approval.binding.network_id and
                runtime_approval.network.target_ipv4 == approval.binding.target.ipv4 and
                runtime_approval.network.runner_ipv4 == approval.binding.runner.ipv4, 'runtime_network_binding_mismatch')
        require(approval.operator == self.operator and approval.created_at <= self.clock() < approval.expires_at,
                'operator_approval_invalid')
        require(rules_hash(bootstrap) == approval.bootstrap_digest and rules_hash(active) == approval.active_digest and
                exact_tables(bootstrap) == exact_tables(active), 'unapproved_ruleset')
        require(bootstrap == approved_rules(approval.approval_uuid,runtime_approval,approval.binding,active=False) and
                active == approved_rules(approval.approval_uuid,runtime_approval,approval.binding,active=True),
                'fixed_rules_required')
        with self.store.transaction() as db:
            self.store.put(db,'approval',approval.approval_uuid,approval)
            self.store.put(db,'bootstrap',approval.approval_uuid,bootstrap)
            self.store.put(db,'active',approval.approval_uuid,active)
            db.execute("INSERT OR IGNORE INTO network_state VALUES(?,'new',0,0)",(approval.approval_uuid,))
        return approval

    def _approved(self, db, approval):
        require(type(approval) is NetworkApproval and normalize(approval) == self.store.get(db,'approval',approval.approval_uuid),
                'network_approval_not_issued')

    def _guard(self, approval, deadline, *, recovery=False):
        snapshot = self.host.snapshot()
        if recovery:
            # Restoring our known tables to deny does not require a live runner.
            # Host/daemon/network ownership must still be exact, never inferred
            # from a table/interface name after a host/session change.
            fields = ('host_boot_uuid','host_identity_digest','host_netns_inode','daemon','network_id',
                      'bridge_name','bridge_ifindex','bridge_mac')
            require(all(getattr(snapshot.binding,k) == getattr(approval.binding,k) for k in fields) and
                    snapshot.bridge_names == ('tcsh0',), 'rollback_host_identity_drift')
        else:
            snapshot.__post_init__()
            require(snapshot.binding == approval.binding, 'install_host_identity_drift')
        require(not snapshot.foreign_bridge_hooks and snapshot.netlink_lost == 0,
                'install_host_identity_drift')
        if not recovery:
            require(not self.store.stopped() and approval.created_at <= self.clock() < approval.expires_at and
                    self.clock() < deadline, 'install_cancelled_or_expired')

    def _quarantine(self, approval, job, reason):
        with self.store.transaction() as db:
            db.execute("UPDATE jobs SET status='quarantined',reason=? WHERE id=? AND receipt IS NULL",(reason,job))
            db.execute("UPDATE network_state SET stage='quarantined',blocked=1 WHERE approval=?",(approval.approval_uuid,))
            self.store.event(db,job,'quarantined')

    def install(self, approval, operation, request_uuid, deadline):
        require(operation in ('bootstrap','active','rollback'), 'install_operation_invalid')
        from trusted_checker_runtime.contracts import uid,stamp
        uid(request_uuid);stamp(deadline)
        recovery = operation == 'rollback'
        with self.store.transaction() as db:
            self._approved(db,approval)
            rules = self.store.get(db,'active' if operation == 'active' else 'bootstrap',approval.approval_uuid)
            fingerprint = digest({'approval':normalize(approval),'operation':operation,'rules':rules,'deadline':deadline})
            old = db.execute('SELECT * FROM jobs WHERE id=?',(request_uuid,)).fetchone()
            if old:
                require(old['payload_hash'] == fingerprint,'install_request_conflict')
                return json.loads(old['receipt']) if old['receipt'] else {'status':old['status'],'job':request_uuid}
            state = db.execute('SELECT * FROM network_state WHERE approval=?',(approval.approval_uuid,)).fetchone()
            if not recovery:
                require(not state['blocked'] and not db.execute("SELECT 1 FROM jobs WHERE status IN ('dispatched','quarantined')").fetchone(),
                        'network_circuit_open')
                require(state['stage'] == ('new' if operation == 'bootstrap' else 'bootstrap'), 'invalid_install_transition')
            else:
                require(state['generation'] > 0, 'rollback_ownership_unproven')
            self._guard(approval,deadline,recovery=recovery)
            db.execute('INSERT INTO jobs VALUES(?,?,?,?,?,?,NULL)',(request_uuid,approval.approval_uuid,operation,
                       fingerprint,'dispatched','none'))
            self.store.put(db,'intent',request_uuid,{'approval':approval.approval_uuid,'rules':rules_hash(rules),
                'expected_generation':state['generation'],'deadline':deadline,'operation':operation})
            self.store.event(db,request_uuid,'dispatched')
            expected_generation = state['generation']
        started = self.clock()
        monotonic_end = self.monotonic()+min(POLICY.apply_seconds,max(0,deadline-started))
        try:
            # Persisted dispatch is committed BEFORE this mock host mutation.
            signed_ack = self.host.apply(request_uuid,approval,rules,expected_generation)
            ack = self.verifier.verify(signed_ack,'apply_ack',ApplyAck,approval.scope)
            require((ack.context_uuid,ack.owner_uuid,ack.binding_digest,ack.rules_digest,ack.generation,ack.tables) ==
                (request_uuid,approval.approval_uuid,approval.binding.digest,rules_hash(rules),expected_generation+1,exact_tables(rules)),
                'apply_ack_binding_mismatch')
            require(started <= ack.observed_at <= self.clock(),'apply_ack_time_invalid')
            with self.store.transaction() as db:
                self.store.put(db,'ownership',request_uuid,ack)
                db.execute('UPDATE network_state SET generation=? WHERE approval=?',(ack.generation,approval.approval_uuid))
                self.store.event(db,request_uuid,'owned')
            self._guard(approval,deadline,recovery=recovery)
            require(self.clock()-started <= POLICY.apply_seconds, 'apply_budget_exceeded')
            readback = self.reader.verify(approval,request_uuid,rules,ack.generation)
            self._guard(approval,deadline,recovery=recovery)
            require(self.monotonic() < monotonic_end,'install_monotonic_deadline')
            receipt = InstallReceipt(str(uuid4()),request_uuid,approval.scope,approval.binding.digest,operation,
                request_uuid,rules_hash(rules),ack.generation,self.clock())
            self.signer.sign('install',receipt)  # Verify role and scope before persisting/exporting receipt.
            with self.store.transaction() as db:
                self.store.put(db,'readback',request_uuid,readback)
                self.store.put(db,'receipt',request_uuid,receipt)
                db.execute("UPDATE jobs SET status='verified',receipt=? WHERE id=?",(json.dumps(normalize(receipt)),request_uuid))
                db.execute('UPDATE network_state SET stage=? WHERE approval=?',
                           ('active' if operation == 'active' else 'bootstrap',approval.approval_uuid))
                self.store.event(db,request_uuid,'verified')
            return normalize(receipt)
        except Exception:
            self._quarantine(approval,request_uuid,'install_outcome_unknown')
            if operation != 'rollback':
                try:self.install(approval,'rollback',str(uuid4()),self.clock()+POLICY.apply_seconds)
                except Exception:pass
            raise Denied('network_install_unknown') from None

    def attestation(self, approval, request_uuid):
        """Authenticated historical activation record; check() is still required.

        Re-sign the exact immutable issued DTO on replay, never host/operator
        supplied attributes. It does not authorize a new probe or mutation.
        """
        with self.store.transaction() as db:
            self._approved(db,approval)
            job = db.execute('SELECT * FROM jobs WHERE id=?',(request_uuid,)).fetchone()
            require(job is not None and job['approval'] == approval.approval_uuid and job['status'] == 'verified',
                    'activation_receipt_not_issued')
            receipt = InstallReceipt(**self.store.get(db,'receipt',request_uuid))
        return self.signer.sign('install',receipt)

    def recover(self, approval, failed_job, signed_trace):
        """Restore ownership only, then rollback; never adopt active as permission."""
        ack = self.verifier.verify(signed_trace,'apply_ack',ApplyAck,approval.scope)
        with self.store.transaction() as db:
            self._approved(db,approval)
            row = db.execute('SELECT * FROM jobs WHERE id=?',(failed_job,)).fetchone()
            require(row is not None and row['status'] in ('dispatched','quarantined') and row['approval'] == approval.approval_uuid,
                    'recovery_install_missing')
            intent = self.store.get(db,'intent',failed_job)
            require((ack.context_uuid,ack.owner_uuid,ack.binding_digest,ack.rules_digest,ack.generation) ==
                    (failed_job,approval.approval_uuid,approval.binding.digest,intent['rules'],intent['expected_generation']+1),
                    'recovery_apply_trace_mismatch')
            expected = self.store.get(db,'active' if intent['operation'] == 'active' else 'bootstrap',approval.approval_uuid)
            require(ack.tables == exact_tables(expected) and approval.created_at <= ack.observed_at <= self.clock(),
                    'recovery_apply_trace_invalid')
            self.store.put(db,'ownership',failed_job,ack)
            db.execute("UPDATE jobs SET status='quarantined',reason='recovered_ownership' WHERE id=?",(failed_job,))
            db.execute("UPDATE network_state SET stage='quarantined',generation=?,blocked=1 WHERE approval=?",
                       (ack.generation,approval.approval_uuid))
            self.store.event(db,failed_job,'recovered_ownership')
        return self.install(approval,'rollback',str(uuid4()),self.clock()+POLICY.apply_seconds)

    def check(self, approval, *, active):
        with self.store.transaction() as db:
            self._approved(db,approval)
            state = db.execute('SELECT * FROM network_state WHERE approval=?',(approval.approval_uuid,)).fetchone()
            require(not state['blocked'] and state['stage'] == ('active' if active else 'bootstrap') and
                    not self.store.stopped(), 'network_install_not_verified')
            expected = self.store.get(db,'active' if active else 'bootstrap',approval.approval_uuid)
            generation = state['generation']
        self._guard(approval,approval.expires_at)
        return self.reader.verify(approval,approval.approval_uuid,expected,generation)
