from datetime import timedelta

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone

from assessment.constants import SupportLevel
from assessment.models import (
    AssessmentCampaign,
    ExamAssignment,
    ExamBlueprint,
    SupportProfile,
)


class AssessmentCampaignModelTests(TestCase):
    def setUp(self):
        self.blueprint = ExamBlueprint.objects.create(
            name="Тестовый шаблон кампании",
            slug="test-campaign-blueprint",
            level=SupportLevel.L1,
        )

    def test_campaign_string_contains_name(self):
        campaign = AssessmentCampaign.objects.create(
            name="Плановая оценка L1",
            slug="test-planned-l1",
            blueprint=self.blueprint,
        )

        self.assertEqual(
            str(campaign),
            "Плановая оценка L1",
        )

    def test_campaign_is_inactive_by_default(self):
        campaign = AssessmentCampaign.objects.create(
            name="Неактивная кампания",
            slug="test-inactive-campaign",
            blueprint=self.blueprint,
        )

        self.assertFalse(
            campaign.is_active,
        )

    def test_campaign_end_must_be_after_start(self):
        opens_at = timezone.now()

        campaign = AssessmentCampaign(
            name="Кампания с ошибкой дат",
            slug="test-invalid-dates",
            blueprint=self.blueprint,
            opens_at=opens_at,
            closes_at=opens_at - timedelta(hours=1),
        )

        with self.assertRaises(ValidationError):
            campaign.full_clean()


class ExamAssignmentModelTests(TestCase):
    def setUp(self):
        self.blueprint = ExamBlueprint.objects.create(
            name="Тестовый шаблон назначения",
            slug="test-assignment-blueprint",
            level=SupportLevel.L1,
        )

        self.campaign = AssessmentCampaign.objects.create(
            name="Тестовая кампания",
            slug="test-assignment-campaign",
            blueprint=self.blueprint,
        )

        self.user = User.objects.create_user(
            username="assessment-employee",
            first_name="Иван",
            last_name="Иванов",
        )

        self.employee = SupportProfile.objects.create(
            user=self.user,
            level=SupportLevel.L1,
        )

    def test_assignment_has_one_attempt_by_default(self):
        assignment = ExamAssignment.objects.create(
            campaign=self.campaign,
            employee=self.employee,
        )

        self.assertEqual(
            assignment.attempt_limit,
            1,
        )

    def test_assignment_string_contains_campaign_and_employee(
        self,
    ):
        assignment = ExamAssignment.objects.create(
            campaign=self.campaign,
            employee=self.employee,
        )

        self.assertEqual(
            str(assignment),
            (
                "Тестовая кампания — "
                "Иван Иванов"
            ),
        )

    def test_employee_can_be_assigned_only_once_per_campaign(
        self,
    ):
        ExamAssignment.objects.create(
            campaign=self.campaign,
            employee=self.employee,
        )

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                ExamAssignment.objects.create(
                    campaign=self.campaign,
                    employee=self.employee,
                )

    def test_employee_level_must_match_blueprint_level(
        self,
    ):
        self.employee.level = SupportLevel.L2
        self.employee.save(
            update_fields=["level"]
        )

        assignment = ExamAssignment(
            campaign=self.campaign,
            employee=self.employee,
        )

        with self.assertRaises(ValidationError):
            assignment.full_clean()

    def test_inactive_employee_cannot_receive_new_assignment(
        self,
    ):
        self.employee.is_active = False
        self.employee.save(
            update_fields=["is_active"]
        )

        assignment = ExamAssignment(
            campaign=self.campaign,
            employee=self.employee,
        )

        with self.assertRaises(ValidationError):
            assignment.full_clean()

    def test_attempt_limit_must_be_positive(self):
        assignment = ExamAssignment(
            campaign=self.campaign,
            employee=self.employee,
            attempt_limit=0,
        )

        with self.assertRaises(ValidationError):
            assignment.full_clean()
