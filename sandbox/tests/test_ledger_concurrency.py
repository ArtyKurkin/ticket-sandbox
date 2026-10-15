from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Event
from uuid import uuid4
from unittest import skipUnless
from unittest.mock import patch
from django.contrib.auth.models import User
from django.db import connection, close_old_connections, transaction, DatabaseError
from django.test import TransactionTestCase
from django.utils import timezone
from sandbox.models import Queue, Task, TaskAttempt, CheckRun
from sandbox.ledger_models import *
from sandbox.services import ledger
from sandbox.services.checks import run_attempt_check, try_mark_attempt_check_running
from sandbox.services.environments import (
    run_environment_restart,
    try_mark_environment_restarting,
)


@skipUnless(connection.vendor == "postgresql", "Requires PostgreSQL locks and guards")
class LedgerConcurrencyTests(TransactionTestCase):

    def setUp(self):
        (
            SandboxLedgerBoundary.objects.create(pk=1, enabled_at=timezone.now())
            if not SandboxLedgerBoundary.objects.exists()
            else None
        )
        self.user = User.objects.create_user("ledger-race")
        self.queue = Queue.objects.get_or_create(slug="l1", defaults={"name": "L1"})[0]
        self.task = Task.objects.create(
            queue=self.queue,
            slug="https-ipv4-listener",
            title="Task",
            order=1,
            requires_manual_review=True,
        )
        self.attempt = TaskAttempt.objects.create(user=self.user, task=self.task)

    def parallel(self, functions):
        barrier = Barrier(len(functions))

        def run(fn):
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                return fn()
            finally:
                connection.close()

        with ThreadPoolExecutor(max_workers=len(functions)) as pool:
            return [
                f.result(timeout=30) for f in [pool.submit(run, fn) for fn in functions]
            ]

    def test_same_request_one_ordinal_and_one_counter(self):
        op = uuid4()

        def request():
            return try_mark_attempt_check_running(
                attempt=TaskAttempt.objects.get(pk=self.attempt.pk), operation_id=op
            )

        self.assertCountEqual(self.parallel([request, request]), [True, False])
        self.attempt.refresh_from_db()
        self.assertEqual(self.attempt.attempts_count, 1)
        self.assertEqual(TechnicalCheckExecution.objects.count(), 1)

    def test_duplicate_delivery_one_checker_and_one_checkrun(self):
        try_mark_attempt_check_running(attempt=self.attempt)
        run_id = self.attempt._ledger_check_id
        with patch(
            "sandbox.services.checks.check_task_container", return_value=(1, "failed")
        ) as docker:
            self.parallel(
                [
                    lambda: run_attempt_check(
                        attempt=TaskAttempt.objects.get(pk=self.attempt.pk),
                        user_id=self.user.pk,
                        mark_as_running=False,
                        run_id=run_id,
                    )
                ]
                * 2
            )
        self.assertEqual(docker.call_count, 1)
        self.assertEqual(CheckRun.objects.count(), 1)

    def test_same_submission_receipt_and_review_return_unique(self):
        with ledger.writer():
            self.attempt.technical_passed_at = timezone.now()
            self.attempt.save(update_fields=["technical_passed_at"])
        op = uuid4()

        def submit():
            return ledger.submit_answer(
                TaskAttempt.objects.get(pk=self.attempt.pk), "answer", "report", op
            )[0].pk

        ids = self.parallel([submit, submit])
        self.assertEqual(ids[0], ids[1])
        with ledger.writer():
            self.attempt.client_answer = "answer"
            self.attempt.trainee_report = "report"
            self.attempt.save(update_fields=["client_answer", "trainee_report"])
        staff = User.objects.create_user("ledger-mentor-race", is_staff=True)
        review_id = uuid4()

        def review():
            return ledger.review_answer(
                self.attempt, staff, "needs_revision", "Fix", ids[0], review_id
            ).pk

        ids = self.parallel([review, review])
        self.assertEqual(ids[0], ids[1])
        self.assertEqual(SandboxAnswerReviewEvent.objects.count(), 1)

    def test_sql_guards_and_unsupported_update_marker(self):
        models = [
            SandboxLedgerBoundary,
            SandboxProgramManifest,
            SandboxAttemptCoverage,
            SandboxEvidenceGap,
            TechnicalCheckExecution,
            TechnicalCheckExecutionEvent,
            SandboxEnvironmentEvent,
            SandboxAnswerSubmission,
            SandboxAnswerReviewEvent,
        ]
        try_mark_attempt_check_running(attempt=self.attempt)
        ledger.begin_check(self.attempt, self.attempt._ledger_check_id)
        ledger.request_environment(self.attempt, "reset", self.user, "trainee")
        with ledger.writer():
            self.attempt.technical_passed_at = timezone.now()
            self.attempt.save(update_fields=["technical_passed_at"])
        sub, _ = ledger.submit_answer(self.attempt, "a", "r")
        with ledger.writer():
            self.attempt.client_answer = "a"
            self.attempt.trainee_report = "r"
            self.attempt.save(update_fields=["client_answer", "trainee_report"])
        staff = User.objects.create_user("guard-mentor", is_staff=True)
        ledger.review_answer(self.attempt, staff, "approved", "", sub.pk)
        ledger.gap(self.attempt.pk, "test_gap")
        for model in models:
            with self.assertRaises(DatabaseError), transaction.atomic():
                with connection.cursor() as cursor:
                    cursor.execute(
                        f"UPDATE {model._meta.db_table} SET recorded_at=recorded_at"
                    )
            with self.assertRaises(DatabaseError), transaction.atomic():
                with connection.cursor() as cursor:
                    cursor.execute(f"DELETE FROM {model._meta.db_table}")
        with connection.cursor() as cursor:
            cursor.execute(
                "UPDATE sandbox_taskattempt SET restart_count=10 WHERE id=%s",
                [self.attempt.pk],
            )
        self.assertTrue(
            SandboxEvidenceGap.objects.filter(
                attempt_id=self.attempt.pk,
                source="database",
                reason="unsupported_update",
            ).exists()
        )

    def test_watchdog_fences_late_physical_success(self):
        try_mark_attempt_check_running(attempt=self.attempt)
        run_id = self.attempt._ledger_check_id
        started, release = (Event(), Event())

        def checker(**kwargs):
            started.set()
            release.wait(timeout=10)
            return (0, "passed")

        def worker():
            close_old_connections()
            try:
                try:
                    return run_attempt_check(
                        attempt=TaskAttempt.objects.get(pk=self.attempt.pk),
                        user_id=self.user.pk,
                        mark_as_running=False,
                        run_id=run_id,
                    )
                except Exception:
                    return "closed"
            finally:
                connection.close()

        with patch("sandbox.services.checks.check_task_container", side_effect=checker):
            with ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(worker)
                self.assertTrue(started.wait(timeout=10))
                ledger.interrupt(self.attempt, "watchdog")
                release.set()
                self.assertEqual(future.result(timeout=20), "closed")
        self.attempt.refresh_from_db()
        self.assertIsNone(self.attempt.technical_passed_at)
        self.assertFalse(CheckRun.objects.exists())

    def test_duplicate_environment_delivery_one_success_and_counter(self):
        from unittest.mock import MagicMock
        from sandbox.services.environments import (
            try_mark_environment_restarting,
            run_environment_restart,
        )

        op = uuid4()
        try_mark_environment_restarting(
            self.attempt, actor=self.user, origin="trainee", operation_id=op
        )
        container = MagicMock()
        container.name = "test"
        container.id = "test-id"
        with patch(
            "sandbox.services.environments.create_task_container",
            return_value=container,
        ) as docker, patch(
            "sandbox.services.environments.create_terminal_container",
            return_value=container,
        ), patch(
            "sandbox.services.environments.wait_for_terminal_ready"
        ), patch(
            "sandbox.services.environments.get_free_port", return_value=25000
        ):
            self.parallel(
                [
                    lambda: run_environment_restart(
                        TaskAttempt.objects.get(pk=self.attempt.pk), operation_id=op
                    )
                ]
                * 2
            )
        self.attempt.refresh_from_db()
        self.assertEqual(docker.call_count, 1)
        self.assertEqual(self.attempt.restart_count, 1)
        self.assertEqual(
            SandboxEnvironmentEvent.objects.filter(
                operation_id=op, phase="finished", outcome="success"
            ).count(),
            1,
        )
