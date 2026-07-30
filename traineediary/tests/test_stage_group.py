from django.test import SimpleTestCase

from traineediary.models import StageGroup


class StageGroupCompatibilityTests(
    SimpleTestCase,
):
    def test_sandbox_l1_keeps_existing_database_value(
        self,
    ):
        self.assertEqual(
            StageGroup.SANDBOX_L1.value,
            "sandbox_candidate",
        )
