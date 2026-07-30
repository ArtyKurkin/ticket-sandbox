from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from sandbox.models import TraineeProfile
from traineediary.models import (
    EntryType,
    StageGroup,
    TraineeJourney,
    TraineeStage,
    WeeklyMetric,
)


class AssessmentViewIntegrationTests(
    TestCase,
):
    def setUp(self):
        self.staff_user = (
            User.objects.create_user(
                username="assessment-view-mentor",
                password="test",
                is_staff=True,
            )
        )

        self.with_review_stage = (
            TraineeStage.objects.create(
                name="В тикетах с проверками",
                slug="assessment-view-with-review",
                order=10,
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
                slug="assessment-view-optional",
                order=20,
                min_days=7,
                max_days=14,
                progress_weight_percent=20,
                group=StageGroup.OPTIONAL_REVIEW,
                applies_to_new_hire=True,
                applies_to_internal_transfer=True,
            )
        )

        self.trainee_user = (
            User.objects.create_user(
                username="assessment-view-trainee",
                password="test",
                first_name="Иван",
                last_name="Петров",
            )
        )

        TraineeProfile.objects.update_or_create(
            user=self.trainee_user,
            defaults={
                "level": TraineeProfile.Level.L1,
            },
        )

        self.journey = (
            TraineeJourney.objects.create(
                user=self.trainee_user,
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
                    - timedelta(days=15)
                ),
            )
        )

        WeeklyMetric.objects.create(
            journey=self.journey,
            week_number=1,
            week_start_date=(
                self.journey.stage_started_at
            ),
            speed_hours=Decimal("6.0"),
            quality_percent=80,
        )

        self.client.login(
            username="assessment-view-mentor",
            password="test",
        )

    def test_dashboard_uses_assessment_readiness(
        self,
    ):
        response = self.client.get(
            reverse(
                "traineediary:dashboard",
            ),
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        row = next(
            row
            for row in response.context["rows"]
            if (
                row["journey"].id
                == self.journey.id
            )
        )

        assessment = row["assessment"]

        self.assertTrue(
            assessment.readiness.is_ready,
        )
        self.assertEqual(
            assessment.readiness.next_stage,
            self.optional_stage,
        )
        self.assertEqual(
            response.context[
                "ready_to_transition_count"
            ],
            1,
        )

    def test_dashboard_shows_almost_ready_state(
        self,
    ):
        self.journey.stage_started_at = (
            date.today()
            - timedelta(days=13)
        )

        self.journey.save(
            update_fields=[
                "stage_started_at",
            ],
        )

        response = self.client.get(
            reverse(
                "traineediary:dashboard",
            ),
        )

        self.assertEqual(
            response.status_code,
            200,
        )
        self.assertEqual(
            response.context[
                "ready_to_transition_count"
            ],
            0,
        )
        row = next(
            row
            for row in response.context["rows"]
            if row["journey"].id
            == self.journey.id
        )

        self.assertTrue(
            row[
                "assessment"
            ].readiness.is_almost_ready,
        )

    def test_kanban_uses_assessment_next_stage(
        self,
    ):
        response = self.client.get(
            reverse(
                "traineediary:trainees_kanban",
            ),
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        cards = [
            card
            for column
            in response.context["columns"]
            for card
            in column["cards"]
        ]

        card = next(
            card
            for card in cards
            if (
                card["journey"].id
                == self.journey.id
            )
        )

        assessment = card["assessment"]

        self.assertTrue(
            assessment.readiness.is_ready,
        )
        self.assertEqual(
            assessment.readiness.next_stage,
            self.optional_stage,
        )

        self.assertContains(
            response,
            (
                'data-kanban-stage-move-button'
            ),
        )
        self.assertContains(
            response,
            (
                f'data-stage-name="'
                f'{self.optional_stage.name}"'
            ),
        )

    def test_trainee_detail_uses_assessment(
        self,
    ):
        response = self.client.get(
            reverse(
                "traineediary:trainee_detail",
                args=[self.journey.id],
            ),
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        assessment = response.context[
            "assessment"
        ]

        self.assertTrue(
            assessment.readiness.is_ready,
        )
        self.assertEqual(
            assessment.readiness.next_stage,
            self.optional_stage,
        )

        self.assertContains(
            response,
            "Переход на следующий этап",
        )
        self.assertContains(
            response,
            "Готов к переходу",
        )
        self.assertContains(
            response,
            "Можно переводить сотрудника",
        )
        self.assertContains(
            response,
            self.optional_stage.name,
        )

    def test_trainee_detail_shows_readiness_reason(
        self,
    ):
        metric = self.journey.weekly_metrics.get(
            week_number=1,
        )

        metric.quality_percent = 79
        metric.save(
            update_fields=[
                "quality_percent",
            ],
        )

        response = self.client.get(
            reverse(
                "traineediary:trainee_detail",
                args=[self.journey.id],
            ),
        )

        self.assertEqual(
            response.status_code,
            200,
        )
        self.assertContains(
            response,
            "Для перехода необходимо:",
        )
        self.assertContains(
            response,
            "Качество ниже плана",
        )
