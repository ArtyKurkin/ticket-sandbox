from contextlib import closing
from dataclasses import replace
from copy import deepcopy
from pathlib import Path
import sqlite3
from threading import Event,Thread
import unittest
from unittest.mock import patch,Mock
from trusted_checker_runtime.profiles import Denied
from trusted_checker_physical.authorization import Activation,Deadline
from trusted_checker_physical.io import LinuxIO
from trusted_checker_physical.rules import name,rules_hash
from trusted_checker_physical.journal import PhysicalJournal
from trusted_checker_physical.installer import IssuedBatch
from .support import Lab,uuid


class InstallerTests(unittest.TestCase):
    def setUp(self):self.l=Lab();self.addCleanup(self.l.close)

    def test_default_disabled_before_any_host_io(self):
        l=self.l;l.activation.enabled=False
        with self.assertRaises(Denied):l.install('bootstrap')
        self.assertEqual(l.io.calls,[]);self.assertEqual(l.api.calls,[])
        physical=Activation(l.auth)
        io=LinuxIO(physical)
        with patch('subprocess.Popen',side_effect=AssertionError('forbidden')) as spawn:
            with self.assertRaises(Denied):io.run('nft_version',l.budget())
        spawn.assert_not_called()

    def test_explicit_physical_approval_not_root(self):
        l=self.l;l.activation.approval=None
        with self.assertRaises(Denied):l.install('bootstrap')
        l.activation.approve(l.sign(replace(l.approval,permission='review_only'),'approval'))
        with self.assertRaises(Denied):l.install('bootstrap')
        self.assertEqual(l.io.calls,[])

    def test_linux_only(self):
        l=self.l;a=Activation(l.auth,enabled=True);a.approval=l.approval
        with patch('platform.system',return_value='Darwin'),self.assertRaises(Denied):a.check('read')

    def test_readonly_permission_never_mutates(self):
        l=self.l;l.activation.approval=replace(l.approval,permission='readonly')
        with self.assertRaises(Denied):l.install('bootstrap')
        self.assertEqual(l.io.calls,[])

    def test_forged_approval(self):
        l=self.l
        with self.assertRaises(Denied):l.installer.register(replace(l.sign(l.approval,'approval'),signature='0'*64))

    def test_no_arbitrary_nft_bytes_or_generic_commands(self):
        l=self.l;a=Activation(l.auth,enabled=True);a.approval=l.approval;io=LinuxIO(a)
        with patch('platform.system',return_value='Linux'),patch('subprocess.Popen') as spawn:
            for operation,payload in (('nft_apply',b'flush ruleset'),('evil',None)):
                with self.subTest(operation=operation),self.assertRaises(Denied):io.run(operation,l.budget(),payload=payload)
            with self.assertRaises(Denied):io.run('nft_apply',l.budget(),payload=IssuedBatch(uuid(),b'{}',l.clock()+30))
        spawn.assert_not_called()

    def test_atomic_installed_readback_and_duplicate(self):
        l=self.l;key=uuid();budget=l.budget();one=l.install('bootstrap',key,budget);two=l.install('bootstrap',key,budget)
        self.assertEqual(one,two);self.assertEqual(one['status'],'offline_verified');self.assertEqual(len(l.batches),1)
        self.assertTrue(all('create' in c for c in l.batches[0]['nftables'][:1]))
        l.install('active');self.assertEqual(l.generation,2)
        deletes=[c['delete']['table'] for c in l.batches[-1]['nftables'] if 'delete' in c]
        self.assertEqual(deletes,[{'family':'bridge','handle':100},{'family':'inet','handle':101}])
        with self.assertRaises(Denied):l.install('bootstrap',key,l.budget(31))

    def test_failed_atomic_never_retries(self):
        l=self.l;key=uuid();budget=l.budget()
        def fail(stage):raise OSError('SECRET')
        l.apply_hook=fail
        with self.assertRaises(Denied):l.install('bootstrap',key,budget)
        self.assertEqual(l.install('bootstrap',key,budget)['status'],'quarantined')
        self.assertEqual(len(l.batches),1);self.assertTrue(l.journal.stopped())
        with l.journal.transaction() as db:self.assertIsNone(db.execute("SELECT 1 FROM docs WHERE kind='receipt'").fetchone())

    def test_lost_nft_response_unknown_not_readback_adopted(self):
        l=self.l;key=uuid();budget=l.budget()
        def lose(stage):
            if stage=='after':raise OSError('lost')
        l.apply_hook=lose
        with self.assertRaises(Denied):l.install('bootstrap',key,budget)
        l.apply_hook=None
        with self.assertRaises(Denied):l.install('rollback')
        self.assertEqual(len(l.batches),1)
        self.assertEqual(l.installer.recover_ownership(key,l.trace(key),l.budget())['status'],'ownership_only')
        result=l.install('rollback');self.assertEqual(result['operation'],'rollback')
        self.assertTrue(l.journal.stopped())

    def test_mock_trace_cannot_recover_as_physical(self):
        l=self.l;key=uuid()
        def lose(stage):
            if stage=='after':raise OSError()
        l.apply_hook=lose
        with self.assertRaises(Denied):l.install('bootstrap',key)
        with self.assertRaises(Denied):l.installer.recover_ownership(key,l.trace(key,'physical_linux'),l.budget())

    def test_forged_trace_wrong_binding(self):
        l=self.l;key=uuid()
        def lose(stage):
            if stage=='after':raise OSError()
        l.apply_hook=lose
        with self.assertRaises(Denied):l.install('bootstrap',key)
        trace=l.trace(key)
        for field,value in (('transaction_digest','0'*64),('host_boot_uuid',uuid()),('generation',99)):
            with self.subTest(field=field),self.assertRaises(Denied):
                l.installer.recover_ownership(key,l.sign(replace(trace.payload,**{field:value}),'transaction'),l.budget())
        with self.assertRaises(Denied):l.installer.recover_ownership(key,replace(trace,signature='0'*64),l.budget())

    def test_foreign_table_before_install(self):
        l=self.l;l.rules={'nftables':[{'table':{'family':'bridge','name':'foreign','handle':77}}]}
        with self.assertRaises(Denied):l.install('bootstrap')
        self.assertEqual(l.batches,[])

    def test_partial_readback_quarantine(self):
        l=self.l
        def corrupt(stage):
            if stage=='after':l.rules['nftables'].pop()
        l.apply_hook=corrupt
        with self.assertRaises(Denied):l.install('bootstrap')
        self.assertTrue(l.journal.stopped())

    def test_foreign_handle_no_rollback_delete(self):
        l=self.l;l.active()
        next(i['table'] for i in l.rules['nftables'] if 'table' in i)['handle']=999
        with self.assertRaises(Denied):l.install('rollback')
        self.assertEqual(len(l.batches),2)

    def test_kill_during_nft_records_unknown(self):
        l=self.l
        l.apply_hook=lambda stage:l.journal.stop() if stage=='after' else None
        with self.assertRaises(Denied):l.install('bootstrap')
        self.assertTrue(l.journal.stopped());self.assertEqual(len(l.batches),1)
        # Synchronous apply+readback preserved exact ownership for rollback.
        l.apply_hook=None;self.assertEqual(l.install('rollback')['operation'],'rollback')

    def test_rollback_failure_stays_blocked(self):
        l=self.l;l.active()
        l.apply_hook=lambda stage:(_ for _ in ()).throw(OSError())
        with self.assertRaises(Denied):l.install('rollback')
        with self.assertRaises(Denied):l.install('active')
    def test_rollback_after_expiry_retains_only_recovery_capability(self):
        l=self.l;l.active();l.clock.advance(3601);l.journal.stop()
        self.assertEqual(l.install('rollback')['operation'],'rollback')
        with self.assertRaises(Denied):l.install('active')
    def test_rollback_after_runner_namespace_exit(self):
        l=self.l;l.active();del l.api.attrs[l.binding.runner.container_id]
        l.links=[p for p in l.links if p['ifindex']!=l.binding.runner.ifindex]
        self.assertEqual(l.install('rollback')['operation'],'rollback')

    def test_deadline_after_nft_no_verified_receipt(self):
        l=self.l;l.apply_hook=lambda stage:l.clock.advance(31) if stage=='after' else None
        with self.assertRaises(Denied):l.install('bootstrap')
        self.assertTrue(l.journal.stopped())

    def test_deadline_not_extended_and_clock_rollback(self):
        l=self.l;budget=l.budget(8);l.clock.advance(8)
        with self.assertRaises(Denied):budget.remaining()
        budget=l.budget(8);l.clock.advance(-1)
        with self.assertRaises(Denied):budget.remaining()

    def test_crash_dispatch_is_durable(self):
        l=self.l;key=uuid();budget=l.budget()
        l.apply_hook=lambda stage:(_ for _ in ()).throw(SystemExit())
        with self.assertRaises(SystemExit):l.install('bootstrap',key,budget)
        self.assertEqual(l.install('bootstrap',key,budget)['status'],'dispatched')
        self.assertEqual(len(l.batches),1)

    def test_crash_after_apply_recovery_releases_only_rollback(self):
        l=self.l;key=uuid();budget=l.budget()
        def crash(stage):
            if stage=='after':raise SystemExit()
        l.apply_hook=crash
        with self.assertRaises(SystemExit):l.install('bootstrap',key,budget)
        l.apply_hook=None;l.installer.recover_ownership(key,l.trace(key),l.budget())
        self.assertEqual(l.install('rollback')['operation'],'rollback')
        with self.assertRaises(Denied):l.install('active')

    def test_concurrent_physical_dispatch_one_apply(self):
        l=self.l;entered=Event();release=Event();results=[]
        def pause(stage):
            if stage=='before':entered.set();assert release.wait(5)
        l.apply_hook=pause
        def run():
            try:results.append(l.install('bootstrap'))
            except Denied:results.append('denied')
        worker=Thread(target=run);worker.start()
        try:
            self.assertTrue(entered.wait(5))
            with self.assertRaises(Denied):l.install('bootstrap')
        finally:release.set();worker.join(5)
        self.assertFalse(worker.is_alive());self.assertEqual(len(l.batches),1)

    def test_foreign_db_unchanged_and_journal_origin(self):
        l=self.l;path=Path(l.tmp.name)/'foreign.physical.sqlite3'
        with closing(sqlite3.connect(path)) as db,db:db.execute('CREATE TABLE sandbox_checkrun(id INTEGER)')
        before=path.read_bytes()
        with self.assertRaises(Denied):PhysicalJournal(path,'physical_linux')
        self.assertEqual(before,path.read_bytes())
        with self.assertRaises(Denied):PhysicalJournal(l.journal.path,'physical_linux')
        l.install('bootstrap')
        with l.journal.transaction() as db:
            with self.assertRaises(sqlite3.IntegrityError):db.execute('DELETE FROM docs')
            with self.assertRaises(sqlite3.IntegrityError):db.execute("UPDATE operations SET receipt='{}'")
