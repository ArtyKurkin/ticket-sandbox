import json
from datetime import timedelta
from io import StringIO
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import IntegrityError, connection, transaction
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from achievements.models import AchievementEvent, AchievementSourceEvent, UserAchievement
from achievements.services.events import process_source_event, publish, save_metric_with_event
from achievements.services.grants import revoke
from achievements.services.reconciliation import reconcile
from roadmap.services.confirmations import change_training_confirmation
from sandbox.models import Queue, Task, TaskAttempt
from sandbox.services.checks import run_attempt_check
from traineediary.models import CompletionStatus, StageGroup
from .base import AchievementTestCase


class SourceEventTests(AchievementTestCase):
    def confirm(self):
        with self.captureOnCommitCallbacks(execute=True):
            return change_training_confirmation(journey_id=self.journey.pk, actor=self.staff, confirmed=True)

    def test_confirmation_automatically_grants_once_and_revocation_flags_proof(self):
        self.confirm()
        self.confirm()
        self.assertEqual(AchievementSourceEvent.objects.count(), 1)
        self.assertEqual(AchievementEvent.objects.count(), 1)
        entitlement = UserAchievement.objects.get()
        self.assertEqual(entitlement.active_tier.code, "bronze")
        with self.captureOnCommitCallbacks(execute=True):
            change_training_confirmation(journey_id=self.journey.pk, actor=self.staff, confirmed=False)
        entitlement.refresh_from_db()
        self.assertTrue(entitlement.evidence_disputed)
        self.assertEqual(entitlement.active_tier.code, "bronze")
        self.assertEqual(AchievementEvent.objects.last().action, "evidence_disputed")

    def test_business_write_and_durable_source_roll_back_together(self):
        with patch("achievements.services.events.publish", side_effect=IntegrityError("outbox failure")):
            with self.assertRaises(IntegrityError):
                change_training_confirmation(journey_id=self.journey.pk, actor=self.staff, confirmed=True)
        self.assertFalse(self.journey.roadmap_confirmation_events.exists())
        self.assertFalse(AchievementSourceEvent.objects.exists())

    def test_crashed_wake_leaves_retryable_source_and_no_partial_grant(self):
        with patch("achievements.services.events.grant", side_effect=RuntimeError("worker unavailable")):
            with self.assertLogs("achievements.services.events", level="ERROR"):
                self.confirm()
        event = AchievementSourceEvent.objects.get()
        self.assertEqual(event.status, "error")
        self.assertEqual(event.attempts, 1)
        self.assertFalse(UserAchievement.objects.exists())
        process_source_event(event.pk)
        process_source_event(event.pk)
        self.assertEqual(AchievementEvent.objects.count(), 1)
        event.refresh_from_db()
        self.assertEqual(event.status, "processed")
        self.assertEqual(event.attempts, 2)

    def test_duplicate_source_and_conflicting_payload(self):
        self.confirm()
        event = AchievementSourceEvent.objects.get()
        repeated = publish(provider=event.provider, external_id=event.external_id,
            user_id=event.user_id, context=event.context, payload=event.payload)
        self.assertEqual(repeated.pk, event.pk)
        with self.assertRaises(ValidationError):
            publish(provider=event.provider, external_id=event.external_id,
                user_id=event.user_id, context=event.context, payload={"action": "forged"})
        self.assertEqual(AchievementEvent.objects.count(), 1)

    def test_source_fact_is_immutable_but_processing_fields_can_change(self):
        self.confirm()
        source = AchievementSourceEvent.objects.get()
        source.payload = {"forged": True}
        with self.assertRaises(ValidationError):
            source.save()
        with self.assertRaises(ValidationError):
            AchievementSourceEvent.objects.update(provider="forged")
        with self.assertRaises(ValidationError):
            source.delete()

    def test_sandbox_credit_success_and_completion_automatically_grant(self):
        queue, _ = Queue.objects.update_or_create(slug="l1", defaults={"name": "L1", "is_active": True})
        Task.objects.filter(queue=queue).delete()
        task = Task.objects.create(queue=queue, slug="award-tech", title="Task", requires_manual_review=True)
        attempt = TaskAttempt.objects.create(user=self.user, task=task)
        with patch("sandbox.services.checks.check_task_container", return_value=(0, "OK")), patch(
            "sandbox.services.checks.notify_user_completed_all_tasks"), self.captureOnCommitCallbacks(execute=True):
            run_attempt_check(attempt=attempt, user_id=self.user.pk)
        self.assertEqual(set(UserAchievement.objects.values_list("definition__code", flat=True)),
                         {"sandbox_program", "sandbox_first_success"})
        self.assertEqual(AchievementSourceEvent.objects.count(), 2)
        self.assertEqual(AchievementEvent.objects.count(), 2)

    def test_new_weeks_upgrade_directly_and_worse_week_does_not_dispute(self):
        self.move(StageGroup.NO_REVIEW, self.start)
        metric = self.metric(speed="5")
        with self.captureOnCommitCallbacks(execute=True):
            save_metric_with_event(metric=metric, actor=self.staff)
        # An unchanged row does not create an event; explicitly reconcile a legacy row.
        reconcile(user_id=self.user.pk, definition=self.definition(), apply=True)
        new = self.metric(speed="10.1", start=self.start + timedelta(days=7), number=2)
        new.speed_hours = 11
        with self.captureOnCommitCallbacks(execute=True):
            save_metric_with_event(metric=new, actor=self.staff)
        self.assertEqual(list(AchievementEvent.objects.values_list("action", "to_tier__code")), [("grant", "bronze"), ("upgrade", "platinum")])
        worse = self.metric(speed="2", start=self.start + timedelta(days=14), number=3)
        worse.speed_hours = 1
        with self.captureOnCommitCallbacks(execute=True):
            save_metric_with_event(metric=worse, actor=self.staff)
        entitlement = UserAchievement.objects.get()
        self.assertEqual(entitlement.active_tier.code, "platinum")
        self.assertFalse(entitlement.evidence_disputed)

    def test_correction_flags_evidence_without_downgrade(self):
        metric = self.metric()
        reconcile(user_id=self.user.pk, definition=self.definition("review_quality"), apply=True)
        metric.quality_percent = 80
        with self.captureOnCommitCallbacks(execute=True):
            save_metric_with_event(metric=metric, actor=self.staff)
        entitlement = UserAchievement.objects.get()
        self.assertEqual(entitlement.active_tier.code, "gold")
        self.assertTrue(entitlement.evidence_disputed)
        self.assertEqual(AchievementEvent.objects.last().action, "evidence_disputed")

    def test_superseded_unprocessed_metric_cannot_award_old_high_value(self):
        metric = self.metric(quality=80)
        metric.quality_percent = 96
        with patch("achievements.services.events.wake"):
            with self.captureOnCommitCallbacks(execute=True):
                save_metric_with_event(metric=metric, actor=self.staff)
        old = AchievementSourceEvent.objects.get()
        metric.quality_percent = 80
        with self.captureOnCommitCallbacks(execute=True):
            save_metric_with_event(metric=metric, actor=self.staff)
        process_source_event(old.pk)
        self.assertEqual(UserAchievement.objects.get().active_tier.code, "bronze")
        self.assertEqual(AchievementEvent.objects.count(), 1)

    def test_unfinished_week_queues_until_period_end(self):
        from traineediary.models import WeeklyMetric
        metric = WeeklyMetric(journey=self.journey, week_number=1,
            week_start_date=self.today - timedelta(days=6), quality_percent=96, speed_hours=6)
        with self.captureOnCommitCallbacks(execute=True):
            save_metric_with_event(metric=metric, actor=self.staff)
        event = AchievementSourceEvent.objects.get()
        self.assertEqual(event.status, "pending")
        self.assertFalse(UserAchievement.objects.exists())
        future = timezone.now() + timedelta(days=2)
        with patch("achievements.services.events.timezone.now", return_value=future), patch(
            "django.utils.timezone.localdate", return_value=self.today + timedelta(days=2)):
            call_command("process_achievement_events", stdout=StringIO())
        self.assertEqual(UserAchievement.objects.get().active_tier.code, "gold")

    def test_staff_stage_transition_and_successful_probation_emit_sources(self):
        with self.captureOnCommitCallbacks(execute=True):
            self.move(StageGroup.OPTIONAL_REVIEW, self.start + timedelta(days=7))
            self.move(StageGroup.NO_REVIEW, self.start + timedelta(days=14))
            self.journey.complete_probation(status=CompletionStatus.SUCCESS,
                completed_at=self.start + timedelta(days=29), completed_by=self.staff)
        by_code = {a.definition.code: a.active_tier.code for a in UserAchievement.objects.select_related("definition", "active_tier")}
        self.assertEqual(by_code, {"independent_engineer": "silver", "probation_new_hire": "platinum"})

    def test_unconfirmed_or_terminated_completion_does_not_emit_completion_source(self):
        self.journey.complete_probation(status=CompletionStatus.TERMINATED, completed_by=self.staff, comment="Стоп")
        self.assertFalse(AchievementSourceEvent.objects.filter(provider="probation_completion").exists())

    def test_resync_dry_run_is_select_only_apply_repeat_and_suppression(self):
        self.metric()
        kwargs = dict(user_ids=[self.user.pk], families=["review_quality"])
        output = StringIO()
        with CaptureQueriesContext(connection) as queries:
            call_command("reconcile_achievements", **kwargs, stdout=output)
        self.assertTrue(all(q["sql"].lstrip().upper().startswith("SELECT") for q in queries))
        self.assertEqual(json.loads(output.getvalue())[0]["action"], "grant")
        self.assertFalse(UserAchievement.objects.exists())
        call_command("reconcile_achievements", **kwargs, apply=True, stdout=StringIO())
        call_command("reconcile_achievements", **kwargs, apply=True, stdout=StringIO())
        self.assertEqual(AchievementEvent.objects.count(), 1)
        entitlement = UserAchievement.objects.get()
        revoke(user_id=self.user.pk, definition_id=entitlement.definition_id, actor=self.staff, reason="Ошибка", operation_id="revoke")
        output = StringIO()
        call_command("reconcile_achievements", **kwargs, apply=True, stdout=output)
        self.assertEqual(json.loads(output.getvalue())[0]["action"], "suppressed")
        self.assertIsNone(UserAchievement.objects.get().active_tier_id)

    def test_resync_requires_explicit_known_users_families_and_rule_version(self):
        for kwargs in [dict(user_ids=[999999]), dict(user_ids=[self.user.pk], families=["fake"]), dict(user_ids=[self.user.pk], rule_version=2)]:
            with self.assertRaises(CommandError):
                call_command("reconcile_achievements", **kwargs, stdout=StringIO())

    def test_resync_unknown_pending_and_source_filter(self):
        output = StringIO()
        call_command("reconcile_achievements", user_ids=[self.user.pk], families=["clean_week"], stdout=output)
        self.assertEqual(json.loads(output.getvalue())[0]["status"], "unknown")
        output = StringIO()
        call_command("reconcile_achievements", user_ids=[self.user.pk], source="sandbox_completion", stdout=output)
        self.assertEqual({r["definition"] for r in json.loads(output.getvalue())}, {"sandbox_program", "sandbox_first_success", "sandbox_five_successes"})

    def test_existing_metric_post_writer_records_source_and_awards_correct_group(self):
        from django.urls import reverse
        self.client.force_login(self.staff)
        url = reverse("traineediary:save_weekly_metric", args=[self.journey.pk, 1])
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(url, {"speed_hours": "7", "quality_percent": "90"})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(AchievementSourceEvent.objects.get().provider, "weekly_metric")
        self.assertEqual(UserAchievement.objects.get().definition.code, "review_quality")
        self.assertEqual(UserAchievement.objects.get().active_tier.code, "silver")

    def test_ui_legacy_fallback_does_not_become_award_evidence(self):
        from django.urls import reverse
        self.journey.stage_history.all().delete()
        self.client.force_login(self.staff)
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(reverse("traineediary:save_weekly_metric", args=[self.journey.pk, 1]),
                                        {"speed_hours": "11", "quality_percent": "100"})
        self.assertEqual(response.status_code, 302)
        self.assertFalse(UserAchievement.objects.exists())
        self.assertTrue(all(result["status"] == "unknown" for result in AchievementSourceEvent.objects.get().result))

    def test_reconciliation_detects_maintenance_correction_without_mutating_dry_run(self):
        from traineediary.models import WeeklyMetric
        metric = self.metric()
        definition = self.definition("review_quality")
        reconcile(user_id=self.user.pk, definition=definition, apply=True)
        WeeklyMetric.objects.filter(pk=metric.pk).update(quality_percent=80)
        result = reconcile(user_id=self.user.pk, definition=definition)
        self.assertTrue(result["evidence_disputed"])
        self.assertEqual(AchievementEvent.objects.count(), 1)
        reconcile(user_id=self.user.pk, definition=definition, apply=True)
        reconcile(user_id=self.user.pk, definition=definition, apply=True)
        self.assertEqual(AchievementEvent.objects.count(), 2)
        self.assertEqual(UserAchievement.objects.get().active_tier.code, "gold")
        self.assertTrue(UserAchievement.objects.get().evidence_disputed)
