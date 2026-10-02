from html import escape
from unittest.mock import patch

from django.test import override_settings
from django.db import DatabaseError
from django.urls import reverse
from django.utils import timezone

from sandbox.models import TaskAttempt
from sandbox.tests.base import SandboxTestCase


class AnswerDraftTests(SandboxTestCase):
    def setUp(self):
        user = self.create_user("draft-trainee", level="l1")
        task = self.create_task(self.create_queue("l1"), "draft-task")
        task.requires_manual_review = True
        task.ai_review_context = {"root_cause": "test"}
        task.save(update_fields=["requires_manual_review", "ai_review_context"])
        self.attempt = TaskAttempt.objects.create(
            user=user, task=task, status=TaskAttempt.Status.IN_PROGRESS,
            technical_passed_at=timezone.now(),
        )
        self.client.force_login(user)

    @patch("sandbox.views.cleanup_attempt_environment")
    @patch("sandbox.views.start_ai_review_in_background")
    @patch("sandbox.views.create_ai_review")
    def test_invalid_posts_preserve_exact_drafts_without_workflow_changes(self, create, start, cleanup):
        cases = [
            {"client_answer": "", "trainee_report": "  Диагностика <nginx>\nещё строка  "},
            {"client_answer": "  Ответ <клиенту>\nещё строка  ", "trainee_report": ""},
            {"client_answer": " \n ", "trainee_report": "Сохранить комментарий"},
            {"client_answer": "Сохранить ответ", "trainee_report": " \n "},
            {"client_answer": "", "trainee_report": ""},
        ]
        for status in (TaskAttempt.Status.IN_PROGRESS, TaskAttempt.Status.FAILED):
            for data in cases:
                with self.subTest(status=status, data=data):
                    self.attempt.status = status
                    self.attempt.client_answer = "Старый ответ"
                    self.attempt.trainee_report = "Старый комментарий"
                    self.attempt.save()
                    before = TaskAttempt.objects.values().get(pk=self.attempt.pk)
                    response = self.client.post(
                        reverse("sandbox:check_task", args=[self.attempt.pk]), data, follow=True,
                    )
                    self.assertEqual(response.status_code, 200)
                    self.attempt.refresh_from_db()
                    self.assertEqual(self.attempt.client_answer, data["client_answer"])
                    self.assertEqual(self.attempt.trainee_report, data["trainee_report"])
                    for field, value in data.items():
                        self.assertEqual(getattr(response.context["attempt"], field), value)
                        if value.strip():
                            self.assertContains(response, escape(value))
                    after = TaskAttempt.objects.values().get(pk=self.attempt.pk)
                    for field in before:
                        if field not in data:
                            self.assertEqual(before[field], after[field], field)
                    self.assertFalse(self.attempt.ai_reviews.exists())
        create.assert_not_called()
        start.assert_not_called()
        cleanup.assert_not_called()

    def test_answer_fields_have_browser_validation(self):
        response = self.client.get(reverse("sandbox:task_detail", args=[self.attempt.pk]))
        for name in ("client_answer", "trainee_report"):
            self.assertContains(response, f'name="{name}"\n            required')

    @override_settings(TWC_AI_PROMPT_VERSION="v3")
    @patch("sandbox.views.cleanup_attempt_environment")
    @patch("sandbox.tasks.run_ai_review_task.delay")
    def test_prompt_load_failure_keeps_draft_and_original_state(self, delay, cleanup):
        for status in (TaskAttempt.Status.IN_PROGRESS, TaskAttempt.Status.FAILED):
            with self.subTest(status=status):
                self.attempt.status = status
                self.attempt.save(update_fields=["status"])
                data = {"client_answer": "  Ответ клиенту.  ", "trainee_report": "  Диагностика.  "}
                with self.captureOnCommitCallbacks(execute=True) as callbacks:
                    with patch("sandbox.services.ai_reviewer.Path.read_bytes", side_effect=OSError("missing prompt")):
                        response = self.client.post(reverse("sandbox:check_task", args=[self.attempt.pk]), data)
                self.assertEqual(response.status_code, 302)
                self.attempt.refresh_from_db()
                self.assertEqual(self.attempt.status, status)
                self.assertEqual(self.attempt.client_answer, data["client_answer"])
                self.assertEqual(self.attempt.trainee_report, data["trainee_report"])
                self.assertFalse(self.attempt.ai_reviews.exists())
                self.assertEqual(callbacks, [])
                page = self.client.get(response.url)
                self.assertContains(page, "Не удалось подготовить AI-проверку. Текст сохранён.")
        delay.assert_not_called()
        cleanup.assert_not_called()

    @override_settings(TWC_AI_PROMPT_VERSION="v3")
    @patch("sandbox.views.notify_manual_review_required")
    @patch("sandbox.views.cleanup_attempt_environment")
    @patch("sandbox.tasks.run_ai_review_task.delay")
    def test_review_and_submission_are_saved_before_celery_is_enqueued(self, delay, cleanup, notify):
        data = {"client_answer": "Ответ клиенту.", "trainee_report": "Диагностика."}
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(reverse("sandbox:check_task", args=[self.attempt.pk]), data)
            self.assertEqual(response.status_code, 302)
            self.attempt.refresh_from_db()
            self.assertEqual(self.attempt.status, TaskAttempt.Status.ON_REVIEW)
            self.assertEqual(self.attempt.client_answer, data["client_answer"])
            self.assertEqual(self.attempt.trainee_report, data["trainee_report"])
            review = self.attempt.ai_reviews.get()
            self.assertEqual(review.client_answer, data["client_answer"])
            self.assertEqual(review.prompt_version, "v3")
            delay.assert_not_called()
        delay.assert_called_once_with(review.pk)

    @override_settings(TWC_AI_PROMPT_VERSION="v3")
    @patch("sandbox.tasks.run_ai_review_task.delay")
    def test_state_write_failure_rolls_back_created_review_but_keeps_draft(self, delay):
        real_save = TaskAttempt.save

        def fail_state_write(attempt, *args, **kwargs):
            if "status" in kwargs.get("update_fields", []):
                raise DatabaseError("state write failed")
            return real_save(attempt, *args, **kwargs)

        data = {"client_answer": "Ответ клиенту.", "trainee_report": "Диагностика."}
        with self.captureOnCommitCallbacks(execute=True):
            with patch.object(TaskAttempt, "save", fail_state_write):
                with self.assertRaisesMessage(DatabaseError, "state write failed"):
                    self.client.post(reverse("sandbox:check_task", args=[self.attempt.pk]), data)
        self.attempt.refresh_from_db()
        self.assertEqual(self.attempt.status, TaskAttempt.Status.IN_PROGRESS)
        self.assertEqual(self.attempt.client_answer, data["client_answer"])
        self.assertEqual(self.attempt.trainee_report, data["trainee_report"])
        self.assertFalse(self.attempt.ai_reviews.exists())
        delay.assert_not_called()
