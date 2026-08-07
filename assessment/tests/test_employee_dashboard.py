from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

from assessment.constants import (
    ExamAttemptStatus,
    SupportLevel,
)
from assessment.models import (
    AssessmentCampaign,
    ExamAssignment,
    ExamAttempt,
    ExamBlueprint,
    SupportProfile,
)


class AssessmentEmployeeDashboardTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="employee-dashboard",
            password="test-password",
            first_name="Иван",
        )

        self.profile = SupportProfile.objects.create(
            user=self.user,
            level=SupportLevel.L1,
        )

        self.blueprint = ExamBlueprint.objects.create(
            name="Тестовый L1",
            slug="employee-dashboard-blueprint",
            level=SupportLevel.L1,
            is_active=True,
        )

        self.campaign = AssessmentCampaign.objects.create(
            name="Плановая оценка L1",
            slug="employee-dashboard-campaign",
            blueprint=self.blueprint,
            is_active=True,
        )

        self.assignment = ExamAssignment.objects.create(
            campaign=self.campaign,
            employee=self.profile,
        )

        self.client.force_login(
            self.user
        )

    def test_dashboard_is_available(self):
        response = self.client.get(
            reverse(
                "assessment:dashboard"
            )
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        self.assertContains(
            response,
            "Плановая оценка L1",
        )

    def test_inactive_assignment_is_hidden(self):
        self.assignment.is_active = False

        self.assignment.save(
            update_fields=["is_active"]
        )

        response = self.client.get(
            reverse(
                "assessment:dashboard"
            )
        )

        self.assertNotContains(
            response,
            "Плановая оценка L1",
        )

    def test_user_without_profile_is_forbidden(self):
        another_user = User.objects.create_user(
            username="without-profile",
        )

        self.client.force_login(
            another_user
        )

        response = self.client.get(
            reverse(
                "assessment:dashboard"
            )
        )

        self.assertEqual(
            response.status_code,
            403,
        )

    @patch(
        "assessment.views.start_exam_attempt"
    )
    def test_start_redirects_to_attempt(
        self,
        start_exam_attempt_mock,
    ):
        attempt = ExamAttempt.objects.create(
            assignment=self.assignment,
            attempt_number=1,
            status=(
                ExamAttemptStatus.IN_PROGRESS
            ),
            selection_seed="ui-test",
            campaign_name=self.campaign.name,
            blueprint_name=self.blueprint.name,
            level=SupportLevel.L1,
            pass_percentage=85,
            allow_back_navigation=False,
            shuffle_questions=True,
            shuffle_answer_options=True,
        )

        start_exam_attempt_mock.return_value = (
            attempt,
            True,
        )

        response = self.client.post(
            reverse(
                "assessment:start_assignment",
                args=[
                    self.assignment.pk,
                ],
            )
        )

        self.assertRedirects(
            response,
            reverse(
                "assessment:attempt_overview",
                args=[
                    attempt.pk,
                ],
            ),
        )

    @patch(
        "assessment.views.start_exam_attempt"
    )
    def test_start_error_returns_to_dashboard(
        self,
        start_exam_attempt_mock,
    ):
        start_exam_attempt_mock.side_effect = (
            ValidationError(
                "Тест пока недоступен."
            )
        )

        response = self.client.post(
            reverse(
                "assessment:start_assignment",
                args=[
                    self.assignment.pk,
                ],
            )
        )

        self.assertRedirects(
            response,
            reverse(
                "assessment:dashboard"
            ),
        )
