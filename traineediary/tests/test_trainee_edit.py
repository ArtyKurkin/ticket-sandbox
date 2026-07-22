from datetime import date, timedelta

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from traineediary.models import (
    EntryType,
    StageGroup,
    TraineeJourney,
    TraineeStage,
)


class TraineeEditViewTests(TestCase):
    def setUp(self):
        self.staff_user = User.objects.create_user(
            username="edit-mentor",
            password="test",
            is_staff=True,
        )

        self.trainee_user = User.objects.create_user(
            username="edit-trainee",
            password="test",
            first_name="Иван",
            last_name="Петров",
        )

        self.stage = TraineeStage.objects.create(
            name="В тикетах с проверками",
            slug="edit-with-review",
            order=7,
            min_days=15,
            max_days=20,
            progress_weight_percent=35,
            group=StageGroup.WITH_REVIEW,
            applies_to_new_hire=True,
            applies_to_internal_transfer=True,
        )

        self.probation_start_date = (
            date.today()
            - timedelta(days=10)
        )

        self.journey = (
            TraineeJourney.objects.create(
                user=self.trainee_user,
                entry_type=EntryType.NEW_HIRE,
                probation_start_date=(
                    self.probation_start_date
                ),
                current_stage=self.stage,
                stage_started_at=(
                    self.probation_start_date
                ),
                comment="Первоначальный комментарий",
            )
        )

        self.url = reverse(
            "traineediary:edit_trainee",
            args=[self.journey.id],
        )

    def login_staff(self):
        self.client.login(
            username="edit-mentor",
            password="test",
        )

    def test_staff_can_open_edit_page(self):
        self.login_staff()

        response = self.client.get(
            self.url,
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        self.assertContains(
            response,
            "Редактировать",
        )

        self.assertContains(
            response,
            "edit-trainee",
        )

    def test_non_staff_gets_403(self):
        self.client.login(
            username="edit-trainee",
            password="test",
        )

        response = self.client.get(
            self.url,
        )

        self.assertEqual(
            response.status_code,
            403,
        )

    def test_edit_updates_user_and_journey(self):
        self.login_staff()

        response = self.client.post(
            self.url,
            {
                "first_name": "Иван",
                "last_name": "Сидоров",
                "entry_type": (
                    EntryType.INTERNAL_TRANSFER
                ),
                "probation_start_date": (
                    self.probation_start_date
                    .isoformat()
                ),
                "comment": (
                    "Обновлённый комментарий"
                ),
                "is_active": "on",
            },
        )

        self.assertRedirects(
            response,
            reverse(
                "traineediary:trainee_detail",
                args=[self.journey.id],
            ),
        )

        self.trainee_user.refresh_from_db()
        self.journey.refresh_from_db()

        self.assertEqual(
            self.trainee_user.last_name,
            "Сидоров",
        )

        self.assertTrue(
            self.trainee_user.is_active,
        )

        self.assertEqual(
            self.journey.entry_type,
            EntryType.INTERNAL_TRANSFER,
        )

        self.assertEqual(
            self.journey.comment,
            "Обновлённый комментарий",
        )

        self.assertEqual(
            self.trainee_user.username,
            "edit-trainee",
        )

    def test_edit_can_deactivate_account(self):
        self.login_staff()

        response = self.client.post(
            self.url,
            {
                "first_name": "Иван",
                "last_name": "Петров",
                "entry_type": (
                    EntryType.NEW_HIRE
                ),
                "probation_start_date": (
                    self.probation_start_date
                    .isoformat()
                ),
                "comment": "",
            },
        )

        self.assertRedirects(
            response,
            reverse(
                "traineediary:trainee_detail",
                args=[self.journey.id],
            ),
        )

        self.trainee_user.refresh_from_db()

        self.assertFalse(
            self.trainee_user.is_active,
        )

    def test_changing_initial_date_updates_stage_history(self):
        self.login_staff()

        new_start_date = (
            self.probation_start_date
            + timedelta(days=2)
        )

        response = self.client.post(
            self.url,
            {
                "first_name": "Иван",
                "last_name": "Петров",
                "entry_type": (
                    EntryType.NEW_HIRE
                ),
                "probation_start_date": (
                    new_start_date.isoformat()
                ),
                "comment": "",
                "is_active": "on",
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

        history_entry = (
            self.journey.stage_history.get()
        )

        self.assertEqual(
            self.journey.probation_start_date,
            new_start_date,
        )

        self.assertEqual(
            self.journey.stage_started_at,
            new_start_date,
        )

        self.assertEqual(
            history_entry.started_at,
            new_start_date,
        )

    def test_rejects_entry_type_incompatible_with_stage(self):
        teachbase_stage = (
            TraineeStage.objects.create(
                name="Teachbase",
                slug="edit-teachbase",
                order=1,
                progress_weight_percent=10,
                group=StageGroup.TEACHBASE,
                applies_to_new_hire=True,
                applies_to_internal_transfer=False,
            )
        )

        second_user = User.objects.create_user(
            username="edit-teachbase-trainee",
            password="test",
        )

        journey = TraineeJourney.objects.create(
            user=second_user,
            entry_type=EntryType.NEW_HIRE,
            probation_start_date=(
                self.probation_start_date
            ),
            current_stage=teachbase_stage,
            stage_started_at=(
                self.probation_start_date
            ),
        )

        self.login_staff()

        response = self.client.post(
            reverse(
                "traineediary:edit_trainee",
                args=[journey.id],
            ),
            {
                "first_name": "Анна",
                "last_name": "Смирнова",
                "entry_type": (
                    EntryType.INTERNAL_TRANSFER
                ),
                "probation_start_date": (
                    self.probation_start_date
                    .isoformat()
                ),
                "comment": "",
                "is_active": "on",
            },
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        self.assertContains(
            response,
            (
                "Текущий этап не применим "
                "к выбранному типу входа."
            ),
        )

        journey.refresh_from_db()

        self.assertEqual(
            journey.entry_type,
            EntryType.NEW_HIRE,
        )
