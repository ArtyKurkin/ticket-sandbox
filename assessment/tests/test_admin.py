from django.contrib import admin
from django.test import SimpleTestCase

from assessment.models import SupportProfile


class SupportProfileAdminTests(SimpleTestCase):
    def setUp(self):
        self.model_admin = admin.site._registry[
            SupportProfile
        ]

    def test_profile_is_registered_in_admin(self):
        self.assertIsNotNone(
            self.model_admin,
        )

    def test_level_and_activity_are_editable_from_list(self):
        self.assertIn(
            "level",
            self.model_admin.list_editable,
        )

        self.assertIn(
            "is_active",
            self.model_admin.list_editable,
        )

    def test_employee_fields_are_searchable(self):
        self.assertIn(
            "user__username",
            self.model_admin.search_fields,
        )

        self.assertIn(
            "user__email",
            self.model_admin.search_fields,
        )
