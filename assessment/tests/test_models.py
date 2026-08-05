from django.contrib.auth.models import User
from django.test import TestCase

from assessment.constants import SupportLevel
from assessment.models import SupportProfile


class SupportProfileModelTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="support-user",
            first_name="Иван",
            last_name="Иванов",
        )

    def test_profile_supports_all_levels(self):
        self.assertEqual(
            set(SupportLevel.values),
            {
                SupportLevel.L1,
                SupportLevel.L2,
                SupportLevel.PRIME,
            },
        )

    def test_profile_is_active_by_default(self):
        profile = SupportProfile.objects.create(
            user=self.user,
            level=SupportLevel.L1,
        )

        self.assertTrue(profile.is_active)

    def test_profile_is_available_from_user(self):
        profile = SupportProfile.objects.create(
            user=self.user,
            level=SupportLevel.L2,
        )

        self.assertEqual(
            self.user.support_profile,
            profile,
        )

    def test_profile_string_contains_employee_and_level(self):
        profile = SupportProfile.objects.create(
            user=self.user,
            level=SupportLevel.PRIME,
        )

        self.assertEqual(
            str(profile),
            "Иван Иванов — Prime",
        )
