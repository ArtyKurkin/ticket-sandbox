from datetime import date
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


class DashboardViewTests(TestCase):
    def setUp(self):
        self.stage = TraineeStage.objects.create(
            name="В тикетах с проверками",
            slug="with-review-dashboard",
            order=7,
            min_days=15,
            max_days=20,
            progress_weight_percent=35,
            group=StageGroup.WITH_REVIEW,
        )
        self.staff_user = User.objects.create_user(
            username="mentor1", password="test", is_staff=True,
        )
        self.trainee_user = User.objects.create_user(
            username="trainee2", password="test",
        )
        TraineeJourney.objects.create(
            user=self.trainee_user,
            entry_type=EntryType.NEW_HIRE,
            probation_start_date=date.today(),
            current_stage=self.stage,
            stage_started_at=date.today(),
        )

    def test_staff_can_view_dashboard(self):
        self.client.login(username="mentor1", password="test")
        response = self.client.get(reverse("traineediary:dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Дневник")

    def test_non_staff_gets_403(self):
        self.client.login(username="trainee2", password="test")
        response = self.client.get(reverse("traineediary:dashboard"))
        self.assertEqual(response.status_code, 403)

    def test_anonymous_is_redirected_to_login(self):
        response = self.client.get(reverse("traineediary:dashboard"))
        self.assertEqual(response.status_code, 302)


class WeeklyPulseDashboardTests(TestCase):
    def setUp(self):
        self.stage = TraineeStage.objects.create(
            name="В тикетах с проверками",
            slug="with-review-weekly-pulse",
            order=7,
            group=StageGroup.WITH_REVIEW,
        )

        self.staff_user = User.objects.create_user(
            username="pulse-mentor",
            password="test",
            is_staff=True,
        )

        self.trainee_user = User.objects.create_user(
            username="pulse-trainee",
            password="test",
            first_name="Иван",
            last_name="Петров",
        )

        self.journey = TraineeJourney.objects.create(
            user=self.trainee_user,
            entry_type=EntryType.NEW_HIRE,
            probation_start_date=date.today(),
            current_stage=self.stage,
            stage_started_at=date.today(),
        )

    def test_dashboard_builds_weekly_pulse(self):
        WeeklyMetric.objects.create(
            journey=self.journey,
            week_number=1,
            speed_hours=Decimal("4.5"),
            quality_percent=82,
        )
        WeeklyMetric.objects.create(
            journey=self.journey,
            week_number=2,
            speed_hours=Decimal("6.0"),
            quality_percent=78,
        )

        self.client.login(
            username="pulse-mentor",
            password="test",
        )

        response = self.client.get(
            reverse("traineediary:dashboard"),
        )

        self.assertEqual(response.status_code, 200)

        pulse = response.context["weekly_pulse"]

        self.assertEqual(len(pulse), 1)

        item = pulse[0]

        self.assertEqual(
            item["journey"],
            self.journey,
        )
        self.assertEqual(
            item["speed_delta"],
            Decimal("1.5"),
        )
        self.assertEqual(
            item["quality_delta"],
            -4,
        )
        self.assertEqual(
            item["speed_state"],
            "up",
        )
        self.assertEqual(
            item["quality_state"],
            "down",
        )
        self.assertEqual(
            item["overall_state"],
            "danger",
        )

        self.assertContains(
            response,
            "Пульс недели",
        )
        self.assertContains(
            response,
            "Иван Петров",
        )

    def test_dashboard_excludes_trainee_with_one_week(self):
        WeeklyMetric.objects.create(
            journey=self.journey,
            week_number=1,
            speed_hours=Decimal("5.0"),
            quality_percent=75,
        )

        self.client.login(
            username="pulse-mentor",
            password="test",
        )

        response = self.client.get(
            reverse("traineediary:dashboard"),
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.context["weekly_pulse"],
            [],
        )
        self.assertContains(
            response,
            "Пока недостаточно данных",
        )

    def test_dashboard_puts_declines_before_growth(self):
        WeeklyMetric.objects.create(
            journey=self.journey,
            week_number=1,
            speed_hours=Decimal("6.0"),
            quality_percent=85,
        )
        WeeklyMetric.objects.create(
            journey=self.journey,
            week_number=2,
            speed_hours=Decimal("5.5"),
            quality_percent=80,
        )

        growth_user = User.objects.create_user(
            username="pulse-growth",
            password="test",
            first_name="Анна",
            last_name="Смирнова",
        )
        growth_journey = TraineeJourney.objects.create(
            user=growth_user,
            entry_type=EntryType.NEW_HIRE,
            probation_start_date=date.today(),
            current_stage=self.stage,
            stage_started_at=date.today(),
        )

        WeeklyMetric.objects.create(
            journey=growth_journey,
            week_number=1,
            speed_hours=Decimal("4.0"),
            quality_percent=70,
        )
        WeeklyMetric.objects.create(
            journey=growth_journey,
            week_number=2,
            speed_hours=Decimal("5.0"),
            quality_percent=78,
        )

        self.client.login(
            username="pulse-mentor",
            password="test",
        )

        response = self.client.get(
            reverse("traineediary:dashboard"),
        )

        pulse = response.context["weekly_pulse"]

        self.assertEqual(
            pulse[0]["journey"],
            self.journey,
        )
        self.assertEqual(
            pulse[0]["overall_state"],
            "danger",
        )
        self.assertEqual(
            pulse[1]["journey"],
            growth_journey,
        )
        self.assertEqual(
            pulse[1]["overall_state"],
            "success",
        )
