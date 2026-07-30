from datetime import date, timedelta

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.test import TestCase

from traineediary.models import (
    CompletionStatus,
    EntryType,
    StageGroup,
    TraineeJourney,
    TraineeStage,
)


class TraineeCompletionModelTests(TestCase):
    def setUp(self):
        self.active_stage = (
            TraineeStage.objects.create(
                name="Без проверок",
                slug="completion-no-review",
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
                slug="completion-done",
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
                username="completion-mentor",
                password="test",
                is_staff=True,
            )
        )

        self.trainee = (
            User.objects.create_user(
                username="completion-trainee",
                password="test",
            )
        )

        self.today = date.today()

        self.journey = (
            TraineeJourney.objects.create(
                user=self.trainee,
                entry_type=EntryType.NEW_HIRE,
                probation_start_date=(
                    self.today
                    - timedelta(days=30)
                ),
                current_stage=self.active_stage,
                stage_started_at=(
                    self.today
                    - timedelta(days=14)
                ),
            )
        )

    def test_successful_completion_moves_to_done_stage(
        self,
    ):
        previous_stage = (
            self.journey.complete_probation(
                status=CompletionStatus.SUCCESS,
                completed_at=self.today,
                completed_by=self.mentor,
                comment=(
                    "Плановые показатели выполнены."
                ),
            )
        )

        self.journey.refresh_from_db()

        self.assertEqual(
            previous_stage,
            self.active_stage,
        )
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
            self.today,
        )
        self.assertEqual(
            self.journey.completed_by,
            self.mentor,
        )
        self.assertEqual(
            self.journey.completion_comment,
            "Плановые показатели выполнены.",
        )
        self.assertEqual(
            self.journey.days_left_until_probation_end,
            0,
        )
        self.assertEqual(
            self.journey.progress_percent,
            100,
        )

        old_history = (
            self.journey.stage_history.get(
                stage=self.active_stage,
            )
        )

        self.assertEqual(
            old_history.ended_at,
            self.today,
        )

        done_history = (
            self.journey.stage_history.get(
                stage=self.done_stage,
                ended_at__isnull=True,
            )
        )

        self.assertEqual(
            done_history.started_at,
            self.today,
        )
        self.assertEqual(
            done_history.changed_by,
            self.mentor,
        )
        self.assertEqual(
            done_history.note,
            "Плановые показатели выполнены.",
        )

    def test_terminated_completion_requires_comment(
        self,
    ):
        with self.assertRaises(
            ValidationError,
        ) as error:
            self.journey.complete_probation(
                status=(
                    CompletionStatus.TERMINATED
                ),
                completed_at=self.today,
                completed_by=self.mentor,
                comment="",
            )

        self.assertIn(
            "completion_comment",
            error.exception.message_dict,
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

    def test_completion_rejects_future_date(
        self,
    ):
        with self.assertRaises(
            ValidationError,
        ) as error:
            self.journey.complete_probation(
                status=CompletionStatus.SUCCESS,
                completed_at=(
                    self.today
                    + timedelta(days=1)
                ),
                completed_by=self.mentor,
            )

        self.assertIn(
            "completed_at",
            error.exception.message_dict,
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

    def test_completion_cannot_be_saved_on_active_stage(
        self,
    ):
        self.journey.completion_status = (
            CompletionStatus.SUCCESS
        )
        self.journey.completed_at = self.today

        with self.assertRaises(
            ValidationError,
        ) as error:
            self.journey.full_clean()

        self.assertIn(
            "completion_status",
            error.exception.message_dict,
        )

    def test_completed_duration_does_not_keep_growing(
        self,
    ):
        completed_at = (
            self.journey.probation_start_date
            + timedelta(days=20)
        )

        self.journey.stage_started_at = (
            completed_at
            - timedelta(days=5)
        )
        self.journey.save(
            update_fields=[
                "stage_started_at",
            ],
        )

        self.journey.complete_probation(
            status=CompletionStatus.SUCCESS,
            completed_at=completed_at,
            completed_by=self.mentor,
        )

        self.journey.refresh_from_db()

        self.assertEqual(
            self.journey.days_total,
            20,
        )
        self.assertEqual(
            self.journey.days_on_stage,
            0,
        )
        self.assertEqual(
            self.journey.progress_percent,
            100,
        )
