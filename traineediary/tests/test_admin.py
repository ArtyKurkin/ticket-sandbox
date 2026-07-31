from django.contrib import admin
from django.test import SimpleTestCase

from traineediary.models import (
    TraineeJourney,
)


class TraineeJourneyAdminTests(
    SimpleTestCase,
):
    def setUp(self):
        self.model_admin = (
            admin.site._registry[
                TraineeJourney
            ]
        )

    def test_completion_fields_are_visible(
        self,
    ):
        self.assertIn(
            "completion_status",
            self.model_admin.list_display,
        )

        self.assertIn(
            "completed_at",
            self.model_admin.list_display,
        )

    def test_completion_status_is_filterable(
        self,
    ):
        self.assertIn(
            "completion_status",
            self.model_admin.list_filter,
        )

    def test_completion_comment_is_searchable(
        self,
    ):
        self.assertIn(
            "completion_comment",
            self.model_admin.search_fields,
        )

    def test_completion_fields_are_not_list_editable(
        self,
    ):
        self.assertNotIn(
            "completion_status",
            self.model_admin.list_editable,
        )

        self.assertNotIn(
            "completed_at",
            self.model_admin.list_editable,
        )
