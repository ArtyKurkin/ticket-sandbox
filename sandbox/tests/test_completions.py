import json
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import timedelta
from io import StringIO
from threading import Barrier
from unittest.mock import patch

from django.contrib.admin.sites import AdminSite
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import IntegrityError, close_old_connections, connection, transaction
from django.db.models.deletion import ProtectedError
from django.test import RequestFactory, TransactionTestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from sandbox.admin import SandboxProgramCompletionAdmin
from sandbox.models import (
    CheckRun,
    Queue,
    SandboxProgramCompletion,
    Task,
    TaskAttempt,
    TraineeProfile,
)
from sandbox.services.checks import run_attempt_check
from sandbox.services.completions import (
    analyze_program_completion,
    record_completion_after_success,
    restore_program_completion,
)
from sandbox.services.progress import build_sandbox_queue_progress
from traineediary.models import (
    EntryType,
    StageGroup,
    StageScheme,
    TraineeJourney,
    TraineeStage,
)
from traineediary.services.assessment import build_readiness_summary
from traineediary.services.sandbox_progress import (
    build_sandbox_queue_progress as diary_progress,
)
from .base import SandboxTestCase


class CompletionTests(SandboxTestCase):
    @classmethod
    def setUpTestData(cls):
        cls.queue, _ = Queue.objects.update_or_create(
            slug="l1",
            defaults={"name": "Snapshot L1", "is_active": True, "required_level": "l1"},
        )
        Task.objects.filter(queue=cls.queue).delete()
        cls.tasks = [
            Task.objects.create(
                queue=cls.queue,
                slug=f"snapshot-{i}",
                title=f"Task {i}",
                order=i,
                requires_manual_review=True,
            )
            for i in (1, 2)
        ]
        cls.user = User.objects.create_user("snapshot-user")
        cls.user.trainee_profile.level = TraineeProfile.Level.L1
        cls.user.trainee_profile.save()
        cls.staff = User.objects.create_superuser("snapshot-staff", password="test")
        cls.other = User.objects.create_user("snapshot-other")

    def success(self, task=None, **kwargs):
        attempt = TaskAttempt.objects.create(
            user=self.user,
            task=task or self.tasks[0],
            technical_passed_at=timezone.now(),
            **kwargs,
        )
        run = CheckRun.objects.create(
            attempt=attempt, result=CheckRun.Result.PASSED, exit_code=0
        )
        return attempt, run

    def complete(self):
        self.success()
        attempt, run = self.success(self.tasks[1])
        record, created = record_completion_after_success(
            attempt_id=attempt.pk, check_run_id=run.pk
        )
        self.assertTrue(created)
        return record

    def progress(self):
        return build_sandbox_queue_progress(self.user)

    def test_successful_check_persists_completion_only_on_last_task(self):
        first = TaskAttempt.objects.create(
            user=self.user, task=self.tasks[0], container_name="first"
        )
        last = TaskAttempt.objects.create(
            user=self.user, task=self.tasks[1], container_name="last"
        )
        with patch(
            "sandbox.services.checks.check_task_container", return_value=(0, "OK")
        ):
            run_attempt_check(attempt=first, user_id=self.user.pk)
            self.assertFalse(SandboxProgramCompletion.objects.exists())
            run_attempt_check(attempt=last, user_id=self.user.pk)
        record = SandboxProgramCompletion.objects.get(user=self.user)
        self.assertEqual(record.source, SandboxProgramCompletion.Source.TECHNICAL_CHECK)
        self.assertEqual(
            [e["task_id"] for e in record.snapshot["tasks"]],
            [task.pk for task in self.tasks],
        )
        self.assertEqual(
            {e["attempt_id"] for e in record.snapshot["tasks"]}, {first.pk, last.pk}
        )
        self.assertTrue(all(e["check_run_id"] for e in record.snapshot["tasks"]))
        self.assertTrue(self.progress().is_completed)
        self.assertTrue(self.progress().is_technically_completed)
        self.assertEqual(record.completed_at, last.technical_passed_at)

    def test_repeated_check_and_repeated_capture_never_change_snapshot(self):
        record = self.complete()
        before = list(SandboxProgramCompletion.objects.values())
        attempt = TaskAttempt.objects.get(user=self.user, task=self.tasks[1])
        run = attempt.check_runs.get()
        with patch("sandbox.services.checks.check_task_container") as checker:
            run_attempt_check(attempt=attempt, user_id=self.user.pk)
        checker.assert_not_called()
        again, created = record_completion_after_success(
            attempt_id=attempt.pk, check_run_id=run.pk
        )
        self.assertFalse(created)
        self.assertEqual(again.pk, record.pk)
        self.assertEqual(before, list(SandboxProgramCompletion.objects.values()))

    def test_new_tasks_change_live_progress_but_not_recorded_completion(self):
        record = self.complete()
        original = deepcopy(record.snapshot)
        new = Task.objects.create(
            queue=self.queue, slug="new-required", title="New", order=3
        )
        progress = self.progress()
        self.assertTrue(progress.is_completed)
        self.assertFalse(progress.is_technically_completed)
        self.assertFalse(progress.is_ready)
        self.assertEqual(
            (progress.technical_completed_count, progress.total_count), (2, 3)
        )
        self.assertNotIn(new.pk, progress.completion_task_ids)
        self.assertIn(new.pk, progress.required_task_ids)
        record.refresh_from_db()
        self.assertEqual(record.snapshot, original)

    def test_deactivation_deletion_reordering_and_rename_do_not_change_snapshot(self):
        record = self.complete()
        original = list(SandboxProgramCompletion.objects.values())
        Task.objects.filter(pk=self.tasks[0].pk).update(
            is_active=False, slug="renamed", order=9
        )
        self.tasks[1].delete()
        progress = self.progress()
        self.assertEqual(progress.total_count, 0)
        self.assertFalse(progress.is_technically_completed)
        self.assertTrue(progress.is_completed)
        self.assertEqual(
            progress.completion_task_ids,
            tuple(entry["task_id"] for entry in record.snapshot["tasks"]),
        )
        self.assertEqual(original, list(SandboxProgramCompletion.objects.values()))

    def test_missing_or_inactive_queue_keeps_completed_fact(self):
        self.complete()
        self.queue.is_active = False
        self.queue.save(update_fields=["is_active"])
        self.assertFalse(self.progress().queue_exists)
        self.assertTrue(self.progress().is_completed)
        Task.objects.filter(queue=self.queue).delete()
        self.queue.delete()
        self.assertFalse(self.progress().queue_exists)
        self.assertTrue(self.progress().is_completed)

    def test_answer_notifications_can_change_without_touching_completion(self):
        self.complete()
        original = list(SandboxProgramCompletion.objects.values())
        self.assertEqual(self.progress().unsubmitted_count, 2)
        first = TaskAttempt.objects.get(user=self.user, task=self.tasks[0])
        first.status = TaskAttempt.Status.FAILED
        first.mentor_decision = TaskAttempt.MentorDecision.NEEDS_REVISION
        first.mentor_feedback = "Fix wording"
        first.mentor_reviewed_at = timezone.now()
        first.save()
        second = TaskAttempt.objects.get(user=self.user, task=self.tasks[1])
        second.status = TaskAttempt.Status.ON_REVIEW
        second.save(update_fields=["status"])
        progress = self.progress()
        self.assertTrue(progress.is_completed)
        self.assertEqual(
            (
                progress.needs_revision_count,
                progress.on_review_count,
                progress.unread_feedback_count,
            ),
            (1, 1, 1),
        )
        first.mentor_feedback_seen_at = timezone.now() + timedelta(seconds=1)
        first.save(update_fields=["mentor_feedback_seen_at"])
        self.assertEqual(self.progress().unread_feedback_count, 0)
        self.assertEqual(original, list(SandboxProgramCompletion.objects.values()))

    def test_practice_check_does_not_create_or_replace_completion(self):
        first, _ = self.success(is_current=False)
        practice = TaskAttempt.objects.create(
            user=self.user, task=first.task, attempt_number=2, container_name="practice"
        )
        with patch(
            "sandbox.services.checks.check_task_container", return_value=(0, "OK")
        ), patch(
            "sandbox.services.checks.remove_task_container",
            return_value=(True, "Removed"),
        ):
            run_attempt_check(attempt=practice, user_id=self.user.pk)
        self.assertFalse(SandboxProgramCompletion.objects.exists())
        last, run = self.success(self.tasks[1])
        record_completion_after_success(attempt_id=last.pk, check_run_id=run.pk)
        original = list(SandboxProgramCompletion.objects.values())
        TaskAttempt.objects.filter(pk=practice.pk).update(
            status=TaskAttempt.Status.FAILED, technical_passed_at=None
        )
        self.assertTrue(self.progress().is_completed)
        self.assertEqual(original, list(SandboxProgramCompletion.objects.values()))

    def test_live_complete_without_snapshot_does_not_mint_completion_on_reads(self):
        for task in self.tasks:
            self.success(task)
        before = list(TaskAttempt.objects.values())
        with CaptureQueriesContext(connection) as queries:
            progress = self.progress()
            diary_progress(self.user)
            analyze_program_completion(self.user.pk)
        self.assertTrue(progress.is_technically_completed)
        self.assertFalse(progress.is_completed)
        self.assertFalse(SandboxProgramCompletion.objects.exists())
        self.assertEqual(before, list(TaskAttempt.objects.values()))
        self.assertTrue(
            all(q["sql"].lstrip().upper().startswith("SELECT") for q in queries)
        )

    def test_progress_read_is_select_only_with_existing_snapshot(self):
        self.complete()
        before = list(SandboxProgramCompletion.objects.values())
        with CaptureQueriesContext(connection) as queries:
            progress = self.progress()
        self.assertTrue(progress.is_completed)
        self.assertTrue(
            all(q["sql"].lstrip().upper().startswith("SELECT") for q in queries)
        )
        self.assertEqual(before, list(SandboxProgramCompletion.objects.values()))

    def test_model_orm_and_admin_are_immutable(self):
        record = self.complete()
        record.snapshot["tasks"][0]["task_slug"] = "Changed in memory"
        with self.assertRaises(ValidationError):
            record.save()
        with self.assertRaises(ValidationError):
            SandboxProgramCompletion.objects.filter(pk=record.pk).update(
                source="legacy_restore"
            )
        with self.assertRaises(ValidationError):
            SandboxProgramCompletion.objects.bulk_update([record], ["snapshot"])
        with self.assertRaises(ValidationError):
            record.delete()
        with self.assertRaises(ValidationError):
            SandboxProgramCompletion.objects.filter(pk=record.pk).delete()
        admin = SandboxProgramCompletionAdmin(SandboxProgramCompletion, AdminSite())
        request = RequestFactory().get("/")
        request.user = self.staff
        self.assertFalse(admin.has_add_permission(request))
        self.assertFalse(admin.has_change_permission(request, record))
        self.assertFalse(admin.has_delete_permission(request, record))
        self.assertTrue(admin.has_view_permission(request, record))
        request.user = self.other
        self.assertFalse(admin.has_view_permission(request, record))

    def test_explicit_pk_save_cannot_overwrite_and_unique_program_is_db_enforced(self):
        record = self.complete()
        clone = SandboxProgramCompletion(
            user=self.user,
            program_key=record.program_key,
            source=record.source,
            completed_at=record.completed_at,
            snapshot=deepcopy(record.snapshot),
            composition_fingerprint=record.composition_fingerprint,
        )
        with self.assertRaises(IntegrityError), transaction.atomic():
            clone.save()
        clone.pk = record.pk
        with self.assertRaises(IntegrityError), transaction.atomic():
            clone.save()
        self.assertEqual(SandboxProgramCompletion.objects.count(), 1)
        with self.assertRaises(ProtectedError):
            self.user.delete()

    def test_invalid_or_empty_snapshot_cannot_be_saved(self):
        with self.assertRaises(ValidationError):
            SandboxProgramCompletion.objects.create(
                user=self.user,
                source="legacy_restore",
                completed_at=timezone.now(),
                snapshot={"schema_version": 1, "tasks": []},
                composition_fingerprint="x" * 64,
            )

    def test_ambiguous_passed_and_training_results_cannot_be_restored(self):
        for task in self.tasks:
            TaskAttempt.objects.create(
                user=self.user,
                task=task,
                status=TaskAttempt.Status.PASSED,
                is_current=False,
                mentor_decision=TaskAttempt.MentorDecision.APPROVED,
            )
            self.success(task, attempt_number=2)
        candidate = analyze_program_completion(self.user.pk)
        self.assertFalse(candidate.eligible)
        with self.assertRaises(ValidationError):
            restore_program_completion(
                user_id=self.user.pk, expected_fingerprint=candidate.fingerprint
            )
        self.assertFalse(SandboxProgramCompletion.objects.exists())

    def test_legacy_check_runs_are_explicitly_restored_without_backfilling_attempts(
        self,
    ):
        for task in self.tasks:
            attempt = TaskAttempt.objects.create(
                user=self.user, task=task, status=TaskAttempt.Status.FAILED
            )
            CheckRun.objects.create(
                attempt=attempt, result=CheckRun.Result.PASSED, exit_code=0
            )
        before = list(TaskAttempt.objects.values())
        output = StringIO()
        with CaptureQueriesContext(connection) as queries:
            call_command(
                "restore_sandbox_completions",
                user_ids=[self.user.pk],
                json=True,
                stdout=output,
            )
        self.assertTrue(
            all(q["sql"].lstrip().upper().startswith("SELECT") for q in queries)
        )
        report = json.loads(output.getvalue())[0]
        self.assertTrue(report["eligible"])
        self.assertFalse(SandboxProgramCompletion.objects.exists())
        call_command(
            "restore_sandbox_completions",
            user_ids=[self.user.pk],
            apply=True,
            expected_fingerprint=report["fingerprint"],
            stdout=StringIO(),
        )
        record = SandboxProgramCompletion.objects.get(user=self.user)
        self.assertEqual(record.source, SandboxProgramCompletion.Source.LEGACY_RESTORE)
        self.assertEqual(record.completed_at.isoformat(), report["completed_at"])
        self.assertTrue(
            all(e["evidence_source"] == "check_run" for e in record.snapshot["tasks"])
        )
        self.assertEqual(before, list(TaskAttempt.objects.values()))
        original = list(SandboxProgramCompletion.objects.values())
        call_command(
            "restore_sandbox_completions",
            user_ids=[self.user.pk],
            apply=True,
            expected_fingerprint=report["fingerprint"],
            stdout=StringIO(),
        )
        self.assertEqual(original, list(SandboxProgramCompletion.objects.values()))

    def test_restore_requires_explicit_users_and_unchanged_composition(self):
        for task in self.tasks:
            self.success(task)
        candidate = analyze_program_completion(self.user.pk)
        with self.assertRaises(CommandError):
            call_command("restore_sandbox_completions", apply=True, stdout=StringIO())
        Task.objects.create(queue=self.queue, slug="extra", title="Extra", order=3)
        with self.assertRaisesMessage(CommandError, "Состав программы изменился"):
            call_command(
                "restore_sandbox_completions",
                user_ids=[self.user.pk],
                apply=True,
                expected_fingerprint=candidate.fingerprint,
                stdout=StringIO(),
            )
        self.assertFalse(SandboxProgramCompletion.objects.exists())

    def test_bulk_selected_restore_rolls_back_if_one_user_is_not_proven(self):
        for task in self.tasks:
            self.success(task)
        candidate = analyze_program_completion(self.user.pk)
        with self.assertRaises(CommandError):
            call_command(
                "restore_sandbox_completions",
                user_ids=[self.user.pk, self.other.pk],
                apply=True,
                expected_fingerprint=candidate.fingerprint,
                stdout=StringIO(),
            )
        self.assertFalse(SandboxProgramCompletion.objects.exists())

    def test_inactive_empty_program_cannot_be_recorded_or_restored(self):
        attempt, run = self.success()
        Task.objects.filter(queue=self.queue).update(is_active=False)
        self.assertEqual(
            record_completion_after_success(attempt_id=attempt.pk, check_run_id=run.pk),
            (None, False),
        )
        candidate = analyze_program_completion(self.user.pk)
        self.assertEqual(candidate.reason, "empty_program")
        with self.assertRaises(ValidationError):
            restore_program_completion(
                user_id=self.user.pk, expected_fingerprint=candidate.fingerprint
            )

    def test_other_users_cannot_trigger_snapshot_via_foreign_attempt(self):
        self.success()
        last = TaskAttempt.objects.create(
            user=self.user, task=self.tasks[1], container_name="last"
        )
        self.client.force_login(self.other)
        with patch("sandbox.views.start_attempt_check_in_background") as check:
            response = self.client.post(reverse("sandbox:check_task", args=[last.pk]))
        self.assertEqual(response.status_code, 404)
        check.assert_not_called()
        self.assertFalse(SandboxProgramCompletion.objects.exists())
        self.client.force_login(self.user)
        response = self.client.get(reverse("sandbox:dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(SandboxProgramCompletion.objects.exists())

    def test_success_and_completion_are_one_transaction(self):
        self.success()
        last = TaskAttempt.objects.create(
            user=self.user, task=self.tasks[1], container_name="last"
        )
        with patch(
            "sandbox.services.checks.check_task_container", return_value=(0, "OK")
        ), patch(
            "sandbox.services.checks.record_completion_after_success",
            side_effect=IntegrityError("Snapshot failed"),
        ):
            with self.assertRaises(IntegrityError):
                run_attempt_check(attempt=last, user_id=self.user.pk)
        last.refresh_from_db()
        self.assertIsNone(last.technical_passed_at)
        self.assertFalse(CheckRun.objects.filter(attempt=last).exists())
        self.assertFalse(SandboxProgramCompletion.objects.exists())

    def test_diary_schemes_readiness_and_history_do_not_change(self):
        self.complete()
        stage = TraineeStage.objects.create(
            name="Sandbox", slug="snapshot-stage", order=5, group=StageGroup.SANDBOX_L1
        )
        TraineeStage.objects.create(
            name="Review", slug="snapshot-review", order=7, group=StageGroup.WITH_REVIEW
        )
        for scheme in StageScheme.values:
            journey = TraineeJourney.objects.create(
                user=self.user,
                stage_scheme=scheme,
                entry_type=EntryType.NEW_HIRE,
                probation_start_date=timezone.localdate(),
                current_stage=stage,
                stage_started_at=timezone.localdate(),
            )
            before = list(journey.stage_history.values())
            self.assertTrue(diary_progress(self.user).is_completed)
            self.assertTrue(build_readiness_summary(journey).is_ready)
            self.assertEqual(before, list(journey.stage_history.values()))
            journey.refresh_from_db()
            self.assertEqual(journey.current_stage, stage)
            journey.delete()


class ConcurrentCompletionTests(TransactionTestCase):
    def test_parallel_capture_returns_same_completion(self):
        queue, _ = Queue.objects.update_or_create(
            slug="l1", defaults={"name": "Concurrent", "is_active": True}
        )
        Task.objects.filter(queue=queue).delete()
        task = Task.objects.create(
            queue=queue, slug="concurrent", title="Concurrent", order=1
        )
        user = User.objects.create_user("concurrent-completion")
        attempt = TaskAttempt.objects.create(
            user=user, task=task, technical_passed_at=timezone.now()
        )
        run = CheckRun.objects.create(
            attempt=attempt, result=CheckRun.Result.PASSED, exit_code=0
        )
        barrier = Barrier(2)

        def capture():
            close_old_connections()
            try:
                barrier.wait(timeout=5)
                record, created = record_completion_after_success(
                    attempt_id=attempt.pk, check_run_id=run.pk
                )
                return record.pk, created
            finally:
                connection.close()

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(capture) for _ in range(2)]
            results = [future.result(timeout=10) for future in futures]
        self.assertEqual(results[0][0], results[1][0])
        self.assertEqual(sum(created for _, created in results), 1)
        self.assertEqual(SandboxProgramCompletion.objects.count(), 1)
