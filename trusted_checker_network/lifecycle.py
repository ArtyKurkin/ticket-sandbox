"""Supplemental gates for a mock Runtime Authority composition, never live I/O."""
from uuid import uuid4
from trusted_checker_runtime.authority import RuntimeTargetAuthority
from trusted_checker_runtime.contracts import Resource
from trusted_checker_runtime.profiles import require,Denied
from .collector import IndependentCollector,MatrixReceipt
from .installer import TrustedRulesInstaller
from .contracts import POLICY


class MockNetworkLifecycle:
    def __init__(self, authority, installer, collector, approval, run_id):
        require(type(authority) is RuntimeTargetAuthority and type(installer) is TrustedRulesInstaller and
                type(collector) is IndependentCollector and collector.installer is installer,
                'mock_network_lifecycle_required')
        self.authority,self.installer,self.collector,self.approval,self.run_id = authority,installer,collector,approval,run_id
        self.stage = 'new'; self.deadline = authority.report(run_id)['deadline']
        with installer.store.transaction() as db:
            installer._approved(db,approval)
            # Restart never resumes a partially activated/probed session.
            row = db.execute("SELECT 1 FROM documents WHERE kind='session' AND id=?",(run_id,)).fetchone()
            require(row is None,'network_session_resume_forbidden')
            installer.store.put(db,'session',run_id,{'binding':approval.binding.digest,'deadline':self.deadline})

    def _guard(self):
        a,b = self.authority,self.approval.binding
        require(not self.installer.store.stopped(),'network_stop_latched')
        with a.journal.transaction() as db:
            row,intent,approval = a._object(db,'run',self.run_id)
            a._current(db,approval,a._now(db),row)
            enrollment = a._enrollment_for_run(db,row,a.clock())
            runner = a.journal.get(db,'runner_live',self.run_id)
            target = enrollment.target
            require(approval.digest == b.runtime_approval_digest and intent.runtime_binding_uuid == b.runtime_binding_uuid and
                    intent.generation_uuid == b.generation_uuid and intent.daemon == b.daemon and
                    target.container_id == b.target.container_id and target.started_at == b.target.docker_started_at and
                    target.endpoints[0].endpoint_id == b.target.endpoint_id and
                    runner['container_id'] == b.runner.container_id and runner['started_at'] == b.runner.docker_started_at and
                    runner['endpoint']['endpoint_id'] == b.runner.endpoint_id and runner['endpoint']['network_id'] == b.network_id,
                    'network_runtime_binding_mismatch')
        self.installer._guard(self.approval,self.deadline)

    def _event(self, stage):
        with self.installer.store.transaction() as db:
            self.installer.store.put(db,'gate',self.run_id+':'+stage,{'stage':stage,'binding':self.approval.binding.digest,
                                      'at':self.authority.clock()})
        self.stage = stage

    def _fail(self):
        if self.stage == 'failed': return
        self.stage = 'failed'
        self.installer.store.stop()
        self.authority.abandon_run(self.run_id)
        try:self.installer.install(self.approval,'rollback',str(uuid4()),self.authority.clock()+POLICY.apply_seconds)
        except Exception:pass

    def abort(self):
        self._fail()

    def before_probe(self):
        try:
            require(self.stage == 'new','network_probe_replay')
            self._guard()
            self.installer.install(self.approval,'bootstrap',str(uuid4()),self.deadline)
            self.installer.check(self.approval,active=False)
            self._event('bootstrap_verified')
            self._guard();self._event('target_runner_identity_verified')
            self.installer.install(self.approval,'active',str(uuid4()),self.deadline)
            self._event('active_verified')
            self._matrix('probe_permitted')
        except Exception:
            self._fail();raise Denied('network_probe_not_permitted') from None

    def _matrix(self, stage):
        self._guard()
        signed = self.collector.measure(self.approval,str(uuid4()),self.deadline)
        receipt = self.collector.verifier.verify(signed,'matrix',MatrixReceipt,self.approval.scope)
        require(receipt.binding_digest == self.approval.binding.digest,'network_matrix_binding_mismatch')
        self._guard();self._event(stage)

    def after_probe(self):
        try:
            require(self.stage == 'probe_permitted','network_after_probe_out_of_order')
            self._matrix('after_probe_verified')
        except Exception:
            self._fail();raise Denied('network_after_probe_unknown') from None

    def before_publication(self):
        try:
            require(self.stage == 'after_probe_verified','network_publication_out_of_order')
            self._matrix('publication_permitted')
        except Exception:
            self._fail();raise Denied('network_publication_unknown') from None

    def finished(self):
        try:
            require(self.stage == 'publication_permitted','network_finish_out_of_order')
            self._guard()
            with self.authority.journal.transaction() as db:
                finished = self.authority.journal.get(db,'runner_finished',self.run_id)
                require(finished['container_id'] == self.approval.binding.runner.container_id and finished['exit_code'] == 0,
                        'network_finish_unproven')
            # Known owned tables are restored before runner namespace disappears.
            self.installer.install(self.approval,'rollback',str(uuid4()),self.deadline)
            self._event('finish_verified')
        except Exception:
            self._fail();raise Denied('network_finish_unknown') from None

    def cleaned(self):
        require(self.stage == 'finish_verified' and self.authority.report(self.run_id)['cleanup'] == 'confirmed',
                'network_cleanup_pending')
        self._event('cleanup_confirmed')

    def kill(self):
        self.installer.store.stop()
        self.authority.journal.request_stop()
        self._fail()
