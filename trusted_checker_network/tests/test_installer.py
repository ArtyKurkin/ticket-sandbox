from copy import deepcopy
from contextlib import closing
from dataclasses import replace
import json
from pathlib import Path
import sqlite3
from threading import Thread,Event
import unittest
from trusted_checker_runtime.profiles import Denied
from trusted_checker_network.contracts import HostSnapshot,POLICY
from trusted_checker_network.rules import rules_hash,transaction_for,table_name
from trusted_checker_network.store import NetworkStore
from .support import NetworkLab,uuid


class InstallerTests(unittest.TestCase):
    def setUp(self):self.l = NetworkLab();self.addCleanup(self.l.close)

    def test_atomic_transition_readback_and_duplicate(self):
        l=self.l;l.install('bootstrap');key=uuid();deadline=l.clock()+8
        first=l.install('active',key,deadline);second=l.install('active',key,deadline)
        self.assertEqual(first,second);self.assertEqual(len(l.host.calls),2)
        self.assertEqual(l.installer.check(l.approval,active=True).generation,2)
        transaction=l.host.transactions[-1]['nftables']
        self.assertEqual([c['delete']['table']['name'] for c in transaction[:2]], [table_name(l.approval.approval_uuid)]*2)
        with self.assertRaises(Denied):l.install('active',key,deadline+1)
        from trusted_checker_network.contracts import InstallReceipt
        signed=l.installer.attestation(l.approval,key)
        self.assertEqual(l.verifier.verify(signed,'install',InstallReceipt,l.scope).generation,2)

    def test_unapproved_rules_even_with_operator_hash(self):
        l=self.l;bad=deepcopy(l.active_rules);bad['nftables'].pop()
        approval=replace(l.approval,active_digest=rules_hash(bad))
        with self.assertRaises(Denied):l.installer.register(l.signers['operator'].sign('approval',approval),l.bootstrap_rules,bad,l.runtime_approval)
        self.assertEqual(l.host.calls,[])

    def test_forged_operator_and_foreign_binding(self):
        l=self.l;signed=l.signers['operator'].sign('approval',l.approval)
        with self.assertRaises(Denied):l.installer.register(replace(signed,signature='0'*64),l.bootstrap_rules,l.active_rules,l.runtime_approval)
        with self.assertRaises(Denied):l.installer.register(signed,l.bootstrap_rules,l.active_rules,replace(l.runtime_approval,approval_uuid=uuid()))

    def test_install_error_no_success_receipt(self):
        l=self.l
        def fail(*args):raise OSError('SECRET')
        l.host.on_apply=fail
        with self.assertRaises(Denied):l.install('bootstrap')
        with l.store.transaction() as db:
            self.assertEqual(db.execute('SELECT status FROM jobs').fetchone()[0],'quarantined')
            self.assertNotIn('SECRET',str(list(db.execute('SELECT * FROM jobs'))))
        with self.assertRaises(Denied):l.install('bootstrap')

    def test_lost_ack_restart_never_reapply_recovery_only_bootstrap(self):
        l=self.l;key=uuid();deadline=l.clock()+8
        def lose(stage,host):
            if stage=='after':raise OSError('lost')
        l.host.on_apply=lose
        with self.assertRaises(Denied):l.install('bootstrap',key,deadline)
        l.installer=l.new_installer();l.host.on_apply=None
        self.assertEqual(l.install('bootstrap',key,deadline)['status'],'quarantined')
        self.assertEqual(len(l.host.calls),1)
        result=l.installer.recover(l.approval,key,l.host.trace[key])
        self.assertEqual(result['operation'],'rollback');self.assertEqual(len(l.host.calls),2)
        with self.assertRaises(Denied):l.install('active')

    def test_crash_after_apply_committed_intent_survives(self):
        l=self.l;key=uuid();deadline=l.clock()+8
        def crash(stage,host):
            if stage=='after':raise SystemExit()
        l.host.on_apply=crash
        with self.assertRaises(SystemExit):l.install('bootstrap',key,deadline)
        l.installer=l.new_installer()
        self.assertEqual(l.install('bootstrap',key,deadline)['status'],'dispatched')
        self.assertEqual(len(l.host.calls),1)
        with self.assertRaises(Denied):l.install('bootstrap')

    def test_foreign_recovery_trace_cannot_delete(self):
        l=self.l;key=uuid();deadline=l.clock()+8
        def lose(stage,host):
            if stage=='after':raise OSError()
        l.host.on_apply=lose
        with self.assertRaises(Denied):l.install('bootstrap',key,deadline)
        trace=l.host.trace[key]
        for field,value in (('owner_uuid',uuid()),('binding_digest','0'*64),('generation',99),('context_uuid',uuid())):
            with self.subTest(field=field):
                changed=l.signers['host'].sign('apply_ack',replace(trace.payload,**{field:value}))
                with self.assertRaises(Denied):l.installer.recover(l.approval,key,changed)
        self.assertEqual(len(l.host.calls),1)

    def test_rollback_foreign_host_never_mutates(self):
        l=self.l;l.active()
        l.host.snapshot_value=replace(l.snapshot,binding=replace(l.binding,host_boot_uuid=uuid()))
        with self.assertRaises(Denied):l.install('rollback')
        self.assertEqual(len(l.host.calls),2)

    def test_foreign_name_collision_never_adopted(self):
        l=self.l;l.host.rules=deepcopy(l.active_rules)
        original=deepcopy(l.host.rules)
        with self.assertRaises(Denied):l.install('bootstrap')
        self.assertEqual(l.host.rules,original);self.assertIsNone(l.host.owner)

    def test_foreign_writer_during_atomic_activation(self):
        l=self.l;l.install('bootstrap');foreign=uuid()
        l.host.on_apply=lambda stage,host:setattr(host,'owner',foreign) if stage=='before' else None
        with self.assertRaises(Denied):l.install('active')
        self.assertEqual(l.host.owner,foreign);self.assertEqual(l.host.generation,1)

    def test_monotonic_budget_even_wall_clock_static(self):
        l=self.l;times=iter((0,2,2,2))
        l.installer.monotonic=lambda:next(times)
        with self.assertRaises(Denied):l.install('bootstrap')

    def test_partial_and_foreign_readback_restore_bootstrap(self):
        for corrupt in ('partial','foreign'):
            with self.subTest(corrupt=corrupt):
                l=NetworkLab();self.addCleanup(l.close);l.install('bootstrap')
                def change(host):
                    host.on_read=None
                    if corrupt=='partial':host.rules['nftables'].pop()
                    else:host.owner=uuid()
                l.host.on_read=change
                with self.assertRaises(Denied):l.install('active')
                if corrupt=='partial':self.assertEqual(rules_hash(l.host.rules),l.approval.bootstrap_digest)
                else:self.assertEqual(len(l.host.calls),2) # No deletion on foreign ownership.

    def test_rollback_failure_holds_circuit(self):
        l=self.l;l.install('bootstrap')
        def change(host):host.rules['nftables'].pop();host.on_read=None;host.on_apply=lambda *a:(_ for _ in ()).throw(OSError())
        l.host.on_read=change
        with self.assertRaises(Denied):l.install('active')
        with l.store.transaction() as db:self.assertEqual(db.execute('SELECT blocked FROM network_state').fetchone()[0],1)
        with self.assertRaises(Denied):l.install('active')

    def test_kill_activation_restores_deny(self):
        l=self.l;l.install('bootstrap')
        l.host.on_apply=lambda stage,host:l.store.stop() if stage=='after' else None
        with self.assertRaises(Denied):l.install('active')
        self.assertTrue(l.store.stopped());self.assertEqual(rules_hash(l.host.rules),l.approval.bootstrap_digest)

    def test_kill_during_rollback_cannot_reenable(self):
        l=self.l;l.active()
        l.host.on_apply=lambda stage,host:l.store.stop()
        self.assertEqual(l.install('rollback')['operation'],'rollback')
        with self.assertRaises(Denied):l.install('active')

    def test_deadline_before_and_during_activation(self):
        l=self.l
        with self.assertRaises(Denied):l.install('bootstrap',deadline=l.clock())
        self.assertEqual(len(l.host.calls),0);l.install('bootstrap')
        l.host.on_apply=lambda stage,host:l.clock.advance(9) if stage=='after' else None
        with self.assertRaises(Denied):l.install('active')
        self.assertEqual(rules_hash(l.host.rules),l.approval.bootstrap_digest)

    def test_apply_budget_not_exit_zero(self):
        l=self.l;l.host.on_apply=lambda stage,host:l.clock.advance(1.1) if stage=='after' else None
        with self.assertRaises(Denied):l.install('bootstrap')

    def test_concurrent_activation_one_dispatch(self):
        l=self.l;l.install('bootstrap');entered=Event();release=Event();results=[]
        def hook(stage,host):
            if stage=='before':entered.set();self.assertTrue(release.wait(5))
        l.host.on_apply=hook
        def activate():
            try:results.append(l.install('active'))
            except Denied:results.append('denied')
        thread=Thread(target=activate);thread.start()
        try:
            self.assertTrue(entered.wait(5))
            with self.assertRaises(Denied):l.install('active')
        finally:release.set();thread.join(5)
        self.assertFalse(thread.is_alive());self.assertEqual(len(l.host.calls),2);self.assertIsInstance(results[0],dict)

    def test_topology_and_generation_drift(self):
        l=self.l
        for field,value in (('pid',999),('process_start_ticks',999),('netns_inode',999),('ifindex',99),('interface','vethChanged')):
            with self.subTest(field=field):
                changed=replace(l.binding,runner=replace(l.binding.runner,**{field:value}))
                l.host.snapshot_value=replace(l.snapshot,binding=changed,physical_ports=(changed.target.interface,changed.runner.interface))
                with self.assertRaises(Denied):l.install('bootstrap')
        l.host.snapshot_value=l.snapshot
        l.host.generation=7
        with self.assertRaises(Denied):l.install('bootstrap')

    def test_extra_bridge_or_interface_rejected(self):
        l=self.l
        for change in ({'bridge_names':('tcsh0','docker0')},{'runner_interfaces':(2,3)},
                       {'physical_ports':('vethTarget','vethRunner','vethForeign')}):
            with self.subTest(change=change),self.assertRaises(Denied):replace(l.snapshot,**change)

    def test_kernel_dependency_is_not_assumed(self):
        for change in ({'br_netfilter':True},{'bridge_conntrack':False}):
            with self.subTest(change=change),self.assertRaises(Denied):replace(self.l.snapshot,**change)

    def test_priority_and_foreign_table_rejection(self):
        l=self.l
        chains=[c['add']['chain'] for c in l.active_rules['nftables'] if 'chain' in c['add']]
        self.assertTrue(all(c['prio']==0 for c in chains if c['family']=='bridge'))
        with self.assertRaises(Denied):transaction_for(uuid(),l.active_rules,replacing=True)

    def test_append_only_store_and_foreign_db(self):
        l=self.l;l.install('bootstrap')
        with l.store.transaction() as db:
            with self.assertRaises(sqlite3.IntegrityError):db.execute("DELETE FROM documents")
            with self.assertRaises(sqlite3.IntegrityError):db.execute("UPDATE jobs SET receipt='{}'")
        path=Path(l.tmp.name)/'foreign.network.sqlite3'
        with closing(sqlite3.connect(path)) as db,db:db.execute('CREATE TABLE sandbox_checkrun(id INTEGER)')
        original=path.read_bytes()
        with self.assertRaises(Denied):NetworkStore(path)
        self.assertEqual(original,path.read_bytes())
