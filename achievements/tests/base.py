from datetime import timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone

from achievements.models import AchievementDefinition
from achievements.services.catalog import seed_catalog
from achievements.services.evaluators import evaluate
from achievements.services.grants import grant
from traineediary.models import EntryType, StageGroup, TraineeJourney, TraineeStage, WeeklyMetric


class AchievementTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        seed_catalog()
        cls.user = User.objects.create_user("award-user")
        cls.other = User.objects.create_user("award-other")
        cls.staff = User.objects.create_user("award-staff", is_staff=True)
        cls.today = timezone.localdate()
        cls.start = cls.today - timedelta(days=100)
        cls.stages = {}
        for order, group in enumerate(StageGroup.values, 101):
            cls.stages[group] = TraineeStage.objects.create(slug=f"award-{group}", name=group, group=group, order=order)
        cls.journey = TraineeJourney.objects.create(user=cls.user, entry_type=EntryType.NEW_HIRE,
            probation_start_date=cls.start, current_stage=cls.stages[StageGroup.WITH_REVIEW], stage_started_at=cls.start)

    def definition(self, code="independent_speed"):
        return AchievementDefinition.objects.get(code=code)

    def evaluate(self, code):
        return evaluate(user_id=self.user.pk, definition=self.definition(code))

    def award(self, tier="bronze", code="independent_speed", operation=None, manual=False, **kwargs):
        return grant(user_id=self.user.pk, definition_id=self.definition(code).pk,
            tier_code=tier, evidence={"fixture_value": tier}, occurred_at=timezone.now(),
            source_type="manual" if manual else "test", source_ref=operation or tier,
            operation_id=operation or tier, actor=self.staff if manual else None,
            reason="Проверенное ручное основание" if manual else "", **kwargs)

    def metric(self, quality=96, speed="10.1", start=None, number=1):
        return WeeklyMetric.objects.create(journey=self.journey, week_number=number,
            week_start_date=start or self.start, quality_percent=quality,
            speed_hours=Decimal(speed) if speed is not None else None)

    def move(self, group, date=None, actor=True):
        self.journey.move_to_stage(self.stages[group], changed_by=self.staff if actor else None,
                                  transition_date=date or self.start + timedelta(days=21))
