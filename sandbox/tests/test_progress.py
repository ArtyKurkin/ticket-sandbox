import json
from dataclasses import asdict
from datetime import timedelta
from io import StringIO
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.management import call_command
from django.db import connection
from django.test import Client
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from sandbox.models import CheckRun, Task, TaskAttempt, TraineeProfile
from sandbox.services.attempt_display import enrich_attempts_display_state
from sandbox.services.attempts import task_was_technically_completed
from sandbox.services.checks import run_attempt_check, start_attempt_check_in_background
from sandbox.services.progress import (
    build_sandbox_queue_progress,
    build_sandbox_queue_progress_map,
)
from sandbox.services.technical_evidence import get_technical_evidence
from sandbox.services.trainee_dashboard import build_trainee_dashboard_context
from traineediary.models import (
    EntryType,
    StageGroup,
    StageScheme,
    StageScope,
    TraineeJourney,
    TraineeStage,
)
from traineediary.services.assessment import build_readiness_summary
from traineediary.services.sandbox_progress import (
    build_sandbox_queue_progress as diary_progress,
)

from .base import SandboxTestCase


class SandboxProgressTests(SandboxTestCase):
    @classmethod
    def setUpTestData(cls):
        from sandbox.models import Queue

        cls.queue, _ = Queue.objects.update_or_create(
            slug="l1",
            defaults={
                "name": "Progress L1",
                "required_level": "l1",
                "is_active": True,
            },
        )
        Task.objects.filter(queue=cls.queue).delete()
        cls.tasks = [
            Task.objects.create(
                queue=cls.queue,
                title=f"Task {i}",
                slug=f"progress-{i}",
                order=i,
                requires_manual_review=True,
            )
            for i in (1, 2)
        ]
        cls.user = User.objects.create_user("progress-trainee")
        cls.user.trainee_profile.level = TraineeProfile.Level.L1
        cls.user.trainee_profile.save()
        cls.staff = User.objects.create_user("progress-staff", is_staff=True)
        cls.other = User.objects.create_user("progress-other")

    def attempt(self, task=None, technical=True, **kwargs):
        return TaskAttempt.objects.create(
            user=self.user,
            task=task or self.tasks[0],
            technical_passed_at=timezone.now() if technical else None,
            **kwargs,
        )

    def progress(self):
        return build_sandbox_queue_progress(self.user)

    def test_complete_program_with_unsubmitted_answers(self):
        for task in self.tasks:
            self.attempt(task=task, status=TaskAttempt.Status.IN_PROGRESS)
        progress = self.progress()
        self.assertEqual(
            (progress.technical_completed_count, progress.total_count), (2, 2)
        )
        self.assertTrue(progress.is_technically_completed)
        self.assertEqual(progress.unsubmitted_count, 2)
        self.assertEqual(progress.progress_percent, 100)
        self.assertEqual(progress.required_task_ids, tuple(t.pk for t in self.tasks))

    def test_one_missing_task_keeps_program_incomplete(self):
        self.attempt()
        progress = self.progress()
        self.assertEqual(progress.technical_completed_count, 1)
        self.assertEqual(progress.remaining_count, 1)
        self.assertFalse(progress.is_technically_completed)

    def test_successful_check_sh_without_submitted_answer(self):
        attempt = self.attempt(
            technical=False,
            status=TaskAttempt.Status.IN_PROGRESS,
            container_name="test",
        )
        with patch(
            "sandbox.services.checks.check_task_container", return_value=(0, "OK")
        ), patch("sandbox.services.checks.notify_user_completed_all_tasks"):
            run_attempt_check(attempt=attempt, user_id=self.user.pk)
        progress = self.progress()
        self.assertEqual(progress.technical_completed_count, 1)
        self.assertEqual(progress.unsubmitted_count, 1)
        self.assertEqual(progress.on_review_count, 0)
        self.assertEqual(CheckRun.objects.get(attempt=attempt).exit_code, 0)

    def test_answer_review_and_revision_never_reduce_technical_completion(self):
        now = timezone.now()
        revision = self.attempt(
            status=TaskAttempt.Status.FAILED,
            mentor_decision=TaskAttempt.MentorDecision.NEEDS_REVISION,
            mentor_feedback="Shorten response",
            mentor_reviewed_at=now,
        )
        self.attempt(task=self.tasks[1], status=TaskAttempt.Status.ON_REVIEW)
        progress = self.progress()
        self.assertTrue(progress.is_technically_completed)
        self.assertEqual(progress.needs_revision_count, 1)
        self.assertEqual(progress.on_review_count, 1)
        self.assertEqual(progress.unread_feedback_count, 1)
        self.assertEqual(progress.unsubmitted_count, 0)
        revision.mentor_feedback_seen_at = now + timedelta(seconds=1)
        revision.save(update_fields=["mentor_feedback_seen_at"])
        self.assertEqual(self.progress().unread_feedback_count, 0)
        self.assertEqual(self.progress().needs_revision_count, 1)

    def test_approved_answer_is_separate_from_technical_completion(self):
        self.attempt(
            status=TaskAttempt.Status.PASSED,
            mentor_decision=TaskAttempt.MentorDecision.APPROVED,
        )
        progress = self.progress()
        self.assertEqual(progress.approved_answer_count, 1)
        self.assertEqual(progress.technical_completed_count, 1)
        self.assertEqual(progress.unsubmitted_count, 0)

    def test_feedback_missing_review_date_has_unknown_read_state(self):
        attempt = self.attempt(
            status=TaskAttempt.Status.FAILED,
            mentor_decision=TaskAttempt.MentorDecision.NEEDS_REVISION,
            mentor_feedback="Legacy feedback",
            mentor_feedback_seen_at=timezone.now(),
        )
        progress = self.progress()
        self.assertEqual(progress.unread_feedback_count, 0)
        self.assertEqual(progress.feedback_read_state_unknown_count, 1)
        self.assertFalse(attempt.has_unread_mentor_feedback)

    def test_non_manual_task_has_no_unsubmitted_answer(self):
        self.tasks[0].requires_manual_review = False
        self.tasks[0].save(update_fields=["requires_manual_review"])
        self.attempt()
        self.assertEqual(self.progress().unsubmitted_count, 0)

    def test_practice_attempt_success_does_not_count_as_credit(self):
        self.attempt(
            technical=False, is_current=False, status=TaskAttempt.Status.FAILED
        )
        self.attempt(attempt_number=2, status=TaskAttempt.Status.PASSED)
        progress = self.progress()
        self.assertEqual(progress.technical_completed_count, 0)
        self.assertFalse(task_was_technically_completed(self.user, self.tasks[0]))
        next_attempt = self.attempt(task=self.tasks[1], technical=False)
        self.assertFalse(next_attempt.is_available)

    def test_many_practice_attempts_do_not_inflate_or_erase_credit(self):
        self.attempt(is_current=False)
        for i in range(2, 6):
            self.attempt(attempt_number=i, technical=i != 5, is_current=i == 5)
        progress = self.progress()
        self.assertEqual(progress.technical_completed_count, 1)
        self.assertEqual(len(progress.technically_completed_task_ids), 1)
        current = TaskAttempt.objects.get(
            user=self.user, task=self.tasks[0], is_current=True
        )
        enriched = enrich_attempts_display_state([current])[0]
        self.assertTrue(enriched.was_technically_completed)

    def test_legacy_successful_check_run_is_evidence_without_backfill(self):
        attempt = self.attempt(
            technical=False,
            status=TaskAttempt.Status.FAILED,
            mentor_decision=TaskAttempt.MentorDecision.NEEDS_REVISION,
        )
        run = CheckRun.objects.create(
            attempt=attempt, result=CheckRun.Result.PASSED, exit_code=0
        )
        CheckRun.objects.create(
            attempt=attempt, result=CheckRun.Result.FAILED, exit_code=1
        )
        evidence = get_technical_evidence(attempt)
        self.assertEqual(evidence.source, "check_run")
        self.assertEqual(evidence.check_run_id, run.pk)
        self.assertTrue(attempt.technical_passed)
        self.assertTrue(attempt.is_technically_completed)
        self.assertTrue(attempt.technical_locked)
        self.assertTrue(task_was_technically_completed(self.user, self.tasks[0]))
        self.assertEqual(self.progress().technical_completed_count, 1)
        attempt.refresh_from_db()
        self.assertIsNone(attempt.technical_passed_at)
        self.assertEqual(attempt.status, TaskAttempt.Status.FAILED)

    def test_ambiguous_passed_and_check_status_never_grant_credit(self):
        attempt = self.attempt(
            technical=False,
            status=TaskAttempt.Status.PASSED,
            check_status=TaskAttempt.CheckStatus.PASSED,
            mentor_decision=TaskAttempt.MentorDecision.APPROVED,
        )
        progress = self.progress()
        self.assertEqual(progress.technical_completed_count, 0)
        self.assertEqual(progress.approved_answer_count, 1)
        self.assertEqual(
            {d.code for d in progress.diagnostics},
            {
                "passed_without_technical_evidence",
                "check_status_without_technical_evidence",
            },
        )
        self.assertFalse(attempt.technical_passed)
        self.assertFalse(attempt.is_technically_completed)
        self.assertFalse(task_was_technically_completed(self.user, self.tasks[0]))
        enriched = enrich_attempts_display_state([attempt])[0]
        self.assertFalse(enriched.was_technically_completed)
        self.assertNotEqual(enriched.learning_status_label, "Пройдено")

    def test_inconsistent_check_run_is_diagnostic_not_evidence(self):
        attempt = self.attempt(technical=False)
        CheckRun.objects.create(
            attempt=attempt, result=CheckRun.Result.PASSED, exit_code=1
        )
        CheckRun.objects.create(
            attempt=attempt, result=CheckRun.Result.FAILED, exit_code=0
        )
        progress = self.progress()
        self.assertEqual(progress.technical_completed_count, 0)
        self.assertEqual(progress.diagnostics[0].code, "conflicting_check_run")

    def test_timestamp_remains_authoritative_with_conflicting_legacy_run(self):
        attempt = self.attempt()
        CheckRun.objects.create(
            attempt=attempt, result=CheckRun.Result.PASSED, exit_code=1
        )
        self.assertEqual(self.progress().technical_completed_count, 1)
        self.assertEqual(self.progress().diagnostics[0].code, "conflicting_check_run")

    def test_missing_or_inactive_queue_is_not_completed(self):
        self.assertFalse(
            build_sandbox_queue_progress(
                self.user, "not-found"
            ).is_technically_completed
        )
        self.queue.is_active = False
        self.queue.save(update_fields=["is_active"])
        self.assertFalse(self.progress().queue_exists)
        self.assertFalse(self.progress().is_technically_completed)

    def test_empty_program_is_never_completed_zero_over_zero(self):
        Task.objects.filter(queue=self.queue).update(is_active=False)
        progress = self.progress()
        self.assertTrue(progress.queue_exists)
        self.assertEqual(progress.total_count, 0)
        self.assertFalse(progress.is_technically_completed)
        self.assertEqual(progress.progress_percent, 0)

    def test_inactive_task_and_other_queue_do_not_affect_l1(self):
        self.tasks[1].is_active = False
        self.tasks[1].save(update_fields=["is_active"])
        self.attempt()
        other_queue = self.create_queue("progress-other-queue")
        self.create_task(other_queue, "not-mandatory")
        self.assertTrue(self.progress().is_technically_completed)
        self.assertEqual(self.progress().total_count, 1)

    def test_batch_is_unique_per_user_and_isolates_users(self):
        self.attempt()
        progress = build_sandbox_queue_progress_map([self.user, self.user, self.other])
        self.assertEqual(len(progress), 2)
        self.assertEqual(progress[self.user.pk].technical_completed_count, 1)
        self.assertEqual(progress[self.other.pk].technical_completed_count, 0)

    def test_reads_never_create_attempts_change_current_or_backfill_evidence(self):
        attempt = self.attempt(technical=False, is_current=False)
        CheckRun.objects.create(
            attempt=attempt, result=CheckRun.Result.PASSED, exit_code=0
        )
        before = list(TaskAttempt.objects.values())
        runs_before = list(CheckRun.objects.values())
        with CaptureQueriesContext(connection) as queries:
            self.progress()
            diary_progress(self.user)
            build_sandbox_queue_progress_map([self.user, self.other])
        self.assertTrue(
            all(q["sql"].lstrip().upper().startswith("SELECT") for q in queries)
        )
        self.assertEqual(before, list(TaskAttempt.objects.values()))
        self.assertEqual(runs_before, list(CheckRun.objects.values()))

    def test_batch_uses_three_queries_regardless_of_user_task_count(self):
        self.attempt()
        with self.assertNumQueries(3):
            build_sandbox_queue_progress_map([self.user, self.other])

    def test_diagnostic_command_is_readonly_and_includes_inactive_history(self):
        attempt = self.attempt(technical=False, status=TaskAttempt.Status.PASSED)
        self.tasks[0].is_active = False
        self.tasks[0].save(update_fields=["is_active"])
        before = list(TaskAttempt.objects.values())
        output = StringIO()
        call_command(
            "audit_sandbox_progress", user_id=self.user.pk, json=True, stdout=output
        )
        report = json.loads(output.getvalue())
        self.assertEqual(report[0]["attempt_id"], attempt.pk)
        self.assertEqual(report[0]["code"], "passed_without_technical_evidence")
        self.assertEqual(before, list(TaskAttempt.objects.values()))

    def test_catalog_change_is_explicit_in_required_task_ids(self):
        for task in self.tasks:
            self.attempt(task=task)
        before = self.progress()
        new_task = self.create_task(self.queue, "new-required-task", order=3)
        after = self.progress()
        self.assertTrue(before.is_technically_completed)
        self.assertFalse(after.is_technically_completed)
        self.assertNotEqual(before.required_task_ids, after.required_task_ids)
        self.assertIn(new_task.pk, after.required_task_ids)

    def test_diary_uses_identical_progress_and_never_moves_either_scheme(self):
        for task in self.tasks:
            self.attempt(
                task=task,
                status=TaskAttempt.Status.FAILED,
                mentor_decision=TaskAttempt.MentorDecision.NEEDS_REVISION,
            )
        sandbox = TraineeStage.objects.create(
            name="Sandbox",
            slug="progress-sandbox",
            group=StageGroup.SANDBOX_L1,
            order=5,
        )
        repeat = TraineeStage.objects.create(
            name="Before tickets",
            slug="progress-before",
            group=StageGroup.TEACHBASE,
            order=6,
            catalog_scope=StageScope.LEGACY,
        )
        review = TraineeStage.objects.create(
            name="Review", slug="progress-review", group=StageGroup.WITH_REVIEW, order=7
        )
        for scheme in StageScheme.values:
            journey = TraineeJourney.objects.create(
                user=self.user,
                entry_type=EntryType.NEW_HIRE,
                stage_scheme=scheme,
                current_stage=sandbox,
                probation_start_date=timezone.localdate(),
                stage_started_at=timezone.localdate(),
            )
            before = list(journey.stage_history.values())
            self.assertEqual(asdict(self.progress()), asdict(diary_progress(self.user)))
            readiness = build_readiness_summary(journey)
            self.assertTrue(readiness.is_ready)
            self.assertEqual(
                readiness.next_stage, repeat if scheme == StageScheme.LEGACY else review
            )
            journey.refresh_from_db()
            self.assertEqual(journey.current_stage, sandbox)
            self.assertEqual(before, list(journey.stage_history.values()))
            journey.delete()

    def test_dashboard_has_credit_feedback_and_progress_during_practice(self):
        credit = self.attempt(
            is_current=False,
            status=TaskAttempt.Status.FAILED,
            mentor_decision=TaskAttempt.MentorDecision.NEEDS_REVISION,
            mentor_feedback="Fix credit response",
            mentor_reviewed_at=timezone.now(),
        )
        practice = self.attempt(technical=False, attempt_number=2)
        context = build_trainee_dashboard_context(self.user)
        section = list(context["queue_sections"])[0]
        self.assertEqual(section["completed_count"], 1)
        self.assertIn(credit, context["unread_feedback_attempts"])
        shown = next(a for a in section["attempts"] if a.task_id == credit.task_id)
        self.assertEqual(shown, practice)
        self.assertEqual(shown.credit_attempt, credit)
        self.assertEqual(shown.manual_review_label, "Доработать")
        self.client.force_login(self.user)
        response = self.client.get(reverse("sandbox:dashboard"))
        self.assertContains(response, "Доработать зачётный ответ")
        self.assertContains(response, reverse("sandbox:task_detail", args=[credit.pk]))

    def test_returned_credit_answer_editable_after_practice_started(self):
        credit = self.attempt(
            status=TaskAttempt.Status.PASSED,
            mentor_decision=TaskAttempt.MentorDecision.APPROVED,
            client_answer="Original",
            trainee_report="Diagnosis",
        )
        self.client.force_login(self.user)
        response = self.client.post(reverse("sandbox:rerun_task", args=[credit.pk]))
        self.assertEqual(response.status_code, 302)
        practice = TaskAttempt.objects.get(
            user=self.user, task=credit.task, attempt_number=2
        )
        practice_before = asdict(get_technical_evidence(practice)), list(
            TaskAttempt.objects.filter(pk=practice.pk).values()
        )
        self.client.force_login(self.staff)
        self.client.post(
            reverse("sandbox:save_mentor_feedback", args=[credit.pk]),
            {
                "mentor_decision": TaskAttempt.MentorDecision.NEEDS_REVISION,
                "mentor_feedback": "Fix text",
            },
        )
        credit.refresh_from_db()
        passed_at = credit.technical_passed_at
        self.client.force_login(self.user)
        detail = self.client.get(reverse("sandbox:task_detail", args=[credit.pk]))
        self.assertTrue(detail.context["answer_can_be_edited"])
        self.assertContains(detail, "Доработка зачётного ответа")
        with patch("sandbox.views.start_attempt_check_in_background") as check, patch(
            "sandbox.views.cleanup_attempt_environment"
        ) as cleanup:
            response = self.client.post(
                reverse("sandbox:check_task", args=[credit.pk]),
                {
                    "client_answer": "Corrected credit answer",
                    "trainee_report": "Same diagnosis",
                },
            )
        self.assertEqual(response.status_code, 302)
        check.assert_not_called()
        cleanup.assert_not_called()
        credit.refresh_from_db()
        self.assertFalse(credit.is_current)
        self.assertEqual(credit.client_answer, "Corrected credit answer")
        self.assertEqual(credit.technical_passed_at, passed_at)
        self.assertEqual(credit.status, TaskAttempt.Status.ON_REVIEW)
        self.assertEqual(credit.attempts_count, 0)
        self.assertEqual(
            credit.mentor_decision, TaskAttempt.MentorDecision.NOT_REVIEWED
        )
        self.assertEqual(
            practice_before[1],
            list(TaskAttempt.objects.filter(pk=practice.pk).values()),
        )
        self.assertEqual(self.progress().technical_completed_count, 1)
        self.assertEqual(self.progress().on_review_count, 1)
        self.client.force_login(self.staff)
        dashboard = self.client.get(reverse("sandbox:dashboard"))
        self.assertEqual(dashboard.context["pending_review_count"], 1)

    def test_legacy_check_run_revision_does_not_repeat_technical_check(self):
        credit = self.attempt(
            technical=False,
            status=TaskAttempt.Status.FAILED,
            mentor_decision=TaskAttempt.MentorDecision.NEEDS_REVISION,
            is_current=False,
        )
        CheckRun.objects.create(
            attempt=credit, result=CheckRun.Result.PASSED, exit_code=0
        )
        self.attempt(technical=False, attempt_number=2)
        self.client.force_login(self.user)
        with patch("sandbox.views.start_attempt_check_in_background") as check, patch(
            "sandbox.views.cleanup_attempt_environment"
        ):
            self.client.post(
                reverse("sandbox:check_task", args=[credit.pk]),
                {
                    "client_answer": "Legacy answer corrected",
                    "trainee_report": "Report",
                },
            )
        check.assert_not_called()
        credit.refresh_from_db()
        self.assertIsNone(credit.technical_passed_at)
        self.assertEqual(credit.status, TaskAttempt.Status.ON_REVIEW)
        self.assertEqual(CheckRun.objects.filter(attempt=credit).count(), 1)

    def test_direct_and_queued_check_block_existing_technical_success(self):
        for historical in (False, True):
            attempt = self.attempt(
                task=self.tasks[int(historical)], technical=not historical
            )
            if historical:
                CheckRun.objects.create(
                    attempt=attempt, result=CheckRun.Result.PASSED, exit_code=0
                )
            before = list(TaskAttempt.objects.filter(pk=attempt.pk).values())
            with patch(
                "sandbox.services.checks.check_task_container"
            ) as checker, patch("sandbox.tasks.run_attempt_check_task.delay") as delay:
                self.assertTrue(
                    run_attempt_check(attempt=attempt, user_id=self.user.pk).is_success
                )
                self.assertIsNone(
                    start_attempt_check_in_background(
                        attempt=attempt, user_id=self.user.pk
                    )
                )
            checker.assert_not_called()
            delay.assert_not_called()
            self.assertEqual(
                before, list(TaskAttempt.objects.filter(pk=attempt.pk).values())
            )

    def test_other_users_cannot_edit_returned_credit_answer_or_run_checks(self):
        credit = self.attempt(
            is_current=False,
            status=TaskAttempt.Status.FAILED,
            mentor_decision=TaskAttempt.MentorDecision.NEEDS_REVISION,
        )
        self.attempt(technical=False, attempt_number=2)
        before = list(TaskAttempt.objects.filter(pk=credit.pk).values())
        self.client.force_login(self.other)
        self.assertEqual(
            self.client.get(
                reverse("sandbox:task_detail", args=[credit.pk])
            ).status_code,
            404,
        )
        self.assertEqual(
            self.client.post(
                reverse("sandbox:check_task", args=[credit.pk]),
                {"client_answer": "Intruder"},
            ).status_code,
            404,
        )
        self.assertEqual(
            before, list(TaskAttempt.objects.filter(pk=credit.pk).values())
        )

    def test_historical_environment_actions_remain_blocked_for_owner(self):
        credit = self.attempt(
            is_current=False,
            status=TaskAttempt.Status.FAILED,
            mentor_decision=TaskAttempt.MentorDecision.NEEDS_REVISION,
        )
        self.attempt(technical=False, attempt_number=2)
        self.client.force_login(self.user)
        with patch("sandbox.views.start_environment_in_background") as start, patch(
            "sandbox.views.start_environment_restart_in_background"
        ) as restart:
            for action in ("start_task", "restart_task", "rerun_task"):
                self.assertEqual(
                    self.client.post(
                        reverse(f"sandbox:{action}", args=[credit.pk])
                    ).status_code,
                    302,
                )
        start.assert_not_called()
        restart.assert_not_called()
        self.assertEqual(
            TaskAttempt.objects.filter(user=self.user, task=credit.task).count(), 2
        )

    def test_csrf_is_required_for_answer_revision(self):
        credit = self.attempt(
            status=TaskAttempt.Status.FAILED,
            mentor_decision=TaskAttempt.MentorDecision.NEEDS_REVISION,
        )
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.user)
        self.assertEqual(
            client.post(
                reverse("sandbox:check_task", args=[credit.pk]),
                {"client_answer": "Text"},
            ).status_code,
            403,
        )

    def test_worker_rechecks_evidence_after_loading_a_stale_read_snapshot(self):
        from sandbox.services.technical_evidence import with_technical_evidence

        attempt = self.attempt(technical=False)
        snapshot = with_technical_evidence(
            TaskAttempt.objects.filter(pk=attempt.pk)
        ).get()
        self.assertFalse(get_technical_evidence(snapshot).is_completed)
        CheckRun.objects.create(
            attempt=attempt, result=CheckRun.Result.PASSED, exit_code=0
        )
        with patch("sandbox.services.checks.check_task_container") as checker:
            result = run_attempt_check(attempt=snapshot, user_id=self.user.pk)
        self.assertTrue(result.is_success)
        checker.assert_not_called()
        attempt.refresh_from_db()
        self.assertEqual(attempt.attempts_count, 0)
        self.assertIsNone(attempt.technical_passed_at)

    def test_new_ai_snapshot_uses_historical_technical_evidence(self):
        from sandbox.services.ai_reviewer import create_ai_review

        attempt = self.attempt(technical=False)
        CheckRun.objects.create(
            attempt=attempt, result=CheckRun.Result.PASSED, exit_code=0
        )
        with patch(
            "sandbox.services.ai_reviewer.load_system_prompt",
            return_value="Test prompt",
        ):
            review = create_ai_review(attempt)
        self.assertTrue(
            review.task_context["_review_metadata"]["technical_check_passed"]
        )
        attempt.refresh_from_db()
        self.assertIsNone(attempt.technical_passed_at)
