from decimal import Decimal

from datetime import date, timedelta
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.test import TestCase

from traineediary.models import (
    EntryType,
    RiskLevel,
    StageGroup,
    StageHistory,
    TraineeJourney,
    TraineeStage,
    WeeklyMetric,
)


class TraineeJourneyModelTests(TestCase):
    def setUp(self):
        self.stage = TraineeStage.objects.create(
            name="В тикетах с проверками",
            slug="with-review",
            order=7,
            min_days=15,
            max_days=20,
            progress_weight_percent=35,
            group=StageGroup.WITH_REVIEW,
        )
        self.user = User.objects.create_user(username="trainee1", password="test")
        self.optional_stage = TraineeStage.objects.create(
            name="Кнопка по желанию",
            slug="optional-review-quality",
            order=8,
            group=StageGroup.OPTIONAL_REVIEW,
        )

        self.no_review_stage = TraineeStage.objects.create(
            name="Без проверок",
            slug="no-review-quality",
            order=9,
            group=StageGroup.NO_REVIEW,
        )

    def test_risk_is_low_within_norm(self):
        journey = TraineeJourney.objects.create(
            user=self.user,
            entry_type=EntryType.NEW_HIRE,
            probation_start_date=date.today() - timedelta(days=15),
            current_stage=self.stage,
            stage_started_at=date.today() - timedelta(days=5),
        )
        self.assertEqual(journey.risk_level, RiskLevel.LOW)

    def test_risk_is_high_when_overstayed(self):
        journey = TraineeJourney.objects.create(
            user=self.user,
            entry_type=EntryType.NEW_HIRE,
            probation_start_date=date.today() - timedelta(days=40),
            current_stage=self.stage,
            stage_started_at=date.today() - timedelta(days=30),
        )
        self.assertEqual(journey.risk_level, RiskLevel.HIGH)

    def test_risk_is_none_when_done(self):
        done_stage = TraineeStage.objects.create(
            name="Выход с ИС",
            slug="done",
            order=10,
            group=StageGroup.DONE,
        )
        journey = TraineeJourney.objects.create(
            user=self.user,
            entry_type=EntryType.NEW_HIRE,
            probation_start_date=date.today() - timedelta(days=100),
            current_stage=done_stage,
            stage_started_at=date.today() - timedelta(days=90),
        )
        self.assertIsNone(journey.risk_level)

    def test_move_to_stage_closes_and_opens_history(self):
        journey = TraineeJourney.objects.create(
            user=self.user,
            entry_type=EntryType.NEW_HIRE,
            probation_start_date=date.today(),
            current_stage=self.stage,
            stage_started_at=date.today(),
        )
        new_stage = TraineeStage.objects.create(
            name="Кнопка по желанию",
            slug="optional-review",
            order=8,
            group=StageGroup.OPTIONAL_REVIEW,
        )

        journey.move_to_stage(new_stage, note="Готов к следующему этапу")

        journey.refresh_from_db()
        self.assertEqual(journey.current_stage, new_stage)
        self.assertEqual(journey.stage_history.count(), 2)
        self.assertIsNotNone(
            journey.stage_history.exclude(stage=new_stage).first().ended_at,
        )

    def test_move_to_same_stage_does_not_reset_date_or_duplicate_history(self):
        started_at = date.today() - timedelta(days=5)

        journey = TraineeJourney.objects.create(
            user=self.user,
            entry_type=EntryType.NEW_HIRE,
            probation_start_date=date.today() - timedelta(days=10),
            current_stage=self.stage,
            stage_started_at=started_at,
        )

        journey.move_to_stage(
            self.stage,
            note="Случайный перенос в ту же колонку",
        )

        journey.refresh_from_db()

        self.assertEqual(journey.current_stage, self.stage)
        self.assertEqual(journey.stage_started_at, started_at)
        self.assertEqual(journey.stage_history.count(), 1)
        self.assertIsNone(journey.stage_history.get().ended_at)

    def test_move_to_stage_rolls_back_when_history_creation_fails(self):
        journey = TraineeJourney.objects.create(
            user=self.user,
            entry_type=EntryType.NEW_HIRE,
            probation_start_date=date.today(),
            current_stage=self.stage,
            stage_started_at=date.today(),
        )

        new_stage = TraineeStage.objects.create(
            name="Кнопка по желанию",
            slug="optional-review-rollback",
            order=8,
            group=StageGroup.OPTIONAL_REVIEW,
        )

        with patch.object(
            StageHistory.objects,
            "create",
            side_effect=RuntimeError("Не удалось записать историю"),
        ):
            with self.assertRaisesMessage(
                RuntimeError,
                "Не удалось записать историю",
            ):
                journey.move_to_stage(new_stage)

        journey.refresh_from_db()

        self.assertEqual(journey.current_stage, self.stage)
        self.assertEqual(journey.stage_started_at, date.today())
        self.assertEqual(journey.stage_history.count(), 1)
        self.assertIsNone(journey.stage_history.get().ended_at)

    def test_move_to_stage_uses_selected_date_and_note(self):
        current_stage_started_at = date.today() - timedelta(days=7)
        transition_date = date.today() - timedelta(days=2)

        journey = TraineeJourney.objects.create(
            user=self.user,
            entry_type=EntryType.NEW_HIRE,
            probation_start_date=date.today() - timedelta(days=20),
            current_stage=self.stage,
            stage_started_at=current_stage_started_at,
        )

        new_stage = TraineeStage.objects.create(
            name="Кнопка по желанию с датой",
            slug="optional-review-with-date",
            order=8,
            group=StageGroup.OPTIONAL_REVIEW,
        )

        journey.move_to_stage(
            new_stage,
            changed_by=self.user,
            transition_date=transition_date,
            note="Фактически перешёл два дня назад",
        )

        journey.refresh_from_db()

        previous_history = journey.stage_history.get(stage=self.stage)
        current_history = journey.stage_history.get(stage=new_stage)

        self.assertEqual(journey.current_stage, new_stage)
        self.assertEqual(journey.stage_started_at, transition_date)

        self.assertEqual(previous_history.ended_at, transition_date)
        self.assertEqual(current_history.started_at, transition_date)
        self.assertEqual(
            current_history.note,
            "Фактически перешёл два дня назад",
        )
        self.assertEqual(current_history.changed_by, self.user)

    def test_move_to_stage_rejects_future_date(self):
        journey = TraineeJourney.objects.create(
            user=self.user,
            entry_type=EntryType.NEW_HIRE,
            probation_start_date=date.today(),
            current_stage=self.stage,
            stage_started_at=date.today(),
        )

        new_stage = TraineeStage.objects.create(
            name="Без проверок в будущем",
            slug="no-review-future",
            order=9,
            group=StageGroup.NO_REVIEW,
        )

        with self.assertRaisesMessage(
            ValidationError,
            "Дата начала нового этапа не может быть в будущем.",
        ):
            journey.move_to_stage(
                new_stage,
                transition_date=date.today() + timedelta(days=1),
            )

        journey.refresh_from_db()

        self.assertEqual(journey.current_stage, self.stage)
        self.assertEqual(journey.stage_history.count(), 1)

    def test_leaving_with_review_fixes_latest_quality(self):
        transition_date = (
            date.today() - timedelta(days=1)
        )

        journey = TraineeJourney.objects.create(
            user=self.user,
            entry_type=EntryType.NEW_HIRE,
            probation_start_date=(
                date.today() - timedelta(days=30)
            ),
            current_stage=self.stage,
            stage_started_at=(
                date.today() - timedelta(days=10)
            ),
        )

        WeeklyMetric.objects.create(
            journey=journey,
            week_number=1,
            speed_hours=Decimal("4.5"),
            quality_percent=76,
        )
        WeeklyMetric.objects.create(
            journey=journey,
            week_number=2,
            speed_hours=Decimal("5.5"),
            quality_percent=84,
        )

        journey.move_to_stage(
            self.optional_stage,
            transition_date=transition_date,
        )

        journey.refresh_from_db()

        self.assertEqual(
            journey.fixed_quality_percent,
            84,
        )
        self.assertEqual(
            journey.quality_fixed_at,
            transition_date,
        )

    def test_fixed_quality_is_preserved_after_next_stage(self):
        transition_date = (
            date.today() - timedelta(days=2)
        )

        journey = TraineeJourney.objects.create(
            user=self.user,
            entry_type=EntryType.NEW_HIRE,
            probation_start_date=(
                date.today() - timedelta(days=30)
            ),
            current_stage=self.stage,
            stage_started_at=(
                date.today() - timedelta(days=10)
            ),
        )

        WeeklyMetric.objects.create(
            journey=journey,
            week_number=1,
            speed_hours=Decimal("6.0"),
            quality_percent=83,
        )

        journey.move_to_stage(
            self.optional_stage,
            transition_date=transition_date,
        )
        journey.move_to_stage(
            self.no_review_stage,
            transition_date=date.today(),
        )

        journey.refresh_from_db()

        self.assertEqual(
            journey.fixed_quality_percent,
            83,
        )
        self.assertEqual(
            journey.quality_fixed_at,
            transition_date,
        )

    def test_returning_to_with_review_clears_fixed_quality(self):
        journey = TraineeJourney.objects.create(
            user=self.user,
            entry_type=EntryType.NEW_HIRE,
            probation_start_date=(
                date.today() - timedelta(days=30)
            ),
            current_stage=self.optional_stage,
            stage_started_at=(
                date.today() - timedelta(days=3)
            ),
            fixed_quality_percent=82,
            quality_fixed_at=(
                date.today() - timedelta(days=3)
            ),
        )

        journey.move_to_stage(
            self.stage,
            transition_date=date.today(),
        )

        journey.refresh_from_db()

        self.assertIsNone(
            journey.fixed_quality_percent,
        )
        self.assertIsNone(
            journey.quality_fixed_at,
        )

    def test_leaving_with_review_without_quality_keeps_fix_empty(self):
        journey = TraineeJourney.objects.create(
            user=self.user,
            entry_type=EntryType.NEW_HIRE,
            probation_start_date=(
                date.today() - timedelta(days=20)
            ),
            current_stage=self.stage,
            stage_started_at=(
                date.today() - timedelta(days=7)
            ),
        )

        WeeklyMetric.objects.create(
            journey=journey,
            week_number=1,
            speed_hours=Decimal("5.0"),
            quality_percent=None,
        )

        journey.move_to_stage(
            self.optional_stage,
            transition_date=date.today(),
        )

        journey.refresh_from_db()

        self.assertIsNone(
            journey.fixed_quality_percent,
        )
        self.assertIsNone(
            journey.quality_fixed_at,
        )


