from datetime import date, timedelta

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from traineediary.models import (
    CompletionStatus,
    EntryType,
    StageGroup,
    TraineeJourney,
    TraineeStage,
)


class DashboardCompletionTests(TestCase):
    def setUp(self):
        self.active_stage = (
            TraineeStage.objects.create(
                name="Без проверок",
                slug=(
                    "dashboard-completion-active"
                ),
                order=10,
                group=StageGroup.NO_REVIEW,
                applies_to_new_hire=True,
                applies_to_internal_transfer=True,
            )
        )

        self.done_stage = (
            TraineeStage.objects.create(
                name="Выход с ИС",
                slug=(
                    "dashboard-completion-done"
                ),
                order=20,
                group=StageGroup.DONE,
                applies_to_new_hire=True,
                applies_to_internal_transfer=True,
            )
        )

        self.mentor = (
            User.objects.create_user(
                username=(
                    "dashboard-completion-mentor"
                ),
                password="test",
                is_staff=True,
            )
        )

        self.success_journey = (
            self._create_journey(
                username="completion-success",
            )
        )

        self.success_journey.complete_probation(
            status=CompletionStatus.SUCCESS,
            completed_at=date.today(),
            completed_by=self.mentor,
            comment="Успешно завершил ИС.",
        )

        self.terminated_journey = (
            self._create_journey(
                username="completion-terminated",
            )
        )

        self.terminated_journey.complete_probation(
            status=(
                CompletionStatus.TERMINATED
            ),
            completed_at=date.today(),
            completed_by=self.mentor,
            comment="ИС прекращён.",
        )

        legacy_user = (
            User.objects.create_user(
                username="completion-missing",
                password="test",
            )
        )

        self.missing_journey = (
            TraineeJourney.objects.create(
                user=legacy_user,
                entry_type=EntryType.NEW_HIRE,
                probation_start_date=(
                    date.today()
                    - timedelta(days=20)
                ),
                current_stage=self.done_stage,
                stage_started_at=date.today(),
            )
        )

        self.client.force_login(
            self.mentor,
        )

    def _create_journey(
        self,
        *,
        username,
    ):
        user = User.objects.create_user(
            username=username,
            password="test",
        )

        return TraineeJourney.objects.create(
            user=user,
            entry_type=EntryType.NEW_HIRE,
            probation_start_date=(
                date.today()
                - timedelta(days=30)
            ),
            current_stage=self.active_stage,
            stage_started_at=(
                date.today()
                - timedelta(days=14)
            ),
        )

    def test_completed_dashboard_shows_result_counts(
        self,
    ):
        response = self.client.get(
            reverse(
                "traineediary:dashboard",
            ),
            {
                "status": "completed",
            },
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        cards = response.context[
            "completion_summary_cards"
        ]

        counts = {
            card["value"]: card["count"]
            for card in cards
        }

        self.assertEqual(
            counts[""],
            3,
        )
        self.assertEqual(
            counts[CompletionStatus.SUCCESS],
            1,
        )
        self.assertEqual(
            counts[
                CompletionStatus.TERMINATED
            ],
            1,
        )
        self.assertEqual(
            counts["missing"],
            1,
        )

        self.assertContains(
            response,
            "Успешно завершили",
        )
        self.assertContains(
            response,
            "ИС прекращён",
        )
        self.assertContains(
            response,
            "Без результата",
        )

    def test_dashboard_filters_successful_completion(
        self,
    ):
        response = self.client.get(
            reverse(
                "traineediary:dashboard",
            ),
            {
                "status": "completed",
                "completion": (
                    CompletionStatus.SUCCESS
                ),
            },
        )

        self.assertEqual(
            response.context["filtered_count"],
            1,
        )
        self.assertContains(
            response,
            "completion-success",
        )
        self.assertNotContains(
            response,
            "completion-terminated",
        )
        self.assertNotContains(
            response,
            "completion-missing",
        )

    def test_dashboard_filters_terminated_completion(
        self,
    ):
        response = self.client.get(
            reverse(
                "traineediary:dashboard",
            ),
            {
                "status": "completed",
                "completion": (
                    CompletionStatus.TERMINATED
                ),
            },
        )

        self.assertEqual(
            response.context["filtered_count"],
            1,
        )
        self.assertContains(
            response,
            "completion-terminated",
        )
        self.assertNotContains(
            response,
            "completion-success",
        )

    def test_dashboard_filters_missing_result(
        self,
    ):
        response = self.client.get(
            reverse(
                "traineediary:dashboard",
            ),
            {
                "status": "completed",
                "completion": "missing",
            },
        )

        self.assertEqual(
            response.context["filtered_count"],
            1,
        )
        self.assertContains(
            response,
            "completion-missing",
        )
        self.assertNotContains(
            response,
            "completion-success",
        )

    def test_invalid_completion_filter_is_ignored(
        self,
    ):
        response = self.client.get(
            reverse(
                "traineediary:dashboard",
            ),
            {
                "status": "completed",
                "completion": "unknown",
            },
        )

        self.assertEqual(
            response.context[
                "filters"
            ]["completion"],
            "",
        )
        self.assertEqual(
            response.context["filtered_count"],
            3,
        )
