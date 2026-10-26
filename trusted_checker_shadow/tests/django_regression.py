"""Explicit Django test label only; independent unittest discovery needs no Django.

All academic records below are fixtures in Django's temporary TEST database.
The shadow execution itself must issue ZERO queries through Django.
"""

from dataclasses import asdict, replace
from pathlib import Path
import tempfile
from unittest.mock import patch
from uuid import uuid4

from django.db import connection
from django.test.utils import CaptureQueriesContext

from sandbox.models import TaskAttempt, TraineeProfile
from sandbox.services.checks import run_attempt_check
from sandbox.services.ledger_evidence import program_evidence
from sandbox.services.progress import build_sandbox_queue_progress
from sandbox.tests.base import SandboxTestCase

from trusted_checker_shadow.backend import FakeExecutionBackend, FakeScenario
from trusted_checker_shadow.contracts import CandidateMetadata, OperatorRequest, Verdict
from trusted_checker_shadow.coordinator import OfflineCoordinator
from trusted_checker_shadow.enrollment import FakeTrustedAuthority
from trusted_checker_shadow.predicate import FakeTransport, HTTPResponse, TransportFault
from trusted_checker_shadow.state import ShadowStore
from .support import Clock, fixture


class LegacyIsolationTests(SandboxTestCase):
    def snapshot(self):
        tables = [table for table in connection.introspection.table_names()
                  if table.startswith(("sandbox_", "achievements_", "roadmap_", "traineediary_"))]
        with connection.cursor() as cursor:
            result = {}
            for table in tables:
                cursor.execute("SELECT * FROM " + connection.ops.quote_name(table))
                result[table] = sorted(cursor.fetchall(), key=repr)
        return result

    def test_all_shadow_outcomes_leave_academic_rows_and_progress_unchanged(self):
        user = self.create_user("shadow-isolation", level=TraineeProfile.Level.L1)
        queue = self.create_queue("l1")
        task = self.create_task(queue, "service-bind-localhost", order=1)
        task.requires_manual_review = True
        task.save(update_fields=["requires_manual_review"])
        attempt = TaskAttempt.objects.create(user=user, task=task)
        with patch("sandbox.services.checks.check_task_container", return_value=(0, "ordinary fixture OK")), \
             patch("sandbox.services.checks.notify_user_completed_all_tasks"):
            run_attempt_check(attempt=attempt, user_id=user.pk)
        before = self.snapshot()
        progress_before = asdict(build_sandbox_queue_progress(user))
        ledger_before = program_evidence(user.pk)
        seed = fixture(attempt.pk)
        seed = replace(seed, target=replace(seed.target, owner_id=user.pk))
        authority = FakeTrustedAuthority("fake-authority", (seed,))
        enrollment = authority.enroll(CandidateMetadata(seed.target, "offline_fixture"),
                                     fixture_uuid=seed.fixture_uuid, operator_id="operator-unit")
        clock = Clock()
        with tempfile.TemporaryDirectory() as directory:
            store = ShadowStore(Path(directory) / "test.shadow.sqlite3")
            store.set_enabled(True, operator_id="operator-unit", now=clock())
            for transport, expected in (
                (FakeTransport(HTTPResponse(200, b"APP OK: customer service is running\n")), Verdict.PASSED),
                (FakeTransport(HTTPResponse(500, b"bad")), Verdict.FAILED),
                (FakeTransport(fault=TransportFault.TIMEOUT), Verdict.UNKNOWN),
            ):
                coordinator = OfflineCoordinator(store, authority, FakeExecutionBackend(FakeScenario(transport=transport)),
                                                 operator_id="operator-unit", clock=clock)
                request = OperatorRequest(str(uuid4()), enrollment.enrollment_uuid, attempt.pk, user.pk,
                                          seed.target.scope, str(uuid4()), clock()+8)
                with CaptureQueriesContext(connection) as queries:
                    report = coordinator.submit(request, enrollment)
                self.assertEqual(len(queries), 0)
                self.assertEqual(report.verdict.result, expected)
                self.assertEqual(self.snapshot(), before)
                self.assertEqual(asdict(build_sandbox_queue_progress(user)), progress_before)
                self.assertEqual(program_evidence(user.pk), ledger_before)
