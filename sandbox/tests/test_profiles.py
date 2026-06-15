from django.contrib.auth.models import User

from sandbox.models import TraineeProfile

from .base import SandboxTestCase


class TraineeProfileTests(SandboxTestCase):
    def test_profile_created_automatically_for_new_user(self):
        user = User.objects.create_user(
            username="new-user",
            password="test-password",
        )

        self.assertTrue(hasattr(user, "trainee_profile"))
        self.assertEqual(
            user.trainee_profile.level,
            TraineeProfile.Level.CANDIDATE,
        )
