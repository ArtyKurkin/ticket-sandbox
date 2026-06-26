from unittest.mock import MagicMock, patch

import requests
from django.test import SimpleTestCase
from sandbox.tests.base import SandboxTestCase
from django.utils import timezone

from sandbox.models import TaskAttempt, TraineeProfile
from sandbox.services.notifications import (
    notify_manual_review_required,
    notify_user_completed_all_tasks,
    user_completed_all_available_tasks,
)

from sandbox.services.telegram import send_telegram


class TelegramNotificationTests(SimpleTestCase):
    @patch.dict(
        "os.environ",
        {
            "TELEGRAM_BOT_TOKEN": "",
            "TELEGRAM_CHAT_ID": "",
        },
    )
    @patch("sandbox.services.telegram.requests.post")
    def test_send_telegram_does_nothing_without_env(
        self,
        mocked_post,
    ):
        result = send_telegram("test message")

        self.assertFalse(result)
        mocked_post.assert_not_called()

    @patch.dict(
        "os.environ",
        {
            "TELEGRAM_BOT_TOKEN": "test-token",
            "TELEGRAM_CHAT_ID": "123456",
        },
    )
    @patch("sandbox.services.telegram.requests.post")
    def test_send_telegram_posts_message_when_env_is_configured(
        self,
        mocked_post,
    ):
        response = MagicMock()
        response.raise_for_status.return_value = None
        mocked_post.return_value = response

        result = send_telegram("hello <b>mentor</b>")

        self.assertTrue(result)
        mocked_post.assert_called_once_with(
            "https://api.telegram.org/bottest-token/sendMessage",
            json={
                "chat_id": "123456",
                "text": "hello <b>mentor</b>",
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
            },
            timeout=5,
        )
        response.raise_for_status.assert_called_once()

    @patch.dict(
        "os.environ",
        {
            "TELEGRAM_BOT_TOKEN": "test-token",
            "TELEGRAM_CHAT_ID": "123456",
        },
    )
    @patch("sandbox.services.telegram.requests.post")
    def test_send_telegram_logs_warning_and_does_not_raise_on_request_error(
        self,
        mocked_post,
    ):
        mocked_post.side_effect = requests.RequestException("telegram is down")

        with self.assertLogs("sandbox.telegram", level="WARNING") as logs:
            result = send_telegram("test message")

        self.assertFalse(result)
        self.assertTrue(
            any(
                "Не удалось отправить Telegram-уведомление" in message
                for message in logs.output
            ),
            logs.output,
        )


