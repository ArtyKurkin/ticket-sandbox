
import json

from datetime import date, timedelta
from unittest.mock import patch

from django.urls import reverse
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.test import TestCase

from .models import (
    EntryType,
    RiskLevel,
    StageGroup,
    StageHistory,
    TraineeJourney,
    TraineeStage,
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


class TraineeKanbanAndCreationTests(TestCase):
    def setUp(self):
        self.first_day = TraineeStage.objects.create(
            name="Первый день", slug="first-day-kanban", order=1,
            progress_weight_percent=3, group=StageGroup.TEACHBASE,
            applies_to_new_hire=True, applies_to_internal_transfer=False,
        )
        self.with_review = TraineeStage.objects.create(
            name="В тикетах с проверками", slug="with-review-kanban", order=7,
            min_days=15, max_days=20, progress_weight_percent=35,
            group=StageGroup.WITH_REVIEW,
        )
        self.staff_user = User.objects.create_user(
            username="mentor-kanban", password="test", is_staff=True,
        )

    def test_kanban_renders_for_staff(self):
        self.client.login(username="mentor-kanban", password="test")
        response = self.client.get(reverse("traineediary:trainees_kanban"))
        self.assertEqual(response.status_code, 200)

    def test_create_trainee_creates_user_and_journey(self):
        self.client.login(username="mentor-kanban", password="test")
        response = self.client.post(reverse("traineediary:create_trainee"), {
            "first_name": "Иван",
            "last_name": "Петров",
            "username": "ivan.petrov",
            "entry_type": EntryType.NEW_HIRE,
            "probation_start_date": date.today().isoformat(),
            "current_stage": self.first_day.id,
            "comment": "",
        })
        self.assertEqual(response.status_code, 200)
        self.assertTrue(User.objects.filter(username="ivan.petrov").exists())
        self.assertTrue(
            TraineeJourney.objects.filter(user__username="ivan.petrov").exists(),
        )

    def test_create_trainee_rejects_inapplicable_stage_for_internal_transfer(self):
        self.client.login(username="mentor-kanban", password="test")
        response = self.client.post(reverse("traineediary:create_trainee"), {
            "first_name": "Мария",
            "last_name": "Смирнова",
            "username": "maria.smirnova",
            "entry_type": EntryType.INTERNAL_TRANSFER,
            "probation_start_date": date.today().isoformat(),
            "current_stage": self.first_day.id,  # неприменим для internal_transfer
            "comment": "",
        })
        self.assertEqual(response.status_code, 200)  # форма не сохранилась, показала ошибку
        self.assertFalse(User.objects.filter(username="maria.smirnova").exists())

    def test_move_trainee_stage_via_ajax(self):
        user = User.objects.create_user(username="trainee-move", password="test")
        journey = TraineeJourney.objects.create(
            user=user, entry_type=EntryType.NEW_HIRE,
            probation_start_date=date.today(),
            current_stage=self.first_day, stage_started_at=date.today(),
        )
        new_stage = TraineeStage.objects.create(
            name="VDS", slug="vds-kanban", order=2,
            progress_weight_percent=15, group=StageGroup.TEACHBASE,
            applies_to_new_hire=True, applies_to_internal_transfer=False,
        )

        self.client.login(username="mentor-kanban", password="test")
        response = self.client.post(
            reverse("traineediary:move_trainee_stage", args=[journey.id]),
            data=json.dumps({"stage_id": new_stage.id}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        journey.refresh_from_db()
        self.assertEqual(journey.current_stage, new_stage)

    def test_move_trainee_stage_rejects_inapplicable_stage(self):
        user = User.objects.create_user(username="trainee-move2", password="test")
        journey = TraineeJourney.objects.create(
            user=user, entry_type=EntryType.INTERNAL_TRANSFER,
            probation_start_date=date.today(),
            current_stage=self.with_review, stage_started_at=date.today(),
        )

        self.client.login(username="mentor-kanban", password="test")
        response = self.client.post(
            reverse("traineediary:move_trainee_stage", args=[journey.id]),
            data=json.dumps({"stage_id": self.first_day.id}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        journey.refresh_from_db()
        self.assertEqual(journey.current_stage, self.with_review)
