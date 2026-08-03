from datetime import date, timedelta
from io import StringIO

from django.contrib.auth.models import User
from django.core.management import (
    call_command,
)
from django.core.management.base import (
    CommandError,
)
from django.test import TestCase

from traineediary.models import (
    EntryType,
    StageGroup,
    StageHistory,
    TraineeJourney,
    TraineeStage,
)


class CheckTraineeIntegrityCommandTests(
    TestCase,
):
    def setUp(self):
        self.first_stage = (
            TraineeStage.objects.create(
                name="С проверками",
                slug=(
                    "integrity-with-review"
                ),
                order=1,
                group=(
                    StageGroup.WITH_REVIEW
                ),
                applies_to_new_hire=True,
                applies_to_internal_transfer=True,
            )
        )

        self.second_stage = (
            TraineeStage.objects.create(
                name="Без проверок",
                slug=(
                    "integrity-no-review"
                ),
                order=2,
                group=StageGroup.NO_REVIEW,
                applies_to_new_hire=True,
                applies_to_internal_transfer=True,
            )
        )

        self.done_stage = (
            TraineeStage.objects.create(
                name="Выход с ИС",
                slug="integrity-done",
                order=3,
                group=StageGroup.DONE,
                applies_to_new_hire=True,
                applies_to_internal_transfer=True,
            )
        )

    def create_journey(
        self,
        *,
        username,
        stage=None,
        started_at=None,
    ):
        started_at = (
            started_at
            or date.today()
            - timedelta(days=10)
        )

        user = User.objects.create_user(
            username=username,
            password="test",
        )

        return TraineeJourney.objects.create(
            user=user,
            entry_type=EntryType.NEW_HIRE,
            probation_start_date=(
                started_at
            ),
            current_stage=(
                stage
                or self.first_stage
            ),
            stage_started_at=(
                started_at
            ),
        )

    def test_clean_data_passes(
        self,
    ):
        self.create_journey(
            username="integrity-clean",
        )

        stdout = StringIO()
        stderr = StringIO()

        call_command(
            "check_trainee_integrity",
            stdout=stdout,
            stderr=stderr,
        )

        self.assertIn(
            "проблем не найдено",
            stdout.getvalue(),
        )

        self.assertEqual(
            stderr.getvalue(),
            "",
        )

    def test_reports_current_stage_mismatch(
        self,
    ):
        journey = self.create_journey(
            username=(
                "integrity-stage-mismatch"
            ),
        )

        journey.stage_history.update(
            stage=self.second_stage,
        )

        stderr = StringIO()

        with self.assertRaises(
            CommandError,
        ):
            call_command(
                "check_trainee_integrity",
                stdout=StringIO(),
                stderr=stderr,
            )

        self.assertIn(
            "CURRENT_STAGE_MISMATCH",
            stderr.getvalue(),
        )

    def test_reports_multiple_open_history_entries(
        self,
    ):
        journey = self.create_journey(
            username=(
                "integrity-open-history"
            ),
        )

        StageHistory.objects.create(
            journey=journey,
            stage=self.second_stage,
            started_at=(
                journey.stage_started_at
            ),
        )

        stderr = StringIO()

        with self.assertRaises(
            CommandError,
        ):
            call_command(
                "check_trainee_integrity",
                stdout=StringIO(),
                stderr=stderr,
            )

        self.assertIn(
            "OPEN_HISTORY_COUNT",
            stderr.getvalue(),
        )

    def test_reports_done_without_completion_data(
        self,
    ):
        self.create_journey(
            username=(
                "integrity-done-without-result"
            ),
            stage=self.done_stage,
        )

        stderr = StringIO()

        with self.assertRaises(
            CommandError,
        ):
            call_command(
                "check_trainee_integrity",
                stdout=StringIO(),
                stderr=stderr,
            )

        output = stderr.getvalue()

        self.assertIn(
            "DONE_WITHOUT_COMPLETION_STATUS",
            output,
        )

        self.assertIn(
            "DONE_WITHOUT_COMPLETED_AT",
            output,
        )

    def test_journey_id_limits_check(
        self,
    ):
        clean_journey = self.create_journey(
            username=(
                "integrity-filter-clean"
            ),
        )

        broken_journey = self.create_journey(
            username=(
                "integrity-filter-broken"
            ),
        )

        broken_journey.stage_history.update(
            stage=self.second_stage,
        )

        stdout = StringIO()
        stderr = StringIO()

        call_command(
            "check_trainee_integrity",
            "--journey-id",
            str(clean_journey.id),
            stdout=stdout,
            stderr=stderr,
        )

        self.assertIn(
            "карточек 1",
            stdout.getvalue(),
        )

        self.assertEqual(
            stderr.getvalue(),
            "",
        )

    def test_unknown_journey_id_fails(
        self,
    ):
        with self.assertRaisesMessage(
            CommandError,
            "Карточки не найдены: 999999.",
        ):
            call_command(
                "check_trainee_integrity",
                "--journey-id",
                "999999",
                stdout=StringIO(),
                stderr=StringIO(),
            )
