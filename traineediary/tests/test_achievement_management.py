from datetime import timedelta
from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from achievements.models import AchievementEvent, UserAchievement
from traineediary.models import TraineeJourney, TraineeStage, StageGroup


class DiaryAchievementTabTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.staff = User.objects.create_user("diary-awards-staff", is_staff=True)
        cls.user = User.objects.create_user("diary-awards-user")
        stage = TraineeStage.objects.create(name="Review", slug="diary-awards-review", order=50, group=StageGroup.WITH_REVIEW)
        start = timezone.localdate() - timedelta(days=10)
        cls.journey = TraineeJourney.objects.create(user=cls.user, entry_type="new_hire", probation_start_date=start, stage_started_at=start, current_stage=stage)

    def test_staff_tabs_bootstrap_and_other_sections_preserved(self):
        self.client.force_login(self.staff)
        url = reverse("traineediary:trainee_detail", args=[self.journey.pk])
        before = list(self.journey.stage_history.values())
        adaptation = self.client.get(url)
        achievements = self.client.get(url, {"tab": "achievements"})
        self.assertContains(achievements, 'data-diary-tab="achievements"')
        self.assertContains(achievements, 'data-da-grant')
        self.assertTrue(achievements.context["achievement_management"]["canManage"])
        self.assertEqual(achievements.context["achievement_management"]["userId"], self.user.pk)
        self.assertEqual(achievements.context["achievement_management"]["collectionUrl"], reverse("achievement_api:user", args=[self.user.pk]))
        for key in ["assessment", "progress_percent", "speed_chart", "quality_chart", "weekly_metrics_summary", "history_rows"]:
            if key != "assessment":
                self.assertEqual(adaptation.context[key], achievements.context[key])
        for text in ["Основная информация", "Комментарий наставника", "Динамика метрик", "Этапы обучения", "История этапов"]:
            self.assertContains(adaptation, text)
            self.assertContains(achievements, text)
        self.assertEqual(before, list(self.journey.stage_history.values()))
        self.assertFalse(UserAchievement.objects.exists())
        self.assertFalse(AchievementEvent.objects.exists())

    def test_entire_card_and_tab_staff_only(self):
        url = reverse("traineediary:trainee_detail", args=[self.journey.pk]) + "?tab=achievements"
        self.assertEqual(self.client.get(url).status_code, 302)
        self.client.force_login(self.user)
        response = self.client.get(url)
        self.assertEqual(response.status_code, 403)
        self.assertNotContains(response, 'data-da-grant', status_code=403)
