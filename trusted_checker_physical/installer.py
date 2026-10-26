"""V4 physical adapter for the NetworkInstaller lifecycle, dormant by default.

V3 exact-type/mock gates are deliberately preserved. No duck-typed live injection.
"""
from dataclasses import asdict,dataclass
from copy import deepcopy
import json
from uuid import uuid4
from trusted_checker_runtime.profiles import require,Denied
from trusted_checker_runtime.contracts import uid
from trusted_checker_live.egress import canonical_readback
from trusted_checker_shadow.policy import digest
from .rules import recipes,transaction,name,exact_tables,rules_hash
from .contracts import PhysicalApproval,TransactionTrace
from .io import json_output
from .preflight import validate_ruleset


@dataclass(frozen=True)
class IssuedBatch:
    identifier: str
    payload: bytes
    absolute: float


class IndependentNftReadback:
    def __init__(self,activation,io):self.activation,self.io=activation,io
    def read(self,budget,approval,expected=None,handles=None):
        self.activation.check('read');raw=json_output(self.io.run('nft_read',budget))
        tables=(('bridge',name(approval.approval_uuid)),('inet',name(approval.approval_uuid)))
        validate_ruleset(raw,tables if expected is not None else ())
        if expected is None:return None
        require(canonical_readback(raw)==canonical_readback(expected),'physical_rules_readback_mismatch')
        found=tuple(item['table']['handle'] for item in raw['nftables'] if 'table' in item)
        require(len(found)==2 and all(type(h) is int and h>0 for h in found),'physical_table_handles_missing')
        require(handles is None or found==handles,'physical_table_replaced')
        return found


