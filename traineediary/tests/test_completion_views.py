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


class TraineeCompletionViewTests(TestCase):
    def setUp(self):
        self.active_stage = (
            TraineeStage.objects.create(
                name="Без проверок",
                slug="completion-view-active",
                order=10,
                min_days=14,
                max_days=30,
                progress_weight_percent=80,
                group=StageGroup.NO_REVIEW,
                applies_to_new_hire=True,
                applies_to_internal_transfer=True,
            )
        )

        self.done_stage = (
            TraineeStage.objects.create(
                name="Выход с ИС",
                slug="completion-view-done",
                order=20,
                min_days=0,
                max_days=1,
                progress_weight_percent=20,
                group=StageGroup.DONE,
                applies_to_new_hire=True,
                applies_to_internal_transfer=True,
            )
        )

        self.mentor = (
            User.objects.create_user(
                username="completion-view-mentor",
                password="test",
                is_staff=True,
            )
        )

        self.trainee = (
            User.objects.create_user(
                username="completion-view-trainee",
                password="test",
                first_name="Иван",
                last_name="Петров",
            )
        )

        self.journey = (
            TraineeJourney.objects.create(
                user=self.trainee,
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
        )

        self.url = reverse(
            "traineediary:complete_trainee",
            args=[self.journey.id],
        )

    def test_staff_can_open_completion_page(
        self,
    ):
        self.client.force_login(
            self.mentor,
        )

        response = self.client.get(
            self.url,
        )

        self.assertEqual(
            response.status_code,
            200,
        )
        self.assertContains(
            response,
            "Завершение",
        )
        self.assertContains(
            response,
            "испытательного срока",
        )
        self.assertContains(
            response,
            "Иван Петров",
        )

    def test_non_staff_cannot_open_completion_page(
        self,
    ):
        self.client.force_login(
            self.trainee,
        )

        response = self.client.get(
            self.url,
        )

        self.assertEqual(
            response.status_code,
            403,
        )

    def test_successful_completion(
        self,
    ):
        self.client.force_login(
            self.mentor,
        )

        response = self.client.post(
            self.url,
            {
                "completion_status": (
                    CompletionStatus.SUCCESS
                ),
                "completed_at": (
                    date.today().isoformat()
                ),
                "completion_comment": (
                    "Плановые показатели выполнены."
                ),
            },
        )

        self.assertRedirects(
            response,
            reverse(
                "traineediary:trainee_detail",
                args=[self.journey.id],
            ),
        )

        self.journey.refresh_from_db()

        self.assertEqual(
            self.journey.current_stage,
            self.done_stage,
        )
        self.assertEqual(
            self.journey.completion_status,
            CompletionStatus.SUCCESS,
        )
        self.assertEqual(
            self.journey.completed_at,
            date.today(),
        )
        self.assertEqual(
            self.journey.completed_by,
            self.mentor,
        )
        self.assertEqual(
            self.journey.completion_comment,
            "Плановые показатели выполнены.",
        )

    def test_termination_requires_comment(
        self,
    ):
        self.client.force_login(
            self.mentor,
        )

        response = self.client.post(
            self.url,
            {
                "completion_status": (
                    CompletionStatus.TERMINATED
                ),
                "completed_at": (
                    date.today().isoformat()
                ),
                "completion_comment": "",
            },
        )

        self.assertEqual(
            response.status_code,
            200,
        )
        self.assertContains(
            response,
            (
                "При прекращении "
                "испытательного срока "
                "укажи причину."
            ),
        )

        self.journey.refresh_from_db()

        self.assertEqual(
            self.journey.current_stage,
            self.active_stage,
        )
        self.assertEqual(
            self.journey.completion_status,
            "",
        )
        self.assertIsNone(
            self.journey.completed_at,
        )

    def test_completed_journey_redirects_to_detail(
        self,
    ):
        self.journey.complete_probation(
            status=CompletionStatus.SUCCESS,
            completed_at=date.today(),
            completed_by=self.mentor,
        )

        self.client.force_login(
            self.mentor,
        )

        response = self.client.get(
            self.url,
        )

        self.assertRedirects(
            response,
            reverse(
                "traineediary:trainee_detail",
                args=[self.journey.id],
            ),
        )

    def test_completed_detail_shows_result_and_comment(
        self,
    ):
        self.journey.complete_probation(
            status=CompletionStatus.SUCCESS,
            completed_at=date.today(),
            completed_by=self.mentor,
            comment=(
                "Сотрудник выполнил "
                "плановые показатели."
            ),
        )

        self.client.force_login(
            self.mentor,
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
            (
                "Испытательный срок "
                "успешно пройден"
            ),
        )
        self.assertContains(
            response,
            "Сотрудник выполнил плановые показатели.",
        )
        self.assertContains(
            response,
            self.mentor.username,
        )
