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


class TraineeDetailViewTests(TestCase):
    def setUp(self):
        self.stage = TraineeStage.objects.create(
            name="В тикетах с проверками",
            slug="with-review-detail",
            order=7,
            min_days=15,
            max_days=20,
            progress_weight_percent=35,
            color="#4F64FF",
            group=StageGroup.WITH_REVIEW,
        )

        self.next_stage = TraineeStage.objects.create(
            name="Кнопка по желанию",
            slug="optional-review-detail",
            order=8,
            min_days=7,
            max_days=10,
            progress_weight_percent=20,
            color="#28D17C",
            group=StageGroup.OPTIONAL_REVIEW,
        )

        self.staff_user = User.objects.create_user(
            username="mentor-detail",
            password="test",
            is_staff=True,
        )

        self.trainee_user = User.objects.create_user(
            username="trainee-detail",
            password="test",
            first_name="Иван",
            last_name="Петров",
        )

        self.journey = TraineeJourney.objects.create(
            user=self.trainee_user,
            entry_type=EntryType.NEW_HIRE,
            probation_start_date=date.today() - timedelta(days=20),
            current_stage=self.stage,
            stage_started_at=date.today() - timedelta(days=7),
            comment="Хорошая динамика по качеству.",
        )

    def test_staff_can_view_trainee_detail(self):
        self.client.login(
            username="mentor-detail",
            password="test",
        )

        response = self.client.get(
            reverse(
                "traineediary:trainee_detail",
                args=[self.journey.id],
            ),
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Иван Петров")
        self.assertContains(response, "В тикетах с проверками")
        self.assertContains(response, "Хорошая динамика по качеству.")
        self.assertContains(response, "Открыть в Ticket Sandbox")

    def test_non_staff_cannot_view_trainee_detail(self):
        self.client.login(
            username="trainee-detail",
            password="test",
        )

        response = self.client.get(
            reverse(
                "traineediary:trainee_detail",
                args=[self.journey.id],
            ),
        )

        self.assertEqual(response.status_code, 403)

    def test_anonymous_user_is_redirected_to_login(self):
        response = self.client.get(
            reverse(
                "traineediary:trainee_detail",
                args=[self.journey.id],
            ),
        )

        self.assertEqual(response.status_code, 302)

    def test_detail_shows_stage_history(self):
        transition_date = date.today() - timedelta(days=2)

        self.journey.move_to_stage(
            self.next_stage,
            changed_by=self.staff_user,
            transition_date=transition_date,
            note="Перешёл после стабильной недели.",
        )

        self.client.login(
            username="mentor-detail",
            password="test",
        )

        response = self.client.get(
            reverse(
                "traineediary:trainee_detail",
                args=[self.journey.id],
            ),
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "В тикетах с проверками")
        self.assertContains(response, "Кнопка по желанию")
        self.assertContains(
            response,
            "Перешёл после стабильной недели.",
        )
        self.assertContains(response, "Текущий этап")

    def test_dashboard_contains_link_to_trainee_detail(self):
        self.client.login(
            username="mentor-detail",
            password="test",
        )

        response = self.client.get(
            reverse("traineediary:dashboard"),
        )

        detail_url = reverse(
            "traineediary:trainee_detail",
            args=[self.journey.id],
        )

        self.assertContains(
            response,
            f'href="{detail_url}"',
        )

    def test_kanban_contains_link_to_trainee_detail(self):
        self.client.login(
            username="mentor-detail",
            password="test",
        )

        response = self.client.get(
            reverse("traineediary:trainees_kanban"),
        )

        detail_url = reverse(
            "traineediary:trainee_detail",
            args=[self.journey.id],
        )

        self.assertContains(
            response,
            f'href="{detail_url}"',
        )

    def test_detail_builds_gantt_rows_from_stage_history(self):
        self.client.login(
            username="mentor-detail",
            password="test",
        )

        response = self.client.get(
            reverse(
                "traineediary:trainee_detail",
                args=[self.journey.id],
            ),
        )

        gantt_rows = response.context["gantt_rows"]

        self.assertEqual(len(gantt_rows), 2)

        current_row = next(
            row
            for row in gantt_rows
            if row["stage"] == self.stage
        )
        future_row = next(
            row
            for row in gantt_rows
            if row["stage"] == self.next_stage
        )

        self.assertTrue(current_row["has_started"])
        self.assertTrue(current_row["is_current"])
        self.assertFalse(current_row["is_completed"])
        self.assertEqual(current_row["actual_days"], 7)
        self.assertFalse(current_row["is_overdue"])

        self.assertFalse(future_row["has_started"])
        self.assertFalse(future_row["is_current"])
        self.assertEqual(future_row["actual_days"], 0)

    def test_gantt_marks_overdue_stage(self):
        self.journey.stage_started_at = (
            date.today() - timedelta(days=25)
        )
        self.journey.save(
            update_fields=["stage_started_at"],
        )

        current_history = self.journey.stage_history.get(
            ended_at__isnull=True,
        )
        current_history.started_at = (
            date.today() - timedelta(days=25)
        )
        current_history.save(
            update_fields=["started_at"],
        )

        self.client.login(
            username="mentor-detail",
            password="test",
        )

        response = self.client.get(
            reverse(
                "traineediary:trainee_detail",
                args=[self.journey.id],
            ),
        )

        current_row = next(
            row
            for row in response.context["gantt_rows"]
            if row["stage"] == self.stage
        )

        self.assertEqual(current_row["actual_days"], 25)
        self.assertTrue(current_row["is_overdue"])
        self.assertEqual(current_row["overdue_days"], 5)
        self.assertEqual(
            current_row["actual_width_percent"],
            100,
        )

    def test_internal_transfer_gantt_excludes_teachbase(self):
        teachbase_stage = TraineeStage.objects.create(
            name="Teachbase",
            slug="teachbase-detail-gantt",
            order=1,
            min_days=3,
            max_days=5,
            progress_weight_percent=10,
            group=StageGroup.TEACHBASE,
            applies_to_new_hire=True,
            applies_to_internal_transfer=False,
        )

        internal_user = User.objects.create_user(
            username="internal-detail",
            password="test",
        )
        internal_journey = TraineeJourney.objects.create(
            user=internal_user,
            entry_type=EntryType.INTERNAL_TRANSFER,
            probation_start_date=date.today(),
            current_stage=self.stage,
            stage_started_at=date.today(),
        )

        self.client.login(
            username="mentor-detail",
            password="test",
        )

        response = self.client.get(
            reverse(
                "traineediary:trainee_detail",
                args=[internal_journey.id],
            ),
        )

        gantt_stages = [
            row["stage"]
            for row in response.context["gantt_rows"]
        ]

        self.assertNotIn(teachbase_stage, gantt_stages)
        self.assertIn(self.stage, gantt_stages)
        self.assertIn(self.next_stage, gantt_stages)

    def test_detail_renders_gantt(self):
        self.client.login(
            username="mentor-detail",
            password="test",
        )

        response = self.client.get(
            reverse(
                "traineediary:trainee_detail",
                args=[self.journey.id],
            ),
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            'class="card trainee-gantt-card"',
        )
        self.assertContains(
            response,
            f'data-gantt-stage-id="{self.stage.id}"',
        )
        self.assertContains(
            response,
            f'data-gantt-stage-id="{self.next_stage.id}"',
        )
        self.assertContains(response, "План:")
        self.assertContains(response, "Факт:")
        self.assertContains(response, "Текущий")
        self.assertContains(response, "Ещё не начат")

    def test_detail_renders_overdue_gantt_badge(self):
        started_at = date.today() - timedelta(days=25)

        self.journey.stage_started_at = started_at
        self.journey.save(
            update_fields=["stage_started_at"],
        )

        current_history = self.journey.stage_history.get(
            ended_at__isnull=True,
        )
        current_history.started_at = started_at
        current_history.save(
            update_fields=["started_at"],
        )

        self.client.login(
            username="mentor-detail",
            password="test",
        )

        response = self.client.get(
            reverse(
                "traineediary:trainee_detail",
                args=[self.journey.id],
            ),
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "is-overdue")
        self.assertContains(response, "+5 дн.")

    def test_detail_shows_weekly_metrics_summary_and_charts(self):
        WeeklyMetric.objects.create(
            journey=self.journey,
            week_number=1,
            week_start_date=self.journey.probation_start_date,
            speed_hours=Decimal("4.5"),
            quality_percent=75,
        )
        WeeklyMetric.objects.create(
            journey=self.journey,
            week_number=2,
            week_start_date=(
                self.journey.probation_start_date
                + timedelta(days=7)
            ),
            speed_hours=Decimal("6.0"),
            quality_percent=82,
        )
        WeeklyMetric.objects.create(
            journey=self.journey,
            week_number=3,
            week_start_date=(
                self.journey.probation_start_date
                + timedelta(days=14)
            ),
            speed_hours=Decimal("6.5"),
            quality_percent=88,
        )

        self.client.login(
            username="mentor-detail",
            password="test",
        )

        response = self.client.get(
            reverse(
                "traineediary:trainee_detail",
                args=[self.journey.id],
            ),
        )

        self.assertEqual(response.status_code, 200)

        summary = response.context[
            "weekly_metrics_summary"
        ]

        self.assertEqual(summary["count"], 3)
        self.assertEqual(
            summary["average_speed"],
            Decimal("5.7"),
        )
        self.assertEqual(
            summary["average_quality"],
            82,
        )
        self.assertEqual(
            summary["latest"].week_number,
            3,
        )

        self.assertTrue(
            response.context["speed_chart"]["polyline"],
        )
        self.assertTrue(
            response.context["quality_chart"]["polyline"],
        )

        self.assertContains(response, "Динамика метрик")
        self.assertContains(response, "Средняя скорость")
        self.assertContains(
            response,
            "График скорости по неделям",
        )
        self.assertContains(
            response,
            "График качества по неделям",
        )

    def test_detail_shows_empty_weekly_metrics_state(self):
        self.client.login(
            username="mentor-detail",
            password="test",
        )

        response = self.client.get(
            reverse(
                "traineediary:trainee_detail",
                args=[self.journey.id],
            ),
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.context[
                "weekly_metrics_summary"
            ]["count"],
            0,
        )
        self.assertContains(
            response,
            "Метрики пока не заполнены",
        )
        self.assertContains(
            response,
            reverse("traineediary:weekly_metrics"),
        )
