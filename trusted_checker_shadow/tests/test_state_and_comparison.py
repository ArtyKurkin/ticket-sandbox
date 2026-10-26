import ast
from contextlib import closing
from dataclasses import asdict, replace
import hashlib
import json
from pathlib import Path
import sqlite3
from uuid import uuid4

from trusted_checker_shadow.comparison import compare
from trusted_checker_shadow.contracts import OrdinaryEvidence, Reason, Rejected, Verdict
from trusted_checker_shadow.policy import CRITERIA_SCOPE
from trusted_checker_shadow.state import ShadowStore
from .support import ShadowCase


class StateTests(ShadowCase):
    def test_foreign_or_django_database_is_rejected_without_mutation(self):
        for name in ("legacy.sqlite3", "foreign.shadow.sqlite3"):
            path = Path(self.tmp.name) / name
            with closing(sqlite3.connect(path)) as db, db:
                db.execute("CREATE TABLE sandbox_checkrun(id INTEGER PRIMARY KEY,result TEXT)")
                db.execute("INSERT INTO sandbox_checkrun VALUES(1,'passed')")
            before = hashlib.sha256(path.read_bytes()).hexdigest()
            with self.assertRaisesRegex(Rejected, "dedicated_shadow_path_required|foreign_database_rejected"):
                ShadowStore(path)
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), before)
        link = Path(self.tmp.name) / "link.shadow.sqlite3"
        link.symlink_to(self.path)
        with self.assertRaisesRegex(Rejected, "dedicated_shadow_path_required"):
            ShadowStore(link)

    def test_store_only_owns_shadow_tables_and_mode_600(self):
        with closing(sqlite3.connect(self.path)) as db:
            tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        self.assertEqual(tables, ShadowStore.TABLES)
        self.assertEqual(self.path.stat().st_mode & 0o777, 0o600)

    def test_terminal_binding_and_audit_are_immutable_at_sql_boundary(self):
        report = self.enabled().submit(self.request(), self.enrollment)
        for sql in ("UPDATE shadow_runs SET result='{}'", "UPDATE shadow_runs SET lifecycle='running'",
                    "UPDATE shadow_runs SET execution_id='forged'", "DELETE FROM shadow_runs",
                    "UPDATE shadow_audit SET code='forged'", "DELETE FROM shadow_audit",
                    "UPDATE shadow_requests SET fingerprint='forged'"):
            with self.subTest(sql=sql), closing(sqlite3.connect(self.path)) as db:
                with self.assertRaises(sqlite3.IntegrityError):
                    db.execute(sql)
        self.assertEqual(self.coordinator.report(report.shadow_run_uuid), report)

    def test_legacy_module_imports_and_runtime_operations_are_absent(self):
        root = Path(__file__).parents[1]
        forbidden = {"django", "sandbox", "achievements", "roadmap", "traineediary", "docker",
                     "subprocess", "socket", "http", "requests", "urllib", "trusted_checker_poc"}
        for path in root.glob("*.py"):
            tree = ast.parse(path.read_text())
            for node in ast.walk(tree):
                names = ([alias.name for alias in node.names] if isinstance(node, ast.Import)
                         else [node.module] if isinstance(node, ast.ImportFrom) and node.level == 0 else [])
                for name in names:
                    self.assertNotIn(name.split(".")[0], forbidden, str(path))
        # There is no writer/connection injection point for any legacy model or DB.
        with self.assertRaises(TypeError):
            ShadowStore(self.path, legacy_connection=object())

    def test_sensitive_wrong_body_is_not_retained_in_report_or_database(self):
        from trusted_checker_shadow.backend import FakeExecutionBackend, FakeScenario
        from trusted_checker_shadow.predicate import FakeTransport, HTTPResponse
        secret = b"credentials=super-secret-client-content"
        self.backend = FakeExecutionBackend(FakeScenario(transport=FakeTransport(HTTPResponse(200, secret))))
        self.coordinator = self.make_coordinator()
        report = self.enabled().submit(self.request(), self.enrollment)
        self.assertEqual(report.verdict.reason, Reason.BODY)
        self.assertIsNone(report.verdict.response_digest)
        self.assertNotIn(secret.decode(), json.dumps(report.to_dict()))
        self.assertNotIn(secret, self.path.read_bytes())

    def test_report_diagnostics_are_bounded_and_strict_dto(self):
        request = self.request()
        report = self.enabled().submit(request, self.enrollment)
        for _ in range(100):
            repeated = self.coordinator.submit(request, self.enrollment)
        self.assertEqual(report, repeated)
        self.assertLessEqual(len(report.diagnostics), 16)
        self.assertEqual(report.audit_event_count, 7)
        self.assertNotIn("ownership_token", json.dumps(report.to_dict()))


class ComparisonTests(ShadowCase):
    def ordinary(self, **changes):
        target = self.fixture.target
        return replace(OrdinaryEvidence(target.attempt_id, target.owner_id, check_run_id=12,
            technical_execution_uuid=str(uuid4()), result=Verdict.PASSED, criteria_scope=CRITERIA_SCOPE,
            correlation_quality="same_generation_proven", runtime_binding_uuid=target.runtime_binding_uuid,
            generation=target.generation, observed_from=self.clock()-1, observed_until=self.clock()+1), **changes)

    def comparison(self, ordinary, result=Verdict.PASSED):
        return compare(ordinary, self.fixture.target, result, self.clock(), self.clock())

    def test_agrees_and_differs_only_with_same_scope_generation_and_window(self):
        ordinary = self.ordinary()
        before = asdict(ordinary)
        self.assertEqual(self.comparison(ordinary).status, "agrees")
        result = self.comparison(replace(ordinary, result=Verdict.FAILED))
        self.assertEqual(result.status, "differs")
        self.assertEqual(result.reason, "scoped_observations_only")
        self.assertEqual(asdict(ordinary), before)

    def test_legacy_failed_plus_peer_pass_is_not_legacy_bug_claim(self):
        result = self.comparison(self.ordinary(result=Verdict.FAILED, criteria_scope="full_task_legacy"))
        self.assertEqual((result.status, result.reason), ("incomparable", "criteria_scope_differs"))

    def test_missing_check_unknown_time_generation_and_quality_incomparable(self):
        for ordinary in (None, self.ordinary(check_run_id=None), self.ordinary(result=Verdict.UNKNOWN),
                         self.ordinary(correlation_quality="same_attempt_temporal"),
                         self.ordinary(generation=str(uuid4())),
                         self.ordinary(runtime_binding_uuid=str(uuid4())),
                         self.ordinary(observed_from=None, observed_until=None),
                         self.ordinary(observed_from=self.clock()-5, observed_until=self.clock()-1),
                         self.ordinary(attempt_id=3), self.ordinary(owner_id=22)):
            with self.subTest(ordinary=ordinary):
                self.assertEqual(self.comparison(ordinary).status, "incomparable")
        self.assertEqual(self.comparison(self.ordinary(), Verdict.UNKNOWN).reason, "outcome_unknown")

    def test_coordinator_correlation_refs_and_ordinary_snapshot_are_immutable(self):
        ordinary = self.ordinary()
        before = asdict(ordinary)
        report = self.enabled().submit(self.request(ordinary=ordinary), self.enrollment)
        self.assertEqual(report.comparison.status, "agrees")
        self.assertEqual(report.ordinary.check_run_id, ordinary.check_run_id)
        self.assertEqual(asdict(ordinary), before)
        with self.assertRaisesRegex(Rejected, "ordinary_identity_mismatch"):
            self.request(ordinary=replace(ordinary, attempt_id=99))