class PhysicalNetworkInstaller:
    def __init__(self,activation,io,reader,journal,preflight,inventory,runtime_approval):
        require(io is not reader.io and journal.origin==activation.origin and io.activation is activation and
                reader.activation is activation,'physical_independent_boundary_required')
        if not activation.offline:
            from .io import LinuxIO
            from .inventory import NamespaceInventory
            from .preflight import HostPreflight
            require(type(io) is LinuxIO and type(reader.io) is LinuxIO and type(reader) is IndependentNftReadback and
                    type(preflight) is HostPreflight and type(inventory) is NamespaceInventory,'physical_mock_host_forbidden')
        self.activation,self.io,self.reader,self.journal=activation,io,reader,journal
        self.preflight,self.inventory,self.runtime_approval=preflight,inventory,runtime_approval
    def register(self,signed):
        a=self.activation.approve(signed);r=self.runtime_approval;b=a.binding
        require(r.digest==b.runtime_approval_digest and r.daemon==b.daemon and r.network.network_id==b.network_id and
                r.network.target_ipv4==b.target.ipv4 and r.network.runner_ipv4==b.runner.ipv4,'physical_runtime_approval_mismatch')
        boot,active=(recipes(a.approval_uuid,r,b,active=flag) for flag in (False,True))
        require((rules_hash(boot),rules_hash(active))==(a.bootstrap_digest,a.active_digest),'physical_fixed_recipe_mismatch')
        from .artifacts import source_digest
        require(a.source_digest==source_digest(),'physical_artifact_source_mismatch')
        with self.journal.transaction() as db:
            self.journal.put(db,'approval','selected',asdict(a))
            self.journal.put(db,'recipe','bootstrap',boot);self.journal.put(db,'recipe','active',active)
        return a
    def _guard(self,budget,*,recovery=False):
        a=self.activation.check('mutate',recovery=recovery);budget.remaining()
        from .artifacts import source_digest
        require(a.source_digest==source_digest(),'physical_artifact_source_changed')
        if not recovery:require(not self.journal.stopped(),'physical_stop_latched')
        with self.journal.transaction() as db:
            require(self.journal.get(db,'approval','selected')==json.loads(json.dumps(asdict(a))),'physical_approval_not_issued')
        return a
    def install(self,operation,request_uuid,budget):
        require(operation in ('bootstrap','active','rollback'),'physical_install_operation_invalid');uid(request_uuid)
        recovery=operation=='rollback';a=self.activation.check('mutate',recovery=recovery);budget.remaining()
        with self.journal.transaction() as db:
            recipe=self.journal.get(db,'recipe','active' if operation=='active' else 'bootstrap')
            fp=digest({'approval':a.digest,'operation':operation,'deadline':budget.absolute,'recipe':rules_hash(recipe)})
            old=db.execute('SELECT * FROM operations WHERE id=?',(request_uuid,)).fetchone()
            if old:
                require(old['fingerprint']==fp,'physical_duplicate_conflict')
                return json.loads(old['receipt']) if old['receipt'] else {'status':old['phase'],'origin':self.activation.origin}
            state=dict(db.execute('SELECT * FROM control').fetchone())
            if not recovery:
                require(not state['blocked'] and not db.execute("SELECT 1 FROM operations WHERE phase IN ('dispatched','quarantined')").fetchone(),
                        'physical_circuit_open')
                require(state['stage']==('new' if operation=='bootstrap' else 'bootstrap'),'physical_transition_invalid')
            handles=tuple(json.loads(state['handles'])) if state['handles'] else None
            require(not recovery or handles is not None,'physical_rollback_ownership_unproven')
            previous=self.journal.get(db,'recipe',state['stage']) if state['stage'] in ('active','bootstrap') else None
        self._guard(budget,recovery=recovery)
        tables=exact_tables(recipe)
        # Read-only full host/profile + exact namespace verification before the
        # durable dispatch. These reads never confer ownership of existing tables.
        try:
            with self.activation.recovery_reads(recovery):
                self.preflight.check(budget,tables if handles else (),allow_missing=recovery)
                if not recovery:self.inventory.observe(budget)
                self.reader.read(budget,a,previous,handles)
        except Exception:
            with self.journal.transaction() as db:
                self.journal.put(db,'admission_unknown',request_uuid,{'approval':a.digest,'origin':self.activation.origin,
                                  'reason':'physical_preflight_or_readback_unknown'})
                db.execute('UPDATE control SET blocked=1')
            self.journal.stop()
            raise Denied('physical_preflight_or_readback_unknown') from None
        batch=transaction(a,recipe,handles)
        payload=json.dumps(batch,sort_keys=True,separators=(',',':')).encode()
        with self.journal.transaction() as db:
            require(not db.execute("SELECT 1 FROM operations WHERE phase='dispatched'").fetchone(),'physical_operation_busy')
            current=dict(db.execute('SELECT * FROM control').fetchone())
            require(current==state,'physical_install_state_changed')
            db.execute('INSERT INTO operations VALUES(?,?,?,NULL)',(request_uuid,fp,'dispatched'))
            self.journal.put(db,'intent',request_uuid,{'approval':a.digest,'transaction':digest(batch),
                'rules':rules_hash(recipe),'operation':operation,'generation':state['generation']+1,
                'binding':a.binding.digest,'deadline':budget.absolute})
        try:
            self._guard(budget,recovery=recovery)
            issued=self.activation._issue_batch(request_uuid,payload,budget.absolute)
            self.io.run('nft_apply',budget,payload=issued,recovery=recovery)
            # Exit0 isn't a recovery trace. Successful synchronous completion
            # plus independent exact readback creates initial durable ownership.
            with self.activation.recovery_reads(recovery):new_handles=self.reader.read(budget,a,recipe)
            with self.journal.transaction() as db:
                self.journal.put(db,'ownership',request_uuid,{'handles':new_handles,'rules':rules_hash(recipe),'binding':a.binding.digest})
                db.execute('UPDATE control SET handles=?,generation=?,stage=?',
                           (json.dumps(new_handles),state['generation']+1,'active' if operation=='active' else 'bootstrap'))
            if not recovery:self.inventory.observe(budget)
            self._guard(budget,recovery=recovery)
            result={'status':'offline_verified' if self.activation.offline else 'verified_readback',
                'origin':self.activation.origin,'context_uuid':request_uuid,'rules_digest':rules_hash(recipe),
                'generation':state['generation']+1,'operation':operation,'timings':deepcopy(budget.timings)}
            with self.journal.transaction() as db:
                db.execute("UPDATE operations SET phase='verified',receipt=? WHERE id=?",(json.dumps(result),request_uuid))
                self.journal.put(db,'receipt',request_uuid,result)
            return result
        except Exception:
            with self.journal.transaction() as db:
                db.execute("UPDATE operations SET phase='quarantined' WHERE id=? AND receipt IS NULL",(request_uuid,))
                db.execute('UPDATE control SET blocked=1')
            # Never re-apply after an uncertain outcome. Restore requires an
            # explicit rollback request with proven current ownership/readback.
            self.journal.stop()
            raise Denied('physical_install_unknown') from None
    def recover_ownership(self,request_uuid,signed_trace,budget):
        a=self._guard(budget,recovery=True)
        trace=self.activation.auth.verify(signed_trace,'transaction',TransactionTrace)
        require(trace.origin==self.activation.origin and trace.scope==a.scope,'physical_trace_origin_mismatch')
        with self.journal.transaction() as db:
            row=db.execute('SELECT * FROM operations WHERE id=?',(request_uuid,)).fetchone()
            require(row is not None and row['phase'] in ('dispatched','quarantined'),'physical_recovery_intent_missing')
            intent=self.journal.get(db,'intent',request_uuid)
            require((trace.context_uuid,trace.approval_digest,trace.transaction_digest,trace.rules_digest,
                     trace.binding_digest,trace.host_boot_uuid,trace.generation)==
                    (request_uuid,a.digest,intent['transaction'],intent['rules'],a.binding.digest,a.binding.host_boot_uuid,intent['generation']) and
                    a.created_at<=trace.committed_at<=min(intent['deadline'],self.activation.clock()),'physical_trace_binding_mismatch')
            stage='active' if intent['operation']=='active' else 'bootstrap'
            expected=self.journal.get(db,'recipe',stage)
        with self.activation.recovery_reads(True):
            self.preflight.check(budget,exact_tables(expected),allow_missing=True)
            self.reader.read(budget,a,expected,trace.table_handles)
        with self.journal.transaction() as db:
            self.journal.put(db,'recovered_ownership',request_uuid,{'handles':trace.table_handles,'origin':trace.origin})
            db.execute("UPDATE operations SET phase='quarantined' WHERE id=? AND receipt IS NULL",(request_uuid,))
            db.execute('UPDATE control SET handles=?,stage=?,generation=?,blocked=1',
                       (json.dumps(trace.table_handles),stage,trace.generation))
        return {'status':'ownership_only','origin':self.activation.origin,'probe_permitted':False}
