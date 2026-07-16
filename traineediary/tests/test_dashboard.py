from datetime import date

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from traineediary.models import (
    EntryType,
    StageGroup,
    TraineeJourney,
    TraineeStage,
)


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
