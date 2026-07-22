from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase

from traineediary.models import (
    EntryType,
    StageGroup,
    TraineeJourney,
    TraineeStage,
    WeeklyMetric,
)
from traineediary.services.attention import (
    build_attention_summary,
)


class TraineeAttentionSummaryTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="attention-trainee",
            password="test",
        )

        self.with_review_stage = (
            TraineeStage.objects.create(
                name="В тикетах с проверками",
                slug="attention-with-review",
                order=7,
                min_days=15,
                max_days=20,
                progress_weight_percent=35,
                group=StageGroup.WITH_REVIEW,
                applies_to_new_hire=True,
                applies_to_internal_transfer=True,
            )
        )

        self.optional_stage = (
            TraineeStage.objects.create(
                name="Кнопка по желанию",
                slug="attention-optional",
                order=8,
                min_days=5,
                max_days=10,
                progress_weight_percent=20,
                group=StageGroup.OPTIONAL_REVIEW,
                applies_to_new_hire=True,
                applies_to_internal_transfer=True,
            )
        )

        self.no_review_stage = (
            TraineeStage.objects.create(
                name="Без проверок",
                slug="attention-no-review",
                order=9,
                min_days=10,
                max_days=10,
                progress_weight_percent=20,
                group=StageGroup.NO_REVIEW,
                applies_to_new_hire=True,
                applies_to_internal_transfer=True,
            )
        )

        self.journey = (
            TraineeJourney.objects.create(
                user=self.user,
                entry_type=EntryType.NEW_HIRE,
                probation_start_date=(
                    date.today()
                    - timedelta(days=30)
                ),
                current_stage=(
                    self.with_review_stage
                ),
                stage_started_at=(
                    date.today()
                    - timedelta(days=5)
                ),
            )
        )

    def create_metric(
        self,
        *,
        speed="6.0",
        quality=80,
        week_number=1,
    ):
        return WeeklyMetric.objects.create(
            journey=self.journey,
            week_number=week_number,
            week_start_date=(
                self.journey.stage_started_at
                + timedelta(
                    weeks=week_number - 1,
                )
            ),
            speed_hours=Decimal(speed),
            quality_percent=quality,
        )

    def reason_codes(self, summary):
        return {
            reason.code
            for reason in summary.reasons
        }

    def test_early_low_metrics_do_not_require_attention(self):
        self.create_metric(
            speed="2.5",
            quality=65,
        )

        summary = build_attention_summary(
            self.journey,
        )

        self.assertFalse(
            summary.requires_attention,
        )

    def test_quality_is_checked_at_end_of_with_review_stage(self):
        self.journey.stage_started_at = (
            date.today()
            - timedelta(days=20)
        )

        self.journey.save(
            update_fields=[
                "stage_started_at",
            ],
        )

        self.create_metric(
            speed="4.0",
            quality=76,
        )

        summary = build_attention_summary(
            self.journey,
        )

        self.assertIn(
            "quality_below_target",
            self.reason_codes(summary),
        )

    def test_missing_quality_is_reported_at_stage_limit(self):
        self.journey.stage_started_at = (
            date.today()
            - timedelta(days=20)
        )

        self.journey.save(
            update_fields=[
                "stage_started_at",
            ],
        )

        summary = build_attention_summary(
            self.journey,
        )

        self.assertIn(
            "quality_missing",
            self.reason_codes(summary),
        )

    def test_quality_is_ignored_after_with_review(self):
        self.journey.current_stage = (
            self.optional_stage
        )
        self.journey.stage_started_at = (
            date.today()
            - timedelta(days=2)
        )
        self.journey.fixed_quality_percent = 60

        self.journey.save(
            update_fields=[
                "current_stage",
                "stage_started_at",
                "fixed_quality_percent",
            ],
        )

        self.create_metric(
            speed="4.0",
            quality=60,
        )

        summary = build_attention_summary(
            self.journey,
        )

        codes = self.reason_codes(summary)

        self.assertNotIn(
            "quality_below_target",
            codes,
        )
        self.assertNotIn(
            "fixed_quality_below_target",
            codes,
        )

    def test_low_speed_is_ignored_early_in_probation(self):
        self.journey.current_stage = (
            self.no_review_stage
        )
        self.journey.stage_started_at = (
            date.today()
            - timedelta(days=2)
        )

        self.journey.save(
            update_fields=[
                "current_stage",
                "stage_started_at",
            ],
        )

        self.create_metric(
            speed="4.0",
            quality=None,
        )

        summary = build_attention_summary(
            self.journey,
        )

        self.assertNotIn(
            "final_speed_below_target",
            self.reason_codes(summary),
        )

    def test_low_speed_requires_attention_near_probation_end(self):
        self.journey.probation_start_date = (
            date.today()
            - timedelta(days=80)
        )
        self.journey.current_stage = (
            self.no_review_stage
        )
        self.journey.stage_started_at = (
            date.today()
            - timedelta(days=2)
        )

        self.journey.save(
            update_fields=[
                "probation_start_date",
                "current_stage",
                "stage_started_at",
            ],
        )

        self.create_metric(
            speed="5.2",
            quality=None,
        )

        summary = build_attention_summary(
            self.journey,
        )

        self.assertIn(
            "final_speed_below_target",
            self.reason_codes(summary),
        )

    def test_route_delay_requires_attention_near_probation_end(self):
        self.journey.probation_start_date = (
            date.today()
            - timedelta(days=80)
        )

        self.journey.save(
            update_fields=[
                "probation_start_date",
            ],
        )

        summary = build_attention_summary(
            self.journey,
        )

        self.assertIn(
            "behind_probation_route",
            self.reason_codes(summary),
        )

    def test_overdue_stage_always_requires_attention(self):
        self.journey.stage_started_at = (
            date.today()
            - timedelta(days=25)
        )

        self.journey.save(
            update_fields=[
                "stage_started_at",
            ],
        )

        summary = build_attention_summary(
            self.journey,
        )

        self.assertIn(
            "stage_overdue",
            self.reason_codes(summary),
        )

        self.assertEqual(
            summary.highest_severity,
            "danger",
        )

    def test_manual_high_risk_requires_attention(self):
        self.journey.manual_risk_override = (
            "high"
        )

        self.journey.save(
            update_fields=[
                "manual_risk_override",
            ],
        )

        summary = build_attention_summary(
            self.journey,
        )

        self.assertIn(
            "manual_high_risk",
            self.reason_codes(summary),
        )
