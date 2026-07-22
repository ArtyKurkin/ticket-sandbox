from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from traineediary.models import (
    EntryType,
    StageGroup,
    TraineeJourney,
    TraineeStage,
    WeeklyMetric,
)


class DashboardAttentionIntegrationTests(
    TestCase,
):
    def setUp(self):
        self.staff_user = (
            User.objects.create_user(
                username=(
                    "attention-dashboard-mentor"
                ),
                password="test",
                is_staff=True,
            )
        )

        self.trainee_user = (
            User.objects.create_user(
                username=(
                    "attention-dashboard-trainee"
                ),
                password="test",
                first_name="Иван",
                last_name="Петров",
            )
        )

        self.stage = (
            TraineeStage.objects.create(
                name="В тикетах с проверками",
                slug=(
                    "dashboard-attention-"
                    "with-review"
                ),
                order=7,
                min_days=15,
                max_days=20,
                progress_weight_percent=35,
                group=StageGroup.WITH_REVIEW,
                applies_to_new_hire=True,
                applies_to_internal_transfer=True,
            )
        )

        self.journey = (
            TraineeJourney.objects.create(
                user=self.trainee_user,
                entry_type=EntryType.NEW_HIRE,
                probation_start_date=(
                    date.today()
                    - timedelta(days=30)
                ),
                current_stage=self.stage,
                stage_started_at=(
                    date.today()
                    - timedelta(days=5)
                ),
            )
        )

        self.url = reverse(
            "traineediary:dashboard",
        )

    def login_staff(self):
        self.client.login(
            username=(
                "attention-dashboard-mentor"
            ),
            password="test",
        )

    def get_journey_row(self, response):
        return next(
            row
            for row in response.context["rows"]
            if (
                row["journey"].id
                == self.journey.id
            )
        )

    def test_early_low_metrics_do_not_increase_attention_count(
        self,
    ):
        WeeklyMetric.objects.create(
            journey=self.journey,
            week_number=1,
            week_start_date=(
                self.journey.stage_started_at
            ),
            speed_hours=Decimal("2.5"),
            quality_percent=65,
        )

        self.login_staff()

        response = self.client.get(
            self.url,
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        row = self.get_journey_row(
            response,
        )

        self.assertFalse(
            row[
                "attention_summary"
            ].requires_attention,
        )

        self.assertEqual(
            response.context[
                "needs_attention_count"
            ],
            0,
        )

        self.assertNotContains(
            response,
            "Требует внимания",
        )

    def test_overdue_stage_is_shown_on_dashboard(
        self,
    ):
        self.journey.stage_started_at = (
            date.today()
            - timedelta(days=25)
        )

        self.journey.save(
            update_fields=[
                "stage_started_at",
            ],
        )

        self.login_staff()

        response = self.client.get(
            self.url,
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        row = self.get_journey_row(
            response,
        )

        self.assertTrue(
            row[
                "attention_summary"
            ].requires_attention,
        )

        self.assertEqual(
            response.context[
                "needs_attention_count"
            ],
            1,
        )

        self.assertContains(
            response,
            "Требует внимания",
        )

        self.assertContains(
            response,
            "Превышен срок этапа",
        )
