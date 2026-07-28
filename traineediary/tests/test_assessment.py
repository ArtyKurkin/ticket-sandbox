from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase

from traineediary.models import (
    EntryType,
    RiskLevel,
    StageGroup,
    TraineeJourney,
    TraineeStage,
    WeeklyMetric,
)
from traineediary.services.assessment import (
    build_trainee_assessment,
)
from traineediary.services.sandbox_progress import (
    SandboxQueueProgress,
)


class TraineeAssessmentTests(TestCase):
    def setUp(self):
        self.sandbox_stage = (
            TraineeStage.objects.create(
                name="Задания в Ticket Sandbox",
                slug="assessment-sandbox",
                order=1,
                min_days=1,
                max_days=3,
                progress_weight_percent=10,
                group=(
                    StageGroup.SANDBOX_CANDIDATE
                ),
                applies_to_new_hire=True,
                applies_to_internal_transfer=False,
            )
        )

        self.with_review_stage = (
            TraineeStage.objects.create(
                name="С проверками",
                slug="assessment-with-review",
                order=2,
                min_days=15,
                max_days=20,
                progress_weight_percent=35,
                group=StageGroup.WITH_REVIEW,
            )
        )

        self.optional_stage = (
            TraineeStage.objects.create(
                name="Кнопка по желанию",
                slug="assessment-optional",
                order=3,
                min_days=7,
                max_days=14,
                progress_weight_percent=15,
                group=StageGroup.OPTIONAL_REVIEW,
            )
        )

        self.no_review_stage = (
            TraineeStage.objects.create(
                name="Без проверок",
                slug="assessment-no-review",
                order=4,
                min_days=14,
                max_days=30,
                progress_weight_percent=20,
                group=StageGroup.NO_REVIEW,
            )
        )

        self.done_stage = (
            TraineeStage.objects.create(
                name="Выход с ИС",
                slug="assessment-done",
                order=5,
                min_days=1,
                max_days=1,
                progress_weight_percent=20,
                group=StageGroup.DONE,
            )
        )

    def create_journey(
        self,
        *,
        stage,
        probation_days_ago=30,
        stage_days_ago=0,
    ):
        user = User.objects.create_user(
            username=(
                f"assessment-{User.objects.count()}"
            ),
            password="test",
        )

        return TraineeJourney.objects.create(
            user=user,
            entry_type=EntryType.NEW_HIRE,
            probation_start_date=(
                date.today()
                - timedelta(
                    days=probation_days_ago,
                )
            ),
            current_stage=stage,
            stage_started_at=(
                date.today()
                - timedelta(
                    days=stage_days_ago,
                )
            ),
        )

    def create_metric(
        self,
        journey,
        *,
        speed="6.0",
        quality=80,
    ):
        return WeeklyMetric.objects.create(
            journey=journey,
            week_number=1,
            week_start_date=(
                journey.stage_started_at
            ),
            speed_hours=Decimal(speed),
            quality_percent=quality,
        )

    def test_sandbox_stage_is_ready_when_all_l1_tasks_passed(
        self,
    ):
        journey = self.create_journey(
            stage=self.sandbox_stage,
        )

        progress = SandboxQueueProgress(
            queue_exists=True,
            queue_slug="l1",
            queue_name="L1",
            total_count=2,
            passed_count=2,
            remaining_count=0,
            on_review_count=0,
            progress_percent=100,
            is_ready=True,
        )

        assessment = build_trainee_assessment(
            journey,
            sandbox_progress=progress,
        )

        self.assertTrue(
            assessment.readiness.is_ready,
        )
        self.assertEqual(
            assessment.readiness.next_stage,
            self.with_review_stage,
        )

    def test_sandbox_stage_is_almost_ready_when_tasks_wait_for_review(
        self,
    ):
        journey = self.create_journey(
            stage=self.sandbox_stage,
        )

        progress = SandboxQueueProgress(
            queue_exists=True,
            queue_slug="l1",
            queue_name="L1",
            total_count=2,
            passed_count=1,
            remaining_count=1,
            on_review_count=1,
            progress_percent=50,
            is_ready=False,
        )

        assessment = build_trainee_assessment(
            journey,
            sandbox_progress=progress,
        )

        self.assertTrue(
            assessment.readiness.is_almost_ready,
        )
        self.assertEqual(
            assessment.readiness.reasons[0].code,
            "sandbox_tasks_on_review",
        )

    def test_with_review_requires_minimum_days_and_target_quality(
        self,
    ):
        journey = self.create_journey(
            stage=self.with_review_stage,
            stage_days_ago=15,
        )

        self.create_metric(
            journey,
            quality=80,
        )

        assessment = build_trainee_assessment(
            journey,
        )

        self.assertTrue(
            assessment.readiness.is_ready,
        )
        self.assertEqual(
            assessment.readiness.next_stage,
            self.optional_stage,
        )

    def test_with_review_is_not_ready_below_quality_target(
        self,
    ):
        journey = self.create_journey(
            stage=self.with_review_stage,
            stage_days_ago=15,
        )

        self.create_metric(
            journey,
            quality=79,
        )

        assessment = build_trainee_assessment(
            journey,
        )

        reason_codes = {
            reason.code
            for reason
            in assessment.readiness.reasons
        }

        self.assertFalse(
            assessment.readiness.is_ready,
        )
        self.assertIn(
            "quality_below_target",
            reason_codes,
        )

    def test_optional_review_ignores_fixed_low_quality(
        self,
    ):
        journey = self.create_journey(
            stage=self.optional_stage,
            stage_days_ago=7,
        )

        journey.fixed_quality_percent = 65
        journey.save(
            update_fields=[
                "fixed_quality_percent",
            ],
        )

        assessment = build_trainee_assessment(
            journey,
        )

        self.assertTrue(
            assessment.readiness.is_ready,
        )
        self.assertEqual(
            assessment.readiness.next_stage,
            self.no_review_stage,
        )

    def test_no_review_is_almost_ready_near_probation_end(
        self,
    ):
        journey = self.create_journey(
            stage=self.no_review_stage,
            probation_days_ago=80,
            stage_days_ago=14,
        )

        self.create_metric(
            journey,
            speed="6.0",
            quality=None,
        )

        assessment = build_trainee_assessment(
            journey,
        )

        self.assertTrue(
            assessment.readiness.is_almost_ready,
        )

        reason_codes = {
            reason.code
            for reason
            in assessment.readiness.reasons
        }

        self.assertEqual(
            reason_codes,
            {
                "probation_not_finished",
            },
        )

    def test_no_review_is_ready_after_probation_with_target_speed(
        self,
    ):
        journey = self.create_journey(
            stage=self.no_review_stage,
            probation_days_ago=90,
            stage_days_ago=14,
        )

        self.create_metric(
            journey,
            speed="6.0",
            quality=None,
        )

        assessment = build_trainee_assessment(
            journey,
        )

        self.assertTrue(
            assessment.readiness.is_ready,
        )
        self.assertEqual(
            assessment.readiness.next_stage,
            self.done_stage,
        )

    def test_attention_danger_produces_high_risk(
        self,
    ):
        journey = self.create_journey(
            stage=self.with_review_stage,
            stage_days_ago=25,
        )

        assessment = build_trainee_assessment(
            journey,
        )

        self.assertTrue(
            assessment.requires_attention,
        )
        self.assertEqual(
            assessment.risk_level,
            RiskLevel.HIGH,
        )

    def test_manual_risk_override_has_priority(
        self,
    ):
        journey = self.create_journey(
            stage=self.with_review_stage,
            stage_days_ago=25,
        )

        journey.manual_risk_override = (
            RiskLevel.LOW
        )
        journey.save(
            update_fields=[
                "manual_risk_override",
            ],
        )

        assessment = build_trainee_assessment(
            journey,
        )

        self.assertEqual(
            assessment.risk_level,
            RiskLevel.LOW,
        )
