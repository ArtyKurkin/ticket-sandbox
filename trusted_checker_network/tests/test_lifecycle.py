from dataclasses import asdict,replace
import ast
from pathlib import Path
import unittest
from unittest.mock import Mock,patch
from trusted_checker_live.tests.support import LiveLab
from trusted_checker_live.adapter import TrustedDockerAdapter
from trusted_checker_runtime.contracts import RunRequest
from trusted_checker_runtime.profiles import Denied
from trusted_checker_runtime.live_contract import LIVE_POLICY
from trusted_checker_network.lifecycle import MockNetworkLifecycle
from trusted_checker_network.timing import PROPOSAL
from .support import NetworkLab,uuid


class LifecycleTests(unittest.TestCase):
    def setUp(self):self.live=LiveLab();self.addCleanup(self.live.close)

    def connect(self,modifier=None):
        live=self.live;live.provision_live();self.sessions=[]
        def factory(authority,run_id):
            lab=NetworkLab(live,run_id);self.net=lab
            if modifier:modifier(lab)
            session=MockNetworkLifecycle(authority,lab.installer,lab.collector,lab.approval,run_id)
            self.sessions.append(session);return session
        live.runtime.mock_network_factory=factory

    def test_full_order_rst_finish_cleanup(self):
        self.connect();report=self.live.submit_live()
        self.assertEqual(report['terminal']['result'],'failed')
        self.assertEqual(report['cleanup'],'confirmed')
        self.assertTrue(self.live.api.released)
        self.assertEqual(self.sessions[0].stage,'cleanup_confirmed')
        self.assertEqual(self.net.host.generation,3)

    def test_fixed_http_scoped_pass(self):
        self.connect(lambda l:setattr(l,'response_flags',18))
        from trusted_checker_live.runner import packet
        import base64
        live=self.live
        live.api.http=packet(live.network.target_ipv4,status=200,body=b'APP OK: customer service is running\n',complete=True,transport='none')
        report=live.submit_live()
        self.assertEqual(report['terminal']['result'],'passed')
        self.assertEqual(report['criteria_scope'],'external_ipv4_http_only')
        self.assertEqual(report['cleanup'],'confirmed')

    def test_missing_matrix_never_probe_or_positive(self):
        self.connect(lambda l:setattr(l,'modify_capture',lambda c:replace(c,packets_dropped=1)))
        report=self.live.submit_live()
        self.assertEqual(report['terminal']['result'],'unknown');self.assertFalse(self.live.api.released)
        self.assertTrue(self.net.store.stopped());self.assertEqual(self.live.api.starts,2)

    def test_after_probe_loss_never_publish_pass(self):
        def configure(l):
            count=[0]
            def fail(c):
                count[0]+=1
                return replace(c,packets_dropped=1) if count[0]==2 else c
            l.modify_capture=fail
        self.connect(configure);report=self.live.submit_live()
        self.assertTrue(self.live.api.released);self.assertEqual(report['terminal']['result'],'unknown')

    def test_publication_loss_never_finish(self):
        def configure(l):
            count=[0]
            def fail(c):
                count[0]+=1
                return replace(c,endpoint_available=False) if count[0]==3 else c
            l.modify_capture=fail
        self.connect(configure);report=self.live.submit_live()
        self.assertEqual(report['terminal']['result'],'unknown');self.assertNotIn('wait',self.live.api.calls)

    def test_identity_drift_cannot_probe(self):
        self.connect(lambda l:setattr(l.host,'snapshot_value',replace(l.snapshot,binding=replace(l.binding,generation_uuid=uuid()))))
        report=self.live.submit_live()
        self.assertEqual(report['terminal']['result'],'unknown');self.assertFalse(self.live.api.released)

    def test_duplicate_command_no_second_activation(self):
        self.connect();report=self.live.submit_live();calls=len(self.net.host.calls)
        again=self.live.runtime.submit(self.live.run_request,self.live.enrollment)
        self.assertEqual(report['id'],again['id']);self.assertEqual(calls,len(self.net.host.calls))

    def test_cleanup_pending_not_operationally_complete(self):
        self.connect();self.live.runtime.cleanup.confirm=Mock(side_effect=Denied('cleanup_unconfirmed'))
        report=self.live.submit_live()
        self.assertEqual(report['cleanup'],'pending')
        self.assertEqual(self.sessions[0].stage,'finish_verified')
        with self.assertRaises(Denied):self.sessions[0].cleaned()

    def test_protocol_error_after_activation_restores_bootstrap(self):
        self.connect();self.live.api.http={'invalid':'SECRET'}
        report=self.live.submit_live()
        self.assertEqual(report['terminal']['result'],'unknown')
        self.assertTrue(self.net.store.stopped())
        from trusted_checker_network.rules import rules_hash
        self.assertEqual(rules_hash(self.net.host.rules),self.net.approval.bootstrap_digest)

    def test_no_network_session_resume_after_process_loss(self):
        self.connect();self.live.submit_live();session=self.sessions[0]
        with self.assertRaises(Denied):MockNetworkLifecycle(self.live.authority,self.net.installer,self.net.collector,
                                                        self.net.approval,session.run_id)

    def test_real_factory_blocked_before_witness_or_client(self):
        live=self.live;live.authority.set_enabled(True);witness=Mock(side_effect=AssertionError('must not connect'))
        adapter=TrustedDockerAdapter(live.authority,live.approval.approval_uuid,live.endpoint,live.adapter.signer,witness_reader=witness)
        with self.assertRaisesRegex(Denied,'physical_network_boundary_not_accepted'):adapter.daemon(uuid())
        witness.assert_not_called()

    def test_network_proof_cannot_sign_live_receipt(self):
        l=NetworkLab();self.addCleanup(l.close);l.active();proof=l.measure()
        from trusted_checker_runtime.contracts import EgressValidation
        with self.assertRaises(Denied):self.live.verifier.verify(proof,EgressValidation,l.scope)

    def test_timing_proposal_separate_and_versioned(self):
        self.assertEqual(LIVE_POLICY.run_seconds,8.0)
        with self.assertRaises(Denied):PROPOSAL.fits(8)
        self.assertTrue(PROPOSAL.fits(30))
        values=asdict(PROPOSAL)
        self.assertEqual(sum(v for k,v in values.items() if type(v) is float and k!='total'),30)
        with self.assertRaises(Denied):replace(PROPOSAL,total=8.0)

    def test_new_package_has_no_live_or_legacy_io_imports(self):
        root=Path(__file__).parents[1]
        banned=('socket','subprocess','docker','django','sandbox','achievements','roadmap','traineediary','requests','http','ctypes')
        for file in root.glob('*.py'):
            tree=ast.parse(file.read_text())
            for node in ast.walk(tree):
                if isinstance(node,ast.Import):names=[n.name for n in node.names]
                elif isinstance(node,ast.ImportFrom):names=[node.module or '']
                else:continue
                self.assertFalse(any(n.split('.')[0] in banned for n in names),str(file))
