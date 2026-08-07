from django.contrib import admin
from django.test import SimpleTestCase

from assessment.admin import ExamAssignmentInline
from assessment.models import (
    AssessmentCampaign,
    ExamAssignment,
)


class AssessmentCampaignAdminTests(SimpleTestCase):
    def test_campaign_is_registered(self):
        self.assertIn(
            AssessmentCampaign,
            admin.site._registry,
        )

    def test_assignment_is_registered(self):
        self.assertIn(
            ExamAssignment,
            admin.site._registry,
        )

    def test_campaign_contains_assignment_inline(self):
        campaign_admin = admin.site._registry[
            AssessmentCampaign
        ]

        self.assertIn(
            ExamAssignmentInline,
            campaign_admin.inlines,
        )

    def test_assignment_can_be_filtered_by_campaign(self):
        assignment_admin = admin.site._registry[
            ExamAssignment
        ]

        self.assertIn(
            "campaign",
            assignment_admin.list_filter,
        )
