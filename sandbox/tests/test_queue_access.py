from django.urls import reverse

from sandbox.models import TaskAttempt, TraineeProfile

from .base import SandboxTestCase


class QueueAccessTests(SandboxTestCase):
    def setUp(self):
        self.candidate_queue = self.create_queue(
            slug="candidate",
            name="Кандидат",
            order=0,
            required_level=TraineeProfile.Level.CANDIDATE,
        )

        self.l1_queue = self.create_queue(
            slug="l1",
            name="ОТП Cloud L1",
            order=1,
            required_level=TraineeProfile.Level.L1,
        )

        self.l2_queue = self.create_queue(
            slug="l2",
            name="L2",
            order=2,
            required_level=TraineeProfile.Level.L2,
        )

        self.candidate_task = self.create_task(
            queue=self.candidate_queue,
            slug="candidate-task",
            order=1,
        )

        self.l1_task = self.create_task(
            queue=self.l1_queue,
            slug="l1-task",
            order=1,
        )

        self.l2_task = self.create_task(
            queue=self.l2_queue,
            slug="l2-task",
            order=1,
        )

    def test_candidate_sees_only_candidate_queue(self):
        user = self.create_user(
            username="candidate-user",
            level=TraineeProfile.Level.CANDIDATE,
        )

        self.client.login(username="candidate-user", password="test-password")

        response = self.client.get(reverse("sandbox:dashboard"))

        self.assertEqual(response.status_code, 200)

        attempts = TaskAttempt.objects.filter(user=user)

        self.assertEqual(attempts.count(), 1)
        self.assertTrue(attempts.filter(task=self.candidate_task).exists())
        self.assertFalse(attempts.filter(task=self.l1_task).exists())
        self.assertFalse(attempts.filter(task=self.l2_task).exists())

    def test_l1_user_sees_only_l1_queue(self):
        user = self.create_user(
            username="l1-user",
            level=TraineeProfile.Level.L1,
        )

        self.client.login(username="l1-user", password="test-password")

        response = self.client.get(reverse("sandbox:dashboard"))

        self.assertEqual(response.status_code, 200)

        attempts = TaskAttempt.objects.filter(user=user)

        self.assertEqual(attempts.count(), 1)
        self.assertTrue(attempts.filter(task=self.l1_task).exists())
        self.assertFalse(attempts.filter(task=self.candidate_task).exists())
        self.assertFalse(attempts.filter(task=self.l2_task).exists())

    def test_l2_user_sees_l1_and_l2_queues(self):
        user = self.create_user(
            username="l2-user",
            level=TraineeProfile.Level.L2,
        )

        self.client.login(username="l2-user", password="test-password")

        response = self.client.get(reverse("sandbox:dashboard"))

        self.assertEqual(response.status_code, 200)

        attempts = TaskAttempt.objects.filter(user=user)

        self.assertEqual(attempts.count(), 2)
        self.assertTrue(attempts.filter(task=self.l1_task).exists())
        self.assertTrue(attempts.filter(task=self.l2_task).exists())
        self.assertFalse(attempts.filter(task=self.candidate_task).exists())

    def test_staff_user_sees_mentor_dashboard(self):
        self.create_user(
            username="mentor",
            level=TraineeProfile.Level.ADMIN,
            is_staff=True,
        )

        self.client.login(username="mentor", password="test-password")

        response = self.client.get(reverse("sandbox:dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "sandbox/mentor_dashboard.html")
