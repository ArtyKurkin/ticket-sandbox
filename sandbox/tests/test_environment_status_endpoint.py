from django.urls import reverse
from django.utils import timezone

from sandbox.models import TaskAttempt, TraineeProfile
from sandbox.tests.base import SandboxTestCase


class EnvironmentStatusEndpointTests(SandboxTestCase):
    def setUp(self):
        self.queue = self.create_queue(
            slug="l1",
            name="ОТП Cloud L1",
            order=1,
            required_level=TraineeProfile.Level.L1,
        )
        self.user = self.create_user(
            username="environment-status-trainee",
            level=TraineeProfile.Level.L1,
        )
        self.task = self.create_task(
            queue=self.queue,
            slug="environment-status-task",
            order=1,
        )
        self.attempt = TaskAttempt.objects.create(
            user=self.user,
            task=self.task,
            status=TaskAttempt.Status.NEW,
            environment_status=TaskAttempt.EnvironmentStatus.STARTING,
            environment_started_at=timezone.now(),
            last_check_output="Окружение запускается...",
        )

    def test_owner_can_get_environment_status(self):
        self.client.force_login(self.user)

        response = self.client.get(
            reverse(
                "sandbox:environment_status",
                args=[self.attempt.id],
            )
        )

        self.assertEqual(response.status_code, 200)

        data = response.json()

        self.assertEqual(data["attempt_id"], self.attempt.id)
        self.assertEqual(data["attempt_status"], TaskAttempt.Status.NEW)
        self.assertEqual(
            data["environment_status"],
            TaskAttempt.EnvironmentStatus.STARTING,
        )
        self.assertEqual(data["environment_status_label"], "Запускается")
        self.assertFalse(data["environment_ready"])
        self.assertTrue(data["is_running"])
        self.assertFalse(data["is_finished"])
        self.assertEqual(
            data["last_check_output"],
            "Окружение запускается...",
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
                "sandbox:environment_status",
                args=[self.attempt.id],
            )
        )

        self.assertEqual(response.status_code, 302)

    def test_other_trainee_cannot_get_environment_status(self):
        other_user = self.create_user(
            username="other-environment-trainee",
            level=TraineeProfile.Level.L1,
        )

        self.client.force_login(other_user)

        response = self.client.get(
            reverse(
                "sandbox:environment_status",
                args=[self.attempt.id],
            )
        )

        self.assertEqual(response.status_code, 404)

    def test_staff_user_can_get_environment_status(self):
        mentor = self.create_user(
            username="environment-status-mentor",
            is_staff=True,
        )

        self.client.force_login(mentor)

        response = self.client.get(
            reverse(
                "sandbox:environment_status",
                args=[self.attempt.id],
            )
        )

        self.assertEqual(response.status_code, 200)

        data = response.json()

        self.assertEqual(data["attempt_id"], self.attempt.id)
        self.assertEqual(
            data["environment_status"],
            TaskAttempt.EnvironmentStatus.STARTING,
        )

    def test_ready_environment_status_response(self):
        self.attempt.status = TaskAttempt.Status.IN_PROGRESS
        self.attempt.environment_status = TaskAttempt.EnvironmentStatus.READY
        self.attempt.environment_finished_at = timezone.now()
        self.attempt.container_name = "task-container"
        self.attempt.terminal_url = "/terminal/1/25000/"
        self.attempt.last_check_output = "Контейнер task-container успешно создан."
        self.attempt.save(
            update_fields=[
                "status",
                "environment_status",
                "environment_finished_at",
                "container_name",
                "terminal_url",
                "last_check_output",
            ]
        )

        self.client.force_login(self.user)

        response = self.client.get(
            reverse(
                "sandbox:environment_status",
                args=[self.attempt.id],
            )
        )

        self.assertEqual(response.status_code, 200)

        data = response.json()

        self.assertFalse(data["is_running"])
        self.assertTrue(data["is_finished"])
        self.assertTrue(data["environment_ready"])
        self.assertEqual(
            data["environment_status"],
            TaskAttempt.EnvironmentStatus.READY,
        )
        self.assertEqual(
            data["environment_status_label"],
            "Готово",
        )
        self.assertEqual(
            data["last_check_output"],
            "Контейнер task-container успешно создан.",
        )

    def test_error_environment_status_response(self):
        self.attempt.status = TaskAttempt.Status.FAILED
        self.attempt.environment_status = TaskAttempt.EnvironmentStatus.ERROR
        self.attempt.environment_finished_at = timezone.now()
        self.attempt.last_check_output = (
            "Не удалось запустить окружение задания из-за ошибки Docker API."
        )
        self.attempt.save(
            update_fields=[
                "status",
                "environment_status",
                "environment_finished_at",
                "last_check_output",
            ]
        )

        self.client.force_login(self.user)

        response = self.client.get(
            reverse(
                "sandbox:environment_status",
                args=[self.attempt.id],
            )
        )

        self.assertEqual(response.status_code, 200)

        data = response.json()

        self.assertFalse(data["is_running"])
        self.assertTrue(data["is_finished"])
        self.assertFalse(data["environment_ready"])
        self.assertEqual(
            data["environment_status"],
            TaskAttempt.EnvironmentStatus.ERROR,
        )
        self.assertEqual(
            data["environment_status_label"],
            "Ошибка",
        )
        self.assertIn(
            "Не удалось запустить окружение задания",
            data["last_check_output"],
        )
