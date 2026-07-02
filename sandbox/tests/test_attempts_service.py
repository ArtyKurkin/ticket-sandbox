from unittest.mock import patch

from django.db import IntegrityError

from sandbox.models import TaskAttempt, TraineeProfile
from sandbox.services.attempts import get_current_attempt

from .base import SandboxTestCase


class GetCurrentAttemptTests(SandboxTestCase):
    def setUp(self):
        self.queue = self.create_queue(
            slug="l1",
            name="ОТП Cloud L1",
            order=1,
            required_level=TraineeProfile.Level.L1,
        )
        self.task = self.create_task(
            queue=self.queue,
            slug="nginx-not-starting",
            order=1,
        )
        self.user = self.create_user(username="trainee")

    def test_get_current_attempt_returns_concurrently_created_attempt_after_integrity_error(self):
        original_create = TaskAttempt.objects.create

        def create_attempt_then_raise_integrity_error(*args, **kwargs):
            original_create(*args, **kwargs)
            raise IntegrityError("duplicate current attempt")

        with patch(
            "sandbox.services.attempts.TaskAttempt.objects.create",
            side_effect=create_attempt_then_raise_integrity_error,
        ):
            attempt = get_current_attempt(
                user=self.user,
                task=self.task,
            )

        self.assertEqual(attempt.user, self.user)
        self.assertEqual(attempt.task, self.task)
        self.assertEqual(attempt.attempt_number, 1)
        self.assertTrue(attempt.is_current)

        self.assertEqual(
            TaskAttempt.objects.filter(
                user=self.user,
                task=self.task,
                is_current=True,
            ).count(),
            1,
        )
