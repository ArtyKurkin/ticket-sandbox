from django.urls import reverse
from django.utils import timezone

from sandbox.models import TaskAttempt, TraineeProfile
from sandbox.tests.base import SandboxTestCase


class CheckTaskStatusEndpointTests(SandboxTestCase):
    def setUp(self):
        self.queue = self.create_queue(
            slug="l1",
            name="ОТП Cloud L1",
            order=1,
            required_level=TraineeProfile.Level.L1,
        )
        self.user = self.create_user(
            username="trainee",
            level=TraineeProfile.Level.L1,
        )
        self.task = self.create_task(
            queue=self.queue,
            slug="check-status-task",
            order=1,
        )
        self.attempt = TaskAttempt.objects.create(
            user=self.user,
            task=self.task,
            status=TaskAttempt.Status.IN_PROGRESS,
            check_status=TaskAttempt.CheckStatus.RUNNING,
            check_started_at=timezone.now(),
            last_check_output="Проверка выполняется...",
        )

    def test_owner_can_get_check_status(self):
        self.client.force_login(self.user)

        response = self.client.get(
            reverse(
                "sandbox:check_task_status",
                args=[self.attempt.id],
            )
        )

        self.assertEqual(response.status_code, 200)

        data = response.json()

        self.assertEqual(data["attempt_id"], self.attempt.id)
        self.assertEqual(
            data["attempt_status"],
            TaskAttempt.Status.IN_PROGRESS,
        )
        self.assertEqual(
            data["check_status"],
            TaskAttempt.CheckStatus.RUNNING,
        )
        self.assertTrue(data["is_running"])
        self.assertFalse(data["is_finished"])
        self.assertFalse(data["technical_passed"])
        self.assertEqual(
            data["last_check_output"],
            "Проверка выполняется...",
        )
        self.assertEqual(
            data["redirect_url"],
            reverse(
                "sandbox:task_detail",
                args=[self.attempt.id],
            ),
        )

    def test_anonymous_user_is_redirected_to_login(self):
        response = self.client.get(
            reverse(
                "sandbox:check_task_status",
                args=[self.attempt.id],
            )
        )

        self.assertEqual(response.status_code, 302)

    def test_other_trainee_cannot_get_check_status(self):
        other_user = self.create_user(
            username="other-trainee",
            level=TraineeProfile.Level.L1,
        )

        self.client.force_login(other_user)

        response = self.client.get(
            reverse(
                "sandbox:check_task_status",
                args=[self.attempt.id],
            )
        )

        self.assertEqual(response.status_code, 404)

    def test_staff_user_can_get_check_status(self):
        mentor = self.create_user(
            username="mentor",
            is_staff=True,
        )

        self.client.force_login(mentor)

        response = self.client.get(
            reverse(
                "sandbox:check_task_status",
                args=[self.attempt.id],
            )
        )

        self.assertEqual(response.status_code, 200)

        data = response.json()

        self.assertEqual(data["attempt_id"], self.attempt.id)
        self.assertEqual(
            data["check_status"],
            TaskAttempt.CheckStatus.RUNNING,
        )

    def test_finished_check_status_response(self):
        self.attempt.status = TaskAttempt.Status.PASSED
        self.attempt.check_status = TaskAttempt.CheckStatus.PASSED
        self.attempt.check_finished_at = timezone.now()
        self.attempt.technical_passed_at = self.attempt.check_finished_at
        self.attempt.last_check_output = "OK: проверка пройдена"
        self.attempt.save(
            update_fields=[
                "status",
                "check_status",
                "check_finished_at",
                "technical_passed_at",
                "last_check_output",
            ]
        )

        self.client.force_login(self.user)

        response = self.client.get(
            reverse(
                "sandbox:check_task_status",
                args=[self.attempt.id],
            )
        )

        self.assertEqual(response.status_code, 200)

        data = response.json()

        self.assertFalse(data["is_running"])
        self.assertTrue(data["is_finished"])
        self.assertTrue(data["technical_passed"])
        self.assertEqual(
            data["check_status"],
            TaskAttempt.CheckStatus.PASSED,
        )
        self.assertEqual(
            data["last_check_output"],
            "OK: проверка пройдена",
        )
