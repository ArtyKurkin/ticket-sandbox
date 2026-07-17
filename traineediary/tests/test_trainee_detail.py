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
