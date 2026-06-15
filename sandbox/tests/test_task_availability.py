from django.urls import reverse

from sandbox.models import TaskAttempt, TraineeProfile

from .base import SandboxTestCase


class TaskAvailabilityTests(SandboxTestCase):
    def setUp(self):
        self.queue = self.create_queue(
            slug="l1",
            name="ОТП Cloud L1",
            order=1,
            required_level=TraineeProfile.Level.L1,
        )

        self.first_task = self.create_task(
            queue=self.queue,
            slug="first-task",
            order=1,
        )

        self.second_task = self.create_task(
            queue=self.queue,
            slug="second-task",
            order=2,
        )

        self.user = self.create_user(
            username="trainee",
            level=TraineeProfile.Level.L1,
        )

    def test_first_task_is_available(self):
        attempt = TaskAttempt.objects.create(
            user=self.user,
            task=self.first_task,
        )

        self.assertTrue(attempt.is_available)

    def test_second_task_is_locked_until_previous_task_passed(self):
        TaskAttempt.objects.create(
            user=self.user,
            task=self.first_task,
            status=TaskAttempt.Status.NEW,
        )

        second_attempt = TaskAttempt.objects.create(
            user=self.user,
            task=self.second_task,
        )

        self.assertFalse(second_attempt.is_available)

    def test_second_task_is_available_after_previous_task_passed(self):
        TaskAttempt.objects.create(
            user=self.user,
            task=self.first_task,
            status=TaskAttempt.Status.PASSED,
        )

        second_attempt = TaskAttempt.objects.create(
            user=self.user,
            task=self.second_task,
        )

        self.assertTrue(second_attempt.is_available)


class DashboardFilteringTests(SandboxTestCase):
    def setUp(self):
        self.queue = self.create_queue(
            slug="l1",
            name="ОТП Cloud L1",
            order=1,
            required_level=TraineeProfile.Level.L1,
        )

        self.active_task = self.create_task(
            queue=self.queue,
            slug="active-task",
            order=1,
        )

        self.inactive_task = self.create_task(
            queue=self.queue,
            slug="inactive-task",
            order=2,
        )
        self.inactive_task.is_active = False
        self.inactive_task.save()

        self.user = self.create_user(
            username="dashboard-user",
            level=TraineeProfile.Level.L1,
        )

    def test_dashboard_creates_attempts_only_for_active_tasks(self):
        self.client.login(
            username="dashboard-user",
            password="test-password",
        )

        response = self.client.get(reverse("sandbox:dashboard"))

        self.assertEqual(response.status_code, 200)

        attempts = TaskAttempt.objects.filter(user=self.user)

        self.assertTrue(
            attempts.filter(task=self.active_task).exists()
        )

        self.assertFalse(
            attempts.filter(task=self.inactive_task).exists()
        )