class ProbationDurationTests(TestCase):
    def setUp(self):
        self.stage = TraineeStage.objects.create(
            name="В тикетах с проверками",
            slug="with-review",
            order=7,
            min_days=15,
            max_days=20,
            progress_weight_percent=35,
            group=StageGroup.WITH_REVIEW,
        )
        self.user = User.objects.create_user(username="user1", password="test")

    def test_new_hire_probation_is_90_days(self):
        journey = TraineeJourney.objects.create(
            user=self.user,
            entry_type=EntryType.NEW_HIRE,
            probation_start_date=date.today() - timedelta(days=10),
            current_stage=self.stage,
            stage_started_at=date.today(),
        )
        self.assertEqual(journey.probation_days_total, 90)
        self.assertEqual(journey.days_left_until_probation_end, 80)

    def test_internal_transfer_probation_is_30_days(self):
        journey = TraineeJourney.objects.create(
            user=self.user,
            entry_type=EntryType.INTERNAL_TRANSFER,
            probation_start_date=date.today() - timedelta(days=10),
            current_stage=self.stage,
            stage_started_at=date.today(),
        )
        self.assertEqual(journey.probation_days_total, 30)
        self.assertEqual(journey.days_left_until_probation_end, 20)


class InternalTransferProgressTests(TestCase):
    def setUp(self):
        self.first_day = TraineeStage.objects.create(
            name="Первый день",
            slug="first-day",
            order=1,
            progress_weight_percent=3,
            group=StageGroup.TEACHBASE,
            applies_to_new_hire=True,
            applies_to_internal_transfer=False,
        )
        self.with_review = TraineeStage.objects.create(
            name="В тикетах с проверками",
            slug="with-review",
            order=7,
            min_days=15,
            max_days=20,
            progress_weight_percent=35,
            group=StageGroup.WITH_REVIEW,
            applies_to_new_hire=True,
            applies_to_internal_transfer=True,
        )
        self.user = User.objects.create_user(username="internal1", password="test")

    def test_internal_transfer_progress_does_not_inherit_teachbase_weight(self):
        journey = TraineeJourney.objects.create(
            user=self.user,
            entry_type=EntryType.INTERNAL_TRANSFER,
            probation_start_date=date.today(),
            current_stage=self.with_review,
            stage_started_at=date.today(),
        )
        self.assertEqual(journey.progress_percent, 0)

    def test_cannot_assign_teachbase_stage_to_internal_transfer(self):
        journey = TraineeJourney(
            user=self.user,
            entry_type=EntryType.INTERNAL_TRANSFER,
            probation_start_date=date.today(),
            current_stage=self.first_day,
            stage_started_at=date.today(),
        )
        with self.assertRaises(ValidationError):
            journey.full_clean()

    def test_move_to_stage_rejects_inapplicable_stage(self):
        journey = TraineeJourney.objects.create(
            user=self.user,
            entry_type=EntryType.INTERNAL_TRANSFER,
            probation_start_date=date.today(),
            current_stage=self.with_review,
            stage_started_at=date.today(),
        )
        with self.assertRaises(ValidationError):
            journey.move_to_stage(self.first_day)
