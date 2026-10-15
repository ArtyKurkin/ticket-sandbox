from datetime import timedelta
from decimal import Decimal

from django.utils import timezone
from roadmap.services.confirmations import change_training_confirmation
from sandbox.models import CheckRun, Queue, Task, TaskAttempt
from sandbox.services.completions import record_completion_after_success, restore_program_completion, analyze_program_completion
from traineediary.models import CompletionStatus, EntryType, StageGroup, StageHistory, WeeklyMetric
from .base import AchievementTestCase


class EvaluatorTests(AchievementTestCase):
    def test_training_manual_confirmation_only_bronze(self):
        self.assertEqual(self.evaluate("training_program").status, "not_met")
        event, _ = change_training_confirmation(journey_id=self.journey.pk, actor=self.staff, confirmed=True)
        result = self.evaluate("training_program")
        self.assertEqual(result.tier_code, "bronze")
        self.assertEqual(result.evidence["confirmation_id"], event.pk)
        self.assertEqual(result.evidence["source"], "manual")
        change_training_confirmation(journey_id=self.journey.pk, actor=self.staff, confirmed=False)
        self.assertEqual(self.evaluate("training_program").status, "not_met")

    def test_quality_numeric_boundaries(self):
        metric = self.metric()
        for value, expected in [(79, None), (80, "bronze"), (89, "bronze"), (90, "silver"), (95, "silver"), (96, "gold"), (100, "gold")]:
            with self.subTest(value=value):
                WeeklyMetric.objects.filter(pk=metric.pk).update(quality_percent=value)
                self.assertEqual(self.evaluate("review_quality").tier_code, expected)

    def test_speed_numeric_boundaries_without_quality(self):
        self.move(StageGroup.NO_REVIEW, self.start)
        metric = self.metric(quality=None)
        for value, expected in [("4.9", None), ("5", "bronze"), ("6.9", "bronze"), ("7", "silver"), ("8.9", "silver"), ("9", "gold"), ("10", "gold"), ("10.1", "platinum")]:
            with self.subTest(value=value):
                WeeklyMetric.objects.filter(pk=metric.pk).update(speed_hours=Decimal(value))
                self.assertEqual(self.evaluate("independent_speed").tier_code, expected)

    def test_zero_is_real_value_not_missing(self):
        self.metric(quality=0)
        self.assertEqual(self.evaluate("review_quality").status, "not_met")

    def test_quality_on_no_review_not_eligible(self):
        self.move(StageGroup.NO_REVIEW, self.start)
        self.metric(quality=100)
        self.assertEqual(self.evaluate("review_quality").status, "not_met")

    def test_speed_on_review_not_eligible(self):
        self.metric()
        self.assertEqual(self.evaluate("independent_speed").status, "not_met")

    def test_best_week_and_old_visit_remain_valid_after_return(self):
        metric = self.metric(quality=96)
        self.metric(quality=80, start=self.start + timedelta(days=7), number=2)
        self.move(StageGroup.OPTIONAL_REVIEW, self.start + timedelta(days=14))
        self.move(StageGroup.WITH_REVIEW, self.start + timedelta(days=21))
        self.metric(quality=79, start=self.start + timedelta(days=21), number=3)
        self.assertEqual(self.evaluate("review_quality").evidence["metric_id"], metric.pk)
        self.assertEqual(self.evaluate("review_quality").tier_code, "gold")

    def test_crossing_visit_is_unknown_even_with_same_group_after_return(self):
        self.metric(start=self.start + timedelta(days=3))
        self.move(StageGroup.OPTIONAL_REVIEW, self.start + timedelta(days=5))
        self.move(StageGroup.WITH_REVIEW, self.start + timedelta(days=6))
        self.assertEqual(self.evaluate("review_quality").status, "unknown")

    def test_missing_date_and_future_or_unfinished_period_unknown(self):
        metric = self.metric(start=self.today - timedelta(days=6))
        self.assertEqual(self.evaluate("review_quality").status, "unknown")
        WeeklyMetric.objects.filter(pk=metric.pk).update(week_start_date=None)
        self.assertEqual(self.evaluate("review_quality").status, "unknown")

    def test_history_overlap_gap_and_card_mismatch_unknown(self):
        self.metric()
        self.move(StageGroup.OPTIONAL_REVIEW, self.start + timedelta(days=14))
        first = self.journey.stage_history.order_by("started_at", "pk").first()
        for bad_date in (self.start + timedelta(days=13), self.start + timedelta(days=15)):
            StageHistory.objects.filter(pk=first.pk).update(ended_at=bad_date)
            self.assertEqual(self.evaluate("review_quality").status, "unknown")
        StageHistory.objects.filter(pk=first.pk).update(ended_at=self.start + timedelta(days=14))
        self.journey.stage_started_at += timedelta(days=1)
        self.journey.save(update_fields=["stage_started_at"])
        self.assertEqual(self.evaluate("review_quality").status, "unknown")

    def test_no_history_or_missing_value_unknown(self):
        self.metric(quality=None)
        self.assertEqual(self.evaluate("review_quality").status, "unknown")
        self.journey.stage_history.all().delete()
        self.assertEqual(self.evaluate("review_quality").status, "unknown")

    def test_fixed_quality_is_not_week_evidence(self):
        self.journey.fixed_quality_percent = 100
        self.journey.save(update_fields=["fixed_quality_percent"])
        self.assertEqual(self.evaluate("review_quality").status, "not_met")

    def test_normal_independent_transition_only(self):
        self.move(StageGroup.OPTIONAL_REVIEW, self.start + timedelta(days=7))
        self.move(StageGroup.NO_REVIEW, self.start + timedelta(days=14))
        self.assertEqual(self.evaluate("independent_engineer").tier_code, "silver")

    def test_skipped_optional_stage_no_independent_award(self):
        self.move(StageGroup.NO_REVIEW)
        self.assertEqual(self.evaluate("independent_engineer").status, "not_met")

    def test_unconfirmed_independent_transition_unknown(self):
        self.move(StageGroup.OPTIONAL_REVIEW, self.start + timedelta(days=7))
        self.move(StageGroup.NO_REVIEW, self.start + timedelta(days=14), actor=False)
        self.assertEqual(self.evaluate("independent_engineer").status, "unknown")

    def test_probation_boundaries_inclusive_day_one(self):
        for day, tier in [(1, "platinum"), (30, "platinum"), (31, "gold"), (45, "gold"), (46, "silver"), (60, "silver"), (61, "bronze")]:
            with self.subTest(day=day):
                # Use a savepoint to isolate each real completion and its source record.
                from django.db import transaction
                with transaction.atomic():
                    self.journey.complete_probation(status=CompletionStatus.SUCCESS,
                        completed_at=self.start + timedelta(days=day-1), completed_by=self.staff)
                    result = self.evaluate("probation_new_hire")
                    self.assertEqual(result.tier_code, tier)
                    self.assertEqual(result.evidence["day_number"], day)
                    transaction.set_rollback(True)
                self.journey.refresh_from_db()

    def test_terminated_does_not_grant(self):
        self.journey.complete_probation(status=CompletionStatus.TERMINATED, completed_by=self.staff, comment="Прекращён")
        self.assertEqual(self.evaluate("probation_new_hire").status, "not_met")

    def test_unconfirmed_probation_unknown(self):
        self.journey.complete_probation(status=CompletionStatus.SUCCESS)
        self.assertEqual(self.evaluate("probation_new_hire").status, "unknown")

    def test_internal_transfer_not_required_does_not_earn_training_sandbox_or_probation(self):
        self.journey.entry_type = EntryType.INTERNAL_TRANSFER
        self.journey.save(update_fields=["entry_type"])
        self.metric()
        for code in ("training_program", "sandbox_program", "sandbox_first_success", "sandbox_five_successes", "probation_new_hire"):
            self.assertEqual(self.evaluate(code).status, "not_applicable")
        self.assertEqual(self.evaluate("review_quality").tier_code, "gold")

    def test_pending_definitions_remain_unknown_even_at_100_percent(self):
        self.metric(quality=100)
        for code in ("clean_week", "review_quality_streak", "sandbox_first_five_clean_answers"):
            self.assertEqual(self.evaluate(code).status, "unknown")

    def sandbox_tasks(self, count=5):
        queue, _ = Queue.objects.update_or_create(slug="l1", defaults={"name": "L1", "is_active": True})
        Task.objects.filter(queue=queue).delete()
        return [Task.objects.create(queue=queue, slug=f"award-task-{i}", title=str(i), order=i) for i in range(count)]

    def test_credit_milestones_ignore_practice_and_workflow_passed(self):
        tasks = self.sandbox_tasks()
        for task in tasks:
            TaskAttempt.objects.create(user=self.user, task=task, status="passed", mentor_decision="approved", is_current=False)
            TaskAttempt.objects.create(user=self.user, task=task, attempt_number=2, technical_passed_at=timezone.now())
        self.assertEqual(self.evaluate("sandbox_first_success").status, "not_met")
        credits = TaskAttempt.objects.filter(user=self.user, attempt_number=1)
        credits.update(technical_passed_at=timezone.now())
        self.assertEqual(self.evaluate("sandbox_five_successes").tier_code, "silver")
        self.assertEqual(self.evaluate("sandbox_first_success").tier_code, "bronze")
        self.assertEqual(self.evaluate("sandbox_program").status, "not_met")

    def test_check_run_evidence_and_frozen_completion_survive_deleted_details(self):
        tasks = self.sandbox_tasks()
        for task in tasks:
            attempt = TaskAttempt.objects.create(user=self.user, task=task, restart_count=0, attempts_count=1, mentor_decision="approved")
            CheckRun.objects.create(attempt=attempt, result="passed", exit_code=0)
        candidate = analyze_program_completion(self.user.pk)
        completion, _ = restore_program_completion(user_id=self.user.pk, expected_fingerprint=candidate.fingerprint)
        self.assertEqual(self.evaluate("sandbox_program").tier_code, "bronze")
        self.assertEqual(self.evaluate("sandbox_five_successes").evidence["distinct_task_count"], 5)
        for task in tasks:
            task.delete()
        self.assertEqual(self.evaluate("sandbox_program").evidence["completion_id"], completion.pk)
        self.assertEqual(self.evaluate("sandbox_five_successes").tier_code, "silver")

    def test_duplicate_tasks_and_contradictory_check_do_not_count(self):
        task = self.sandbox_tasks(1)[0]
        attempt = TaskAttempt.objects.create(user=self.user, task=task)
        CheckRun.objects.create(attempt=attempt, result="passed", exit_code=1)
        self.assertEqual(self.evaluate("sandbox_first_success").status, "not_met")
        for _ in range(5):
            CheckRun.objects.create(attempt=attempt, result="passed", exit_code=0)
        self.assertEqual(self.evaluate("sandbox_five_successes").status, "not_met")
