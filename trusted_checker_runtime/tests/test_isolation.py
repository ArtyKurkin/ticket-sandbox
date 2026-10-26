import ast
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from dataclasses import replace
import json
import multiprocessing
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
from threading import Event
from unittest import TestCase

from trusted_checker_runtime.contracts import ProvisionRequest, Resource
from trusted_checker_runtime.journal import RuntimeJournal
from trusted_checker_runtime.profiles import Denied, LIMITS, RUNNER_PROFILE, TARGET_PROFILE
from .support import Lab, uuid


def process_provision(path, grants, daemon, request, clock_value, output):
    from trusted_checker_runtime.attestation import ReceiptVerifier
    from trusted_checker_runtime.authority import RuntimeTargetAuthority
    try:
        authority = RuntimeTargetAuthority(RuntimeJournal(path), ReceiptVerifier(grants),
            operator_principal='operator:unit', approved_daemon=daemon, clock=lambda: clock_value)
        output.put(('ok', authority.provision(request).intent_uuid))
    except Exception as exc:
        output.put(('error', type(exc).__name__))


class IsolationTests(TestCase):
    def setUp(self):
        self.x = Lab()
        self.addCleanup(self.x.close)

    def test_processes_share_one_provision_mapping(self):
        x = self.x
        x.authority.set_enabled(True)
        request = ProvisionRequest(uuid(), x.approval.approval_uuid, x.attempt)
        ctx = multiprocessing.get_context('spawn')
        output = ctx.Queue()
        processes = [ctx.Process(target=process_provision, args=(str(x.journal.path), x.grants, x.daemon,
                      replace(request, request_uuid=uuid()), x.clock(), output)) for _ in range(2)]
        try:
            for proc in processes:
                proc.start()
            results = [output.get(timeout=30) for _ in processes]
            self.assertEqual([r[0] for r in results], ['ok', 'ok'])
            self.assertEqual(len({r[1] for r in results}), 1)
        finally:
            for proc in processes:
                if proc.pid:
                    proc.join(30)
                    if proc.is_alive():
                        proc.terminate(); proc.join(30)
                    self.assertEqual(proc.exitcode, 0)
                    proc.close()
            output.close(); output.join_thread()

    def test_kill_is_serialized_with_already_dispatched_fake_create(self):
        x = self.x
        intent = x.provision()
        permit = x.authority.begin_create(intent, x.daemon_receipt(intent.intent_uuid))
        entered, release, kill_requested = Event(), Event(), Event()

        def bounded_create():
            with x.authority.create_fence(permit):
                entered.set()
                if not release.wait(30):
                    raise AssertionError('test watchdog')
                x.creates += 1

        def disable():
            kill_requested.set()
            x.new_authority().kill()

        with ThreadPoolExecutor(max_workers=2) as pool:
            creating = pool.submit(bounded_create)
            try:
                self.assertTrue(entered.wait(30))
                killing = pool.submit(disable)
                self.assertTrue(kill_requested.wait(30))
            finally:
                release.set()
            creating.result(timeout=30)
            killing.result(timeout=30)
        x.authority.record_create_response(permit, x.response(intent, permit))
        self.assertEqual(x.authority.report(intent.intent_uuid, Resource.TARGET)['phase'], 'quarantined')
        self.assertEqual(x.creates, 1)

    def test_disabled_after_permit_but_before_dispatch_never_invokes_create(self):
        x = self.x
        intent = x.provision()
        permit = x.authority.begin_create(intent, x.daemon_receipt(intent.intent_uuid))
        x.authority.kill()
        with self.assertRaises(Denied):
            with x.authority.create_fence(permit):
                self.fail('create after disable')
        self.assertEqual(x.creates, 0)

    def test_sql_guards_protect_terminal_binding_and_append_only_history(self):
        x = self.x
        x.enrolled(); x.running(); x.finish()
        statements = ["UPDATE rt_objects SET terminal='{}' WHERE kind='run'",
                      "UPDATE rt_objects SET deadline=deadline+1", "DELETE FROM rt_objects",
                      "DELETE FROM rt_documents", "UPDATE rt_requests SET fingerprint='x'",
                      "DELETE FROM rt_ownership", "UPDATE rt_meta SET version=2"]
        for sql in statements:
            with self.subTest(sql=sql), self.assertRaises(sqlite3.IntegrityError):
                with x.journal.transaction() as db:
                    db.execute(sql)
        self.assertEqual(x.authority.publish(x.run)['result'], 'passed')

    def test_foreign_database_rejected_without_any_byte_change(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'foreign.runtime.sqlite3'
            with closing(sqlite3.connect(path)) as db, db:
                db.execute('CREATE TABLE sandbox_checkrun(id INTEGER)')
            before = path.read_bytes()
            with self.assertRaises(Denied):
                RuntimeJournal(path)
            self.assertEqual(path.read_bytes(), before)

    def test_separate_journal_name_permissions_and_symlink(self):
        x = self.x
        self.assertEqual(x.journal.path.stat().st_mode & 0o777, 0o600)
        for name in ('db.sqlite3', 'sandbox.sqlite3', 'unit.shadow.sqlite3'):
            with self.subTest(name=name), self.assertRaises(Denied):
                RuntimeJournal(Path(x.tmp.name)/name)
        link = Path(x.tmp.name)/'link.runtime.sqlite3'
        link.symlink_to(x.journal.path)
        with self.assertRaises(Denied):
            RuntimeJournal(link)

    def test_runtime_profile_is_task_specific_and_immutable(self):
        self.assertEqual(TARGET_PROFILE.user, '0:0')
        self.assertFalse(TARGET_PROFILE.read_only)
        self.assertEqual(tuple(t[0] for t in TARGET_PROFILE.tmpfs), ('/tmp', '/run'))
        self.assertEqual(RUNNER_PROFILE.cap_drop, ('ALL',))
        self.assertEqual(RUNNER_PROFILE.user, '10001:10001')
        for value, changes in ((TARGET_PROFILE, {'editable_application': False}),
                               (RUNNER_PROFILE, {'user': '0:0'}), (LIMITS, {'max_concurrent_runs': 2}),
                               (LIMITS, {'api_seconds': 4.0})):
            with self.subTest(changes=changes), self.assertRaises(Denied):
                replace(value, **changes)

    def test_no_legacy_network_sdk_or_process_imports_in_package(self):
        root = Path(__file__).resolve().parents[1]
        allowed = {'trusted_checker_shadow.policy', 'trusted_checker_shadow.predicate'}
        forbidden = {'django', 'sandbox', 'achievements', 'roadmap', 'traineediary', 'docker',
                     'socket', 'requests', 'http', 'urllib', 'subprocess', 'ctypes', 'importlib'}
        for path in root.glob('*.py'):
            tree = ast.parse(path.read_text())
            for node in ast.walk(tree):
                modules = [a.name for a in node.names] if isinstance(node, ast.Import) else [node.module or ''] if isinstance(node, ast.ImportFrom) else []
                for module in modules:
                    self.assertNotIn(module.split('.')[0], forbidden, str(path))
                    if module.startswith('trusted_checker_shadow'):
                        self.assertIn(module, allowed)
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                    self.assertNotIn(node.func.id, ('eval', 'exec', '__import__'))

    def test_import_in_fresh_process_has_no_socket_subprocess_or_client_constructor(self):
        # Only this test launches a fresh local Python; the imported package is
        # prohibited from launching processes, opening sockets or legacy clients.
        script = '''
from unittest.mock import patch
import importlib, socket, subprocess, sys
with patch.object(socket, 'socket', side_effect=AssertionError('network forbidden')), patch.object(subprocess, 'Popen', side_effect=AssertionError('process forbidden')):
    for name in ('profiles','contracts','attestation','journal','boundary','authority','interfaces'):
        importlib.import_module('trusted_checker_runtime.'+name)
assert not any(name.split('.')[0] in ('django','docker','sandbox') for name in sys.modules)
'''
        result = subprocess.run([sys.executable, '-B', '-c', script], cwd=Path(__file__).resolve().parents[2],
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_bounded_report_journal_contains_no_body_key_or_exception_text(self):
        x = self.x
        x.enrolled(); x.running(); x.finish(body=b'SECRET-CUSTOMER-CONTENT')
        report = x.authority.report(x.run)
        serialized = json.dumps(report)
        self.assertLessEqual(len(serialized.encode()), 16384)
        self.assertNotIn('SECRET', serialized)
        raw = x.journal.path.read_bytes()
        self.assertNotIn(b'SECRET-CUSTOMER-CONTENT', raw)
        with x.journal.transaction() as db:
            docs = [r[0] for r in db.execute('SELECT body FROM rt_documents')]
        for value in docs:
            self.assertNotIn('"key":', value)
            self.assertNotIn('"signature":', value)
            self.assertNotIn('"body":', value)

    def test_owned_target_cannot_be_deleted_by_runner_cleanup(self):
        x = self.x
        x.enrolled(); x.running(); x.finish()
        forged = x.sign(replace(x.cleanup().payload, container_id=x.target_id, resource=Resource.TARGET))
        with self.assertRaises(Denied):
            x.authority.record_cleanup(forged)
        self.assertEqual(x.authority.report(x.intent.intent_uuid, Resource.TARGET)['phase'], 'enrolled')
