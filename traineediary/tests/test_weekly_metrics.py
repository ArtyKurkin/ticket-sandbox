from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

from traineediary.models import (
    EntryType,
    StageGroup,
    TraineeJourney,
    TraineeStage,
    WeeklyMetric,
)


class WeeklyMetricModelTests(TestCase):
    def setUp(self):
        self.stage = TraineeStage.objects.create(
            name="С проверками",
            slug="with-review-weekly-model",
            order=7,
            group=StageGroup.WITH_REVIEW,
        )
        self.user = User.objects.create_user(
            username="weekly-model-user",
            password="test",
        )
        self.journey = TraineeJourney.objects.create(
            user=self.user,
            entry_type=EntryType.NEW_HIRE,
            probation_start_date=date.today(),
            current_stage=self.stage,
            stage_started_at=date.today(),
        )

    def test_week_number_must_start_from_one(self):
        metric = WeeklyMetric(
            journey=self.journey,
            week_number=0,
            speed_hours=Decimal("6.0"),
            quality_percent=80,
        )

        with self.assertRaises(ValidationError):
            metric.full_clean()

    def test_speed_cannot_be_negative(self):
        metric = WeeklyMetric(
            journey=self.journey,
            week_number=1,
            speed_hours=Decimal("-0.1"),
            quality_percent=80,
        )

        with self.assertRaises(ValidationError):
            metric.full_clean()

    def test_quality_cannot_exceed_100(self):
        metric = WeeklyMetric(
            journey=self.journey,
            week_number=1,
            speed_hours=Decimal("6.0"),
            quality_percent=101,
        )

        with self.assertRaises(ValidationError):
            metric.full_clean()


class WeeklyMetricsViewTests(TestCase):
    def setUp(self):
        self.stage = TraineeStage.objects.create(
            name="С проверками",
            slug="with-review-weekly-view",
            order=7,
            group=StageGroup.WITH_REVIEW,
        )
        self.staff_user = User.objects.create_user(
            username="weekly-mentor",
            password="test",
            is_staff=True,
        )
        self.trainee_user = User.objects.create_user(
            username="weekly-trainee",
            password="test",
            first_name="Иван",
            last_name="Петров",
        )
        self.journey = TraineeJourney.objects.create(
            user=self.trainee_user,
            entry_type=EntryType.NEW_HIRE,
            probation_start_date=date.today() - timedelta(days=14),
            current_stage=self.stage,
            stage_started_at=date.today() - timedelta(days=5),
        )

    def test_staff_can_view_weekly_metrics(self):
        self.client.login(
            username="weekly-mentor",
            password="test",
        )

        response = self.client.get(
            reverse("traineediary:weekly_metrics"),
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Недельные")
        self.assertContains(response, "Иван Петров")
        self.assertContains(response, "Неделя 1")
        self.assertContains(response, "Плановая скорость")
        self.assertContains(response, "Плановое качество")

    def test_non_staff_cannot_view_weekly_metrics(self):
        self.client.login(
            username="weekly-trainee",
            password="test",
        )

        response = self.client.get(
            reverse("traineediary:weekly_metrics"),
        )

        self.assertEqual(response.status_code, 403)

    def test_save_creates_first_week(self):
        self.client.login(
            username="weekly-mentor",
            password="test",
        )

        response = self.client.post(
            reverse(
                "traineediary:save_weekly_metric",
                args=[self.journey.id, 1],
            ),
            {
                "speed_hours": "6.2",
                "quality_percent": "84",
            },
        )

        self.assertRedirects(
            response,
            reverse("traineediary:weekly_metrics"),
        )

        metric = WeeklyMetric.objects.get(
            journey=self.journey,
            week_number=1,
        )

        self.assertEqual(
            metric.speed_hours,
            Decimal("6.2"),
        )
        self.assertEqual(metric.quality_percent, 84)
        self.assertEqual(
            metric.week_start_date,
            self.journey.probation_start_date,
        )

    def test_save_updates_existing_week(self):
        metric = WeeklyMetric.objects.create(
            journey=self.journey,
            week_number=1,
            week_start_date=self.journey.probation_start_date,
            speed_hours=Decimal("5.0"),
            quality_percent=75,
        )

        self.client.login(
            username="weekly-mentor",
            password="test",
        )

        response = self.client.post(
            reverse(
                "traineediary:save_weekly_metric",
                args=[self.journey.id, 1],
            ),
            {
                "speed_hours": "6.5",
                "quality_percent": "88",
            },
        )

        self.assertRedirects(
            response,
            reverse("traineediary:weekly_metrics"),
        )

        metric.refresh_from_db()

        self.assertEqual(
            metric.speed_hours,
            Decimal("6.5"),
        )
        self.assertEqual(metric.quality_percent, 88)

    def test_cannot_skip_week_number(self):
        self.client.login(
            username="weekly-mentor",
            password="test",
        )

        response = self.client.post(
            reverse(
                "traineediary:save_weekly_metric",
                args=[self.journey.id, 2],
            ),
            {
                "speed_hours": "6.0",
                "quality_percent": "80",
            },
        )

        self.assertRedirects(
            response,
            reverse("traineediary:weekly_metrics"),
        )
        self.assertFalse(
            WeeklyMetric.objects.filter(
                journey=self.journey,
                week_number=2,
            ).exists(),
        )

    def test_page_shows_existing_and_next_week(self):
        WeeklyMetric.objects.create(
            journey=self.journey,
            week_number=1,
            week_start_date=self.journey.probation_start_date,
            speed_hours=Decimal("6.0"),
            quality_percent=80,
        )

        self.client.login(
            username="weekly-mentor",
            password="test",
        )

        response = self.client.get(
            reverse("traineediary:weekly_metrics"),
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Неделя 1")
        self.assertContains(response, "Неделя 2")
        self.assertContains(
            response,
            reverse(
                "traineediary:save_weekly_metric",
                args=[self.journey.id, 2],
            ),
        )

    def test_invalid_metric_is_not_saved(self):
        self.client.login(
            username="weekly-mentor",
            password="test",
        )

        response = self.client.post(
            reverse(
                "traineediary:save_weekly_metric",
                args=[self.journey.id, 1],
            ),
            {
                "speed_hours": "-1",
                "quality_percent": "120",
            },
        )

        self.assertRedirects(
            response,
            reverse("traineediary:weekly_metrics"),
        )
        self.assertFalse(
            WeeklyMetric.objects.filter(
                journey=self.journey,
            ).exists(),
        )