class TrainingNotificationTests(SandboxTestCase):
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

    @patch("sandbox.services.notifications.send_telegram")
    def test_notify_manual_review_required_sends_message_for_on_review_attempt(
        self,
        mocked_send_telegram,
    ):
        task = self.create_task(
            queue=self.queue,
            slug="manual-review-task",
            order=1,
            title="Nginx не запускается",
        )
        task.requires_manual_review = True
        task.save(update_fields=["requires_manual_review"])

        attempt = TaskAttempt.objects.create(
            user=self.user,
            task=task,
            status=TaskAttempt.Status.ON_REVIEW,
            attempt_number=1,
            technical_passed_at=timezone.now(),
        )

        mocked_send_telegram.return_value = True

        result = notify_manual_review_required(attempt)

        self.assertTrue(result)
        mocked_send_telegram.assert_called_once()

        message = mocked_send_telegram.call_args.args[0]
        self.assertIn("Требуется ручная проверка", message)
        self.assertIn("trainee", message)
        self.assertIn("Nginx не запускается", message)
        self.assertIn("ОТП Cloud L1", message)

    @patch("sandbox.services.notifications.send_telegram")
    def test_notify_manual_review_required_does_not_send_for_extra_attempt(
        self,
        mocked_send_telegram,
    ):
        task = self.create_task(
            queue=self.queue,
            slug="extra-manual-review-task",
            order=1,
        )
        task.requires_manual_review = True
        task.save(update_fields=["requires_manual_review"])

        attempt = TaskAttempt.objects.create(
            user=self.user,
            task=task,
            status=TaskAttempt.Status.ON_REVIEW,
            attempt_number=2,
            technical_passed_at=timezone.now(),
        )

        result = notify_manual_review_required(attempt)

        self.assertFalse(result)
        mocked_send_telegram.assert_not_called()

    @patch("sandbox.services.notifications.send_telegram")
    def test_notify_manual_review_required_does_not_send_if_status_is_not_on_review(
        self,
        mocked_send_telegram,
    ):
        task = self.create_task(
            queue=self.queue,
            slug="not-on-review-task",
            order=1,
        )
        task.requires_manual_review = True
        task.save(update_fields=["requires_manual_review"])

        attempt = TaskAttempt.objects.create(
            user=self.user,
            task=task,
            status=TaskAttempt.Status.IN_PROGRESS,
            attempt_number=1,
            technical_passed_at=timezone.now(),
        )

        result = notify_manual_review_required(attempt)

        self.assertFalse(result)
        mocked_send_telegram.assert_not_called()

    def test_user_completed_all_available_tasks_returns_false_if_task_remains(self):
        completed_task = self.create_task(
            queue=self.queue,
            slug="completed-task",
            order=1,
        )
        self.create_task(
            queue=self.queue,
            slug="remaining-task",
            order=2,
        )

        TaskAttempt.objects.create(
            user=self.user,
            task=completed_task,
            status=TaskAttempt.Status.PASSED,
            attempt_number=1,
            technical_passed_at=timezone.now(),
        )

        self.assertFalse(
            user_completed_all_available_tasks(self.user)
        )

    def test_user_completed_all_available_tasks_returns_true_when_all_tasks_completed(self):
        first_task = self.create_task(
            queue=self.queue,
            slug="first-completed-task",
            order=1,
        )
        second_task = self.create_task(
            queue=self.queue,
            slug="second-completed-task",
            order=2,
        )

        TaskAttempt.objects.create(
            user=self.user,
            task=first_task,
            status=TaskAttempt.Status.PASSED,
            attempt_number=1,
            technical_passed_at=timezone.now(),
        )
        TaskAttempt.objects.create(
            user=self.user,
            task=second_task,
            status=TaskAttempt.Status.PASSED,
            attempt_number=1,
            technical_passed_at=timezone.now(),
        )

        self.assertTrue(
            user_completed_all_available_tasks(self.user)
        )

    @patch("sandbox.services.notifications.send_telegram")
    def test_notify_user_completed_all_tasks_sends_message_when_all_tasks_completed(
        self,
        mocked_send_telegram,
    ):
        first_task = self.create_task(
            queue=self.queue,
            slug="first-task",
            order=1,
        )
        second_task = self.create_task(
            queue=self.queue,
            slug="second-task",
            order=2,
        )

        TaskAttempt.objects.create(
            user=self.user,
            task=first_task,
            status=TaskAttempt.Status.PASSED,
            attempt_number=1,
            technical_passed_at=timezone.now(),
        )
        last_attempt = TaskAttempt.objects.create(
            user=self.user,
            task=second_task,
            status=TaskAttempt.Status.PASSED,
            attempt_number=1,
            technical_passed_at=timezone.now(),
        )

        mocked_send_telegram.return_value = True

        result = notify_user_completed_all_tasks(last_attempt)

        self.assertTrue(result)
        mocked_send_telegram.assert_called_once()

        message = mocked_send_telegram.call_args.args[0]
        self.assertIn("Стажёр прошёл все задания технически", message)
        self.assertIn("trainee", message)

    @patch("sandbox.services.notifications.send_telegram")
    def test_notify_user_completed_all_tasks_does_not_send_for_extra_attempt(
        self,
        mocked_send_telegram,
    ):
        task = self.create_task(
            queue=self.queue,
            slug="extra-completed-task",
            order=1,
        )

        attempt = TaskAttempt.objects.create(
            user=self.user,
            task=task,
            status=TaskAttempt.Status.PASSED,
            attempt_number=2,
            technical_passed_at=timezone.now(),
        )

        result = notify_user_completed_all_tasks(attempt)

        self.assertFalse(result)
        mocked_send_telegram.assert_not_called()
