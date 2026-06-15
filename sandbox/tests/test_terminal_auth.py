from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from sandbox.models import Queue, Task, TaskAttempt, TraineeProfile


class TerminalAuthTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="terminal_user",
            password="password",
        )

        profile, _ = TraineeProfile.objects.get_or_create(
            user=self.user,
        )
        profile.level = TraineeProfile.Level.L1
        profile.save(update_fields=["level"])

        self.queue, _ = Queue.objects.get_or_create(
            slug="l1",
            defaults={
                "name": "ОТП Cloud L1",
                "required_level": TraineeProfile.Level.L1,
                "order": 1,
            },
        )

        self.queue.name = "ОТП Cloud L1"
        self.queue.required_level = TraineeProfile.Level.L1
        self.queue.order = 1
        self.queue.is_active = True
        self.queue.save(
            update_fields=[
                "name",
                "required_level",
                "order",
                "is_active",
            ]
        )

        self.task = Task.objects.create(
            queue=self.queue,
            title="Terminal task",
            slug="terminal-task",
            order=1,
            description="Учебная задача с терминалом",
        )

        self.attempt = TaskAttempt.objects.create(
            user=self.user,
            task=self.task,
            status=TaskAttempt.Status.IN_PROGRESS,
            attempt_number=1,
            is_current=True,
            container_name="ticket-sandbox-l1-terminal-task-1",
            terminal_container_name="ticket-sandbox-terminal-l1-terminal-task-1",
            terminal_port=24000,
        )

        self.attempt.terminal_url = f"/terminal/{self.attempt.id}/24000/"
        self.attempt.save(
            update_fields=[
                "terminal_url",
            ]
        )

    def terminal_auth_url(self, attempt=None, port=None):
        attempt = attempt or self.attempt
        port = port or attempt.terminal_port

        return reverse(
            "sandbox:terminal_auth",
            args=[
                attempt.id,
                port,
            ],
        )

    def terminal_auth_from_original_uri_url(self):
        return reverse(
            "sandbox:terminal_auth_from_original_uri"
        )

    def test_terminal_auth_returns_401_for_anonymous_user(self):
        response = self.client.get(
            self.terminal_auth_url()
        )

        self.assertEqual(response.status_code, 401)

    def test_terminal_auth_allows_attempt_owner(self):
        self.client.login(
            username="terminal_user",
            password="password",
        )

        response = self.client.get(
            self.terminal_auth_url()
        )

        self.assertEqual(response.status_code, 204)

    def test_terminal_auth_denies_other_user(self):
        User.objects.create_user(
            username="other_user",
            password="password",
        )

        self.client.login(
            username="other_user",
            password="password",
        )

        response = self.client.get(
            self.terminal_auth_url()
        )

        self.assertEqual(response.status_code, 403)

    def test_terminal_auth_allows_staff_user_for_foreign_attempt(self):
        User.objects.create_user(
            username="mentor",
            password="password",
            is_staff=True,
        )

        self.client.login(
            username="mentor",
            password="password",
        )

        with self.assertLogs("sandbox.terminal", level="WARNING") as logs:
            response = self.client.get(
                self.terminal_auth_url()
            )

        self.assertEqual(response.status_code, 204)

        log_output = "\n".join(logs.output)

        self.assertIn("mentor_terminal_access", log_output)
        self.assertIn(f"trainee_user_id={self.user.id}", log_output)
        self.assertIn(f"attempt_id={self.attempt.id}", log_output)
        self.assertIn("task_slug=terminal-task", log_output)
        self.assertIn("queue_slug=l1", log_output)
        self.assertIn("port=24000", log_output)

    def test_terminal_auth_denies_wrong_port(self):
        self.client.login(
            username="terminal_user",
            password="password",
        )

        response = self.client.get(
            self.terminal_auth_url(port=25000)
        )

        self.assertEqual(response.status_code, 403)

    def test_terminal_auth_denies_missing_terminal_container(self):
        self.attempt.terminal_container_name = ""
        self.attempt.save(
            update_fields=[
                "terminal_container_name",
            ]
        )

        self.client.login(
            username="terminal_user",
            password="password",
        )

        response = self.client.get(
            self.terminal_auth_url()
        )

        self.assertEqual(response.status_code, 403)

    def test_terminal_auth_denies_empty_terminal_url(self):
        self.attempt.terminal_url = ""
        self.attempt.save(
            update_fields=[
                "terminal_url",
            ]
        )

        self.client.login(
            username="terminal_user",
            password="password",
        )

        response = self.client.get(
            self.terminal_auth_url()
        )

        self.assertEqual(response.status_code, 403)

    def test_terminal_auth_denies_technically_locked_attempt(self):
        self.attempt.status = TaskAttempt.Status.PASSED
        self.attempt.save(
            update_fields=[
                "status",
            ]
        )

        self.client.login(
            username="terminal_user",
            password="password",
        )

        response = self.client.get(
            self.terminal_auth_url()
        )

        self.assertEqual(response.status_code, 403)

    def test_terminal_auth_from_original_uri_allows_attempt_owner(self):
        self.client.login(
            username="terminal_user",
            password="password",
        )

        response = self.client.get(
            self.terminal_auth_from_original_uri_url(),
            HTTP_X_ORIGINAL_URI=f"/terminal/{self.attempt.id}/24000/",
        )

        self.assertEqual(response.status_code, 204)

    def test_terminal_auth_from_original_uri_denies_invalid_uri(self):
        self.client.login(
            username="terminal_user",
            password="password",
        )

        response = self.client.get(
            self.terminal_auth_from_original_uri_url(),
            HTTP_X_ORIGINAL_URI="/not-terminal/123/24000/",
        )

        self.assertEqual(response.status_code, 403)
