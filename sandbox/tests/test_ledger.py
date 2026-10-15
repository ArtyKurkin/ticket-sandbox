from datetime import timedelta
from uuid import uuid4
from unittest.mock import patch, MagicMock
from django.core.exceptions import ValidationError, PermissionDenied
from django.db import connection, transaction
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone
from sandbox.models import (
    TaskAttempt,
    CheckRun,
    TraineeProfile,
    SandboxProgramCompletion,
)
from sandbox.ledger_models import *
from sandbox.services import ledger
from sandbox.services.checks import (
    run_attempt_check,
    try_mark_attempt_check_running,
    _run_attempt_check_background,
    start_attempt_check_in_background,
)
from sandbox.services.environments import (
    run_environment_restart,
    run_environment_start,
    try_mark_environment_restarting,
    mark_environment_restart_error,
)
from sandbox.services.ledger_evidence import attempt_evidence, program_evidence
from .base import SandboxTestCase


class LedgerTests(SandboxTestCase):

    def setUp(self):
        if not SandboxLedgerBoundary.objects.filter(pk=1).exists():
            SandboxLedgerBoundary.objects.create(pk=1, enabled_at=timezone.now())
        self.queue = self.create_queue(
            slug="l1", name="L1", order=1, required_level=TraineeProfile.Level.L1
        )
        self.user = self.create_user(
            username="ledger-user", level=TraineeProfile.Level.L1
        )
        self.staff = self.create_user(username="ledger-staff", is_staff=True)
        self.task = self.create_task(
            queue=self.queue, slug="https-ipv4-listener", order=1
        )
        self.task.requires_manual_review = True
        self.task.save()
        self.attempt = TaskAttempt.objects.create(user=self.user, task=self.task)

    def check(self, code=0, attempt=None, **kwargs):
        a = attempt or self.attempt
        with patch(
            "sandbox.services.checks.check_task_container",
            return_value=(code, "output"),
        ), patch("sandbox.services.checks.remove_task_container"), patch(
            "sandbox.services.checks.remove_terminal_container"
        ):
            return run_attempt_check(attempt=a, user_id=a.user_id, **kwargs)

    def test_new_attempt_coverage_and_immutable_frozen_manifest(self):
        initial = attempt_evidence(self.attempt.pk)
        self.assertEqual(initial["coverage"]["status"], "complete")
        manifest = SandboxProgramManifest.objects.get(user_id=self.user.pk)
        before = manifest.snapshot
        self.task.requires_manual_review = False
        self.task.save()
        self.create_task(queue=self.queue, slug="extra", order=2)
        self.assertEqual(
            SandboxProgramManifest.objects.get(pk=manifest.pk).snapshot, before
        )
        self.assertTrue(before["tasks"][0]["requires_review"])
        self.assertEqual(
            program_evidence(self.user.pk)["manifest"]["source"], "from_start"
        )

    def test_first_pass_and_bronze_completion_existing_notification(self):
        from traineediary.models import TraineeJourney, TraineeStage, StageGroup

        stage = TraineeStage.objects.create(
            name="Review", slug="ledger-review", order=90, group=StageGroup.WITH_REVIEW
        )
        TraineeJourney.objects.create(
            user=self.user,
            entry_type="new_hire",
            current_stage=stage,
            probation_start_date=timezone.localdate(),
            stage_started_at=timezone.localdate(),
        )
        self.check()
        a = attempt_evidence(self.attempt.pk)
        self.assertEqual(a["coverage"]["status"], "complete")
        self.assertEqual(a["first_check"]["result"], "passed")
        self.assertEqual(a["successful_resets"], 0)
        self.assertTrue(
            SandboxProgramCompletion.objects.filter(user=self.user).exists()
        )
        from achievements.services.evaluators import evaluate
        from achievements.models import AchievementDefinition

        result = evaluate(
            user_id=self.user.pk,
            definition=AchievementDefinition.objects.get(code="sandbox_program"),
        )
        self.assertEqual(result.tier_code, "silver")

    def test_failed_first_then_success_is_two_real_ordinals(self):
        self.check(1)
        self.check()
        evidence = attempt_evidence(self.attempt.pk)
        self.assertEqual(evidence["first_check"]["result"], "failed")
        self.assertEqual([c["ordinal"] for c in evidence["technical_checks"]], [1, 2])
        self.assertEqual(CheckRun.objects.filter(attempt=self.attempt).count(), 2)

    def test_timeout_and_checker_launch_errors_are_not_invented_student_failures(self):
        for code in [2, 42, 124, 125, 126, 127, 137, 255]:
            self.check(code)
            end = TechnicalCheckExecutionEvent.objects.filter(phase="finished").latest(
                "pk"
            )
            self.assertEqual(end.result, "unknown")
            self.assertIn(end.failure_class, ["timeout", "infrastructure", "unknown"])
        self.assertEqual(
            attempt_evidence(self.attempt.pk)["coverage"]["status"], "unknown"
        )

    def test_docker_exception_and_known_prelaunch(self):
        error = RuntimeError("secret password must not enter ledger")
        error._sandbox_checker_started = False
        with patch("sandbox.services.checks.check_task_container", side_effect=error):
            run_attempt_check(attempt=self.attempt, user_id=self.user.pk)
        e = TechnicalCheckExecutionEvent.objects.get(phase="finished")
        self.assertEqual(e.failure_class, "infrastructure")
        self.assertFalse(e.checker_started)
        self.assertNotIn("password", str(e.__dict__))
        self.check()
        self.assertEqual(
            attempt_evidence(self.attempt.pk)["first_check"]["result"], "passed"
        )

    def test_unclassified_docker_outcome_stays_unknown(self):
        with patch(
            "sandbox.services.checks.check_task_container",
            side_effect=RuntimeError("API"),
        ):
            run_attempt_check(attempt=self.attempt, user_id=self.user.pk)
        self.assertIsNone(
            TechnicalCheckExecutionEvent.objects.get(phase="finished").checker_started
        )
        self.assertIn(
            "check_outcome_unknown",
            attempt_evidence(self.attempt.pk)["coverage"]["reasons"],
        )

    def test_missing_exit_code_does_not_invent_technical_failure(self):
        self.check(None)
        end = TechnicalCheckExecutionEvent.objects.get(phase="finished")
        self.assertEqual(end.result, "unknown")
        self.assertEqual(end.reason, "exit_code_missing")
        self.assertIsNone(end.checker_started)
        self.assertIsNone(attempt_evidence(self.attempt.pk)["first_check"])
        self.assertFalse(CheckRun.objects.exists())
        self.attempt.refresh_from_db()
        self.assertEqual(self.attempt.check_status, TaskAttempt.CheckStatus.ERROR)

    def test_duplicate_failed_celery_delivery_does_not_run_again(self):
        try_mark_attempt_check_running(attempt=self.attempt)
        run_id = self.attempt._ledger_check_id
        with patch(
            "sandbox.services.checks.check_task_container", return_value=(1, "failed")
        ) as docker:
            self.check(1, mark_as_running=False, run_id=run_id)
            run_attempt_check(
                attempt=self.attempt,
                user_id=self.user.pk,
                mark_as_running=False,
                run_id=run_id,
            )
            docker.assert_not_called()
        self.assertEqual(TechnicalCheckExecution.objects.count(), 1)
        self.assertEqual(CheckRun.objects.count(), 1)
        self.assertTrue(
            TechnicalCheckExecutionEvent.objects.filter(phase="duplicate").exists()
        )

    def test_dispatch_registration_before_queue_and_replayed_http_key(self):
        op = str(uuid4())
        with patch("sandbox.tasks.run_attempt_check_task.delay") as delay:
            with self.captureOnCommitCallbacks(execute=True):
                result = start_attempt_check_in_background(
                    attempt=self.attempt, user_id=self.user.pk, operation_id=op
                )
                self.assertEqual(str(TechnicalCheckExecution.objects.get().run_id), op)
                delay.assert_not_called()
            delay.assert_called_once_with(self.attempt.pk, self.user.pk, run_id=result)
        self.check(1, mark_as_running=False, run_id=op)
        self.assertFalse(
            try_mark_attempt_check_running(attempt=self.attempt, operation_id=op)
        )
        self.attempt.refresh_from_db()
        self.assertEqual(self.attempt.attempts_count, 1)

    @patch("sandbox.services.checks.close_old_connections")
    def test_background_failure_after_checker_result_no_extra_credit(
        self, close_connections
    ):
        try_mark_attempt_check_running(attempt=self.attempt)
        run_id = self.attempt._ledger_check_id
        with patch(
            "sandbox.services.checks.check_task_container", return_value=(0, "passed")
        ), patch(
            "sandbox.services.checks.record_completion_after_success",
            side_effect=RuntimeError("commit path"),
        ):
            _run_attempt_check_background(
                attempt_id=self.attempt.pk, user_id=self.user.pk, run_id=run_id
            )
        self.attempt.refresh_from_db()
        self.assertIsNone(self.attempt.technical_passed_at)
        self.assertFalse(CheckRun.objects.exists())
        self.assertEqual(
            TechnicalCheckExecutionEvent.objects.get(phase="finished").result, "unknown"
        )

    def test_watchdog_unknown_and_late_worker_fenced(self):
        try_mark_attempt_check_running(attempt=self.attempt)
        execution = TechnicalCheckExecution.objects.get()
        ledger.begin_check(self.attempt, execution.run_id)
        from sandbox.management.commands.detect_stuck_attempts import Command

        with patch(
            "sandbox.management.commands.detect_stuck_attempts.notify_stuck_attempt_detected"
        ):
            Command().mark_stuck_check_attempts([self.attempt], False, timezone.now())
        self.assertEqual(execution.events.get(phase="finished").reason, "watchdog")
        with patch("sandbox.services.checks.check_task_container") as docker:
            run_attempt_check(
                attempt=self.attempt,
                user_id=self.user.pk,
                mark_as_running=False,
                run_id=execution.run_id,
            )
            docker.assert_not_called()

    def environment(self, kind="reset", origin="trainee", op=None, fail=False):
        a = self.attempt
        if kind == "reset":
            try_mark_environment_restarting(
                a,
                actor=self.user if origin == "trainee" else self.staff,
                origin=origin,
                operation_id=op,
            )
        container = MagicMock()
        container.name = "test-container"
        container.id = "test-id"
        with patch(
            "sandbox.services.environments.create_task_container",
            return_value=container,
        ), patch(
            "sandbox.services.environments.create_terminal_container",
            return_value=container,
        ), patch(
            "sandbox.services.environments.wait_for_terminal_ready",
            side_effect=RuntimeError("infra") if fail else None,
        ), patch(
            "sandbox.services.environments.remove_task_container"
        ), patch(
            "sandbox.services.environments.remove_terminal_container"
        ), patch(
            "sandbox.services.environments.get_free_port", return_value=32123
        ):
            return (
                run_environment_restart if kind == "reset" else run_environment_start
            )(
                a,
                operation_id=getattr(a, "_ledger_environment_id", None),
                actor=self.user if origin == "trainee" else self.staff,
                origin=origin,
            )

    def test_successful_user_reset_matches_counter_and_duplicate(self):
        op = str(uuid4())
        self.environment(op=op)
        self.attempt.refresh_from_db()
        self.assertEqual(self.attempt.restart_count, 1)
        with patch("sandbox.services.environments.create_task_container") as docker:
            run_environment_restart(self.attempt, operation_id=op)
            docker.assert_not_called()
        self.assertEqual(attempt_evidence(self.attempt.pk)["successful_resets"], 1)

    def test_first_environment_start_and_maintenance_reset_not_a_user_reset(self):
        self.environment(kind="start")
        self.environment(origin="maintenance")
        self.attempt.refresh_from_db()
        self.assertEqual(self.attempt.restart_count, 1)
        self.assertEqual(attempt_evidence(self.attempt.pk)["successful_resets"], 0)

    def test_failed_reset_unknown_does_not_increase_counter(self):
        with self.assertRaises(RuntimeError):
            self.environment(fail=True)
        mark_environment_restart_error(self.attempt, RuntimeError("infra"))
        self.attempt.refresh_from_db()
        self.assertEqual(self.attempt.restart_count, 0)
        self.assertIsNone(attempt_evidence(self.attempt.pk)["successful_resets"])

    def test_practice_separate_and_owner_check(self):
        practice = TaskAttempt.objects.create(
            user=self.user, task=self.task, attempt_number=2, is_current=False
        )
        self.check(1, attempt=practice)
        self.assertFalse(attempt_evidence(practice.pk)["credit"])
        with self.assertRaises(PermissionDenied):
            run_attempt_check(attempt=practice, user_id=self.staff.pk)

    def test_legacy_midway_and_unsupported_writes_unknown(self):
        self.attempt.attempts_count = 2
        self.attempt.save(update_fields=["attempts_count"])
        self.assertTrue(
            SandboxEvidenceGap.objects.filter(attempt_id=self.attempt.pk).exists()
        )
        self.assertEqual(
            attempt_evidence(self.attempt.pk)["coverage"]["status"], "unknown"
        )
        legacy = TaskAttempt.objects.bulk_create(
            [TaskAttempt(user=self.staff, task=self.task)]
        )[0]
        self.assertIn(
            "history_not_recorded_from_creation",
            attempt_evidence(legacy.pk)["coverage"]["reasons"],
        )
        self.assertTrue(attempt_evidence(legacy.pk)["credit"])
        self.check(1, attempt=legacy)
        self.assertEqual(
            SandboxAttemptCoverage.objects.get(attempt_id=legacy.pk).origin,
            "legacy_observed",
        )

    def submit(self, text=" original ", report=" report ", op=None):
        self.client.force_login(self.user)
        return self.client.post(
            reverse("sandbox:check_task", args=[self.attempt.pk]),
            {
                "client_answer": text,
                "trainee_report": report,
                "operation_id": str(op or uuid4()),
            },
        )

    def review(
        self, decision="needs_revision", comment="Fix", submission=None, op=None
    ):
        self.client.force_login(self.staff)
        submission = (
            submission or SandboxAnswerSubmission.objects.order_by("-pk").first()
        )
        return self.client.post(
            reverse("sandbox:save_mentor_feedback", args=[self.attempt.pk]),
            {
                "mentor_decision": decision,
                "mentor_feedback": comment,
                "submission_id": submission.pk if submission else "",
                "operation_id": str(op or uuid4()),
            },
        )

    def test_submissions_two_returns_immutable_texts_and_idempotency(self):
        self.check()
        op = uuid4()
        self.submit(op=op)
        first = SandboxAnswerSubmission.objects.get()
        self.assertEqual(first.client_answer, " original ")
        self.review()
        self.submit(op=op)
        self.assertEqual(SandboxAnswerSubmission.objects.count(), 1)
        self.submit(" revised ", " report2 ")
        self.review()
        self.assertEqual(SandboxAnswerSubmission.objects.count(), 2)
        self.assertEqual(attempt_evidence(self.attempt.pk)["valid_returns"], 2)
        self.assertEqual(
            SandboxAnswerSubmission.objects.get(pk=first.pk).client_answer, " original "
        )

    def test_review_repeat_comment_correction_and_first_approved(self):
        self.check()
        self.submit()
        self.review()
        self.review()
        self.assertEqual(SandboxAnswerReviewEvent.objects.count(), 1)
        self.review(comment="Edited")
        self.assertEqual(attempt_evidence(self.attempt.pk)["valid_returns"], 1)
        self.review("approved", "Erroneous decision corrected")
        a = attempt_evidence(self.attempt.pk)
        self.assertEqual(a["valid_returns"], 0)
        self.assertTrue(a["first_answer_approved"])
        self.assertEqual(SandboxAnswerReviewEvent.objects.last().kind, "correction")

    def test_invalid_draft_no_submission_and_ai_compatible(self):
        self.check()
        self.submit(text=" ")
        self.assertFalse(SandboxAnswerSubmission.objects.exists())
        self.task.ai_review_context = {"test": "context"}
        self.task.save()
        with patch("sandbox.views.start_ai_review_in_background"):
            self.submit()
        self.assertEqual(SandboxAnswerSubmission.objects.count(), 1)
        self.assertEqual(self.attempt.ai_reviews.count(), 1)

    def test_wrong_submission_nonstaff_and_foreign_owner(self):
        self.check()
        self.submit()
        first = SandboxAnswerSubmission.objects.get()
        self.review()
        self.submit("new", "report")
        count = SandboxAnswerReviewEvent.objects.count()
        self.review("approved", submission=first)
        self.assertEqual(SandboxAnswerReviewEvent.objects.count(), count)
        self.attempt.refresh_from_db()
        self.assertEqual(self.attempt.status, "on_review")
        with self.assertRaises(PermissionDenied):
            ledger.review_answer(self.attempt, self.user, "approved", "", first.pk)
        self.client.force_login(self.staff)
        self.assertEqual(
            self.client.post(
                reverse("sandbox:check_task", args=[self.attempt.pk]), {}
            ).status_code,
            404,
        )

    def test_no_submission_review_not_fabricated_and_deleted_details_unknown(self):
        self.review("approved")
        self.assertFalse(SandboxAnswerSubmission.objects.exists())
        self.assertIn(
            "ledger_gap", attempt_evidence(self.attempt.pk)["coverage"]["reasons"]
        )
        self.check()
        self.attempt.delete()
        self.assertTrue(SandboxProgramCompletion.objects.exists())
        self.assertIn(
            "attempt_details_missing",
            attempt_evidence(
                self.attempt.pk or SandboxAttemptCoverage.objects.first().attempt_id
            )["coverage"]["reasons"],
        )

    def test_read_only_evidence_no_raw_answers_or_awards(self):
        self.check()
        self.submit()
        with CaptureQueriesContext(connection) as queries:
            result = program_evidence(self.user.pk)
        self.assertTrue(
            all((q["sql"].lstrip().upper().startswith("SELECT") for q in queries))
        )
        self.assertNotIn(" original ", str(result))
        self.assertNotIn(" report ", str(result))

    def test_append_only_models_and_explicit_pk(self):
        self.check()
        execution = TechnicalCheckExecution.objects.get()
        with self.assertRaises(ValidationError):
            execution.save()
        with self.assertRaises(ValidationError):
            TechnicalCheckExecution.objects.all().delete()
        with self.assertRaises(ValidationError):
            TechnicalCheckExecution.objects.update(source="fake")
        from django.db import IntegrityError

        with self.assertRaises(IntegrityError), transaction.atomic():
            copy = TechnicalCheckExecution.objects.get(pk=execution.pk)
            copy._state.adding = True
            copy.save()

    def test_replayed_superseded_review_does_not_change_current_decision(self):
        self.check()
        self.submit()
        op = uuid4()
        self.review(op=op)
        self.review("approved", "Corrected")
        self.review(op=op)
        self.attempt.refresh_from_db()
        self.assertEqual(self.attempt.mentor_decision, "approved")
        self.assertEqual(SandboxAnswerReviewEvent.objects.count(), 2)

    def test_alternative_checker_version_is_frozen(self):
        alternative = self.create_task(
            queue=self.queue, slug="wordpress-500-after-move", order=2
        )
        kind, version = ledger.checker_identity(alternative)
        self.assertEqual(kind, "server_php")
        self.assertEqual(len(version), 64)

    def test_manifest_completion_survives_catalog_delete_details_become_unknown(self):
        self.check()
        completion = SandboxProgramCompletion.objects.get()
        snapshot = completion.snapshot
        self.task.delete()
        self.assertEqual(SandboxProgramCompletion.objects.get().snapshot, snapshot)
        self.assertIsNone(program_evidence(self.user.pk)["successful_resets"])
        self.assertIn(
            "credit_attempt_missing",
            program_evidence(self.user.pk)["coverage"]["reasons"],
        )

    def test_valid_technical_first_answer_full_program_and_five_order(self):
        self.check()
        self.submit()
        self.review("approved", "Accepted")
        evidence = program_evidence(self.user.pk)
        self.assertEqual(evidence["coverage"]["status"], "complete")
        self.assertTrue(evidence["all_required_answers_approved"])
        self.assertEqual(evidence["first_five_answers"][0]["ordinal"], 1)

    def test_old_account_without_remaining_rows_does_not_prove_new_program(self):
        from django.contrib.auth.models import User

        old = self.create_user(
            username="old-account-empty", level=TraineeProfile.Level.L1
        )
        User.objects.filter(pk=old.pk).update(
            date_joined=SandboxLedgerBoundary.objects.get(pk=1).enabled_at
            - timedelta(days=10)
        )
        new = TaskAttempt.objects.create(user=old, task=self.task)
        self.assertEqual(attempt_evidence(new.pk)["coverage"]["status"], "complete")
        self.assertEqual(
            program_evidence(old.pk)["manifest"]["source"], "existing_account"
        )
        self.assertIsNone(program_evidence(old.pk)["successful_resets"])

    def test_unknown_check_does_not_invent_first_or_discard_known_reset_history(self):
        self.check(124)
        evidence = attempt_evidence(self.attempt.pk)
        self.assertEqual(evidence["coverage"]["sources"]["checks"]["status"], "unknown")
        self.assertEqual(
            evidence["coverage"]["sources"]["resets"]["status"], "complete"
        )
        self.assertIsNone(evidence["first_check"])
        self.assertEqual(evidence["successful_resets"], 0)

    def test_duplicate_success_delivery_records_marker_not_new_credit(self):
        try_mark_attempt_check_running(attempt=self.attempt)
        run_id = self.attempt._ledger_check_id
        self.check(mark_as_running=False, run_id=run_id)
        self.check(mark_as_running=False, run_id=run_id)
        self.assertEqual(CheckRun.objects.count(), 1)
        self.assertEqual(SandboxProgramCompletion.objects.count(), 1)
        self.assertTrue(
            TechnicalCheckExecutionEvent.objects.filter(phase="duplicate").exists()
        )

    def test_mentor_cannot_approve_changed_unsubmitted_draft_as_old_version(self):
        self.check()
        self.submit()
        self.review()
        self.submit("Changed draft", " ")
        count = SandboxAnswerReviewEvent.objects.count()
        self.review("approved", "Wrong content")
        self.assertEqual(SandboxAnswerReviewEvent.objects.count(), count)
        self.attempt.refresh_from_db()
        self.assertEqual(self.attempt.mentor_decision, "needs_revision")
