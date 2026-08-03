from django.contrib import admin
from django.test import SimpleTestCase

from traineediary.admin import (
    StageHistoryInline,
    WeeklyMetricInline,
)
from traineediary.models import (
    StageHistory,
    TraineeJourney,
    WeeklyMetric,
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

    def test_workflow_fields_are_read_only(
        self,
    ):
        protected_fields = {
            "user",
            "entry_type",
            "probation_start_date",
            "current_stage",
            "stage_started_at",
            "fixed_quality_percent",
            "quality_fixed_at",
            "completion_status",
            "completed_at",
            "completion_comment",
            "completed_by",
        }

        self.assertTrue(
            protected_fields.issubset(
                set(
                    self.model_admin
                    .readonly_fields
                ),
            ),
        )

    def test_mentor_fields_remain_editable(
        self,
    ):
        self.assertNotIn(
            "comment",
            self.model_admin.readonly_fields,
        )

        self.assertNotIn(
            "manual_risk_override",
            self.model_admin.readonly_fields,
        )

    def test_journey_cannot_be_added_in_admin(
        self,
    ):
        self.assertFalse(
            self.model_admin
            .has_add_permission(
                request=None,
            ),
        )

    def test_journey_cannot_be_deleted_in_admin(
        self,
    ):
        self.assertFalse(
            self.model_admin
            .has_delete_permission(
                request=None,
                obj=None,
            ),
        )

    def test_diary_link_is_visible(
        self,
    ):
        self.assertIn(
            "diary_link",
            self.model_admin.list_display,
        )

        self.assertIn(
            "diary_link",
            self.model_admin.readonly_fields,
        )


class StageHistoryAdminTests(
    SimpleTestCase,
):
    def setUp(self):
        self.model_admin = (
            admin.site._registry[
                StageHistory
            ]
        )

    def test_history_fields_are_read_only(
        self,
    ):
        protected_fields = {
            "journey",
            "stage",
            "started_at",
            "ended_at",
            "changed_by",
            "note",
        }

        self.assertTrue(
            protected_fields.issubset(
                set(
                    self.model_admin
                    .readonly_fields
                ),
            ),
        )

    def test_history_cannot_be_added(
        self,
    ):
        self.assertFalse(
            self.model_admin
            .has_add_permission(
                request=None,
            ),
        )

    def test_history_cannot_be_deleted(
        self,
    ):
        self.assertFalse(
            self.model_admin
            .has_delete_permission(
                request=None,
                obj=None,
            ),
        )


class WeeklyMetricAdminTests(
    SimpleTestCase,
):
    def setUp(self):
        self.model_admin = (
            admin.site._registry[
                WeeklyMetric
            ]
        )

    def test_metric_fields_are_read_only(
        self,
    ):
        protected_fields = {
            "journey",
            "week_number",
            "week_start_date",
            "speed_hours",
            "quality_percent",
            "mentor_comment",
            "next_week_goal",
        }

        self.assertTrue(
            protected_fields.issubset(
                set(
                    self.model_admin
                    .readonly_fields
                ),
            ),
        )

    def test_metric_cannot_be_added(
        self,
    ):
        self.assertFalse(
            self.model_admin
            .has_add_permission(
                request=None,
            ),
        )

    def test_metric_cannot_be_deleted(
        self,
    ):
        self.assertFalse(
            self.model_admin
            .has_delete_permission(
                request=None,
                obj=None,
            ),
        )


class TraineeInlineProtectionTests(
    SimpleTestCase,
):
    def test_stage_history_inline_is_read_only(
        self,
    ):
        inline = StageHistoryInline(
            TraineeJourney,
            admin.site,
        )

        self.assertFalse(
            inline.has_add_permission(
                request=None,
                obj=None,
            ),
        )

        self.assertFalse(
            inline.has_delete_permission(
                request=None,
                obj=None,
            ),
        )

        self.assertFalse(
            inline.can_delete,
        )

    def test_weekly_metric_inline_is_read_only(
        self,
    ):
        inline = WeeklyMetricInline(
            TraineeJourney,
            admin.site,
        )

        self.assertFalse(
            inline.has_add_permission(
                request=None,
                obj=None,
            ),
        )

        self.assertFalse(
            inline.has_delete_permission(
                request=None,
                obj=None,
            ),
        )

        self.assertFalse(
            inline.can_delete,
        )
