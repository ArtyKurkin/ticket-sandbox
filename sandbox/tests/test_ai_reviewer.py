import json
import os
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from sandbox.models import AIReview, TaskAttempt
from sandbox.tests.base import SandboxTestCase
from sandbox.services.ai_reviewer import (
    AIReviewerError,
    build_review_input,
    create_ai_review,
    review_trainee_answer,
    run_ai_review,
    validate_review_response,
)


class AIReviewerTests(SimpleTestCase):
    def setUp(self):
        self.task = SimpleNamespace(
            slug="nginx-upstream-wrong-port",
            client_name="Никита Волков",
            ticket_title="Сайт перестал открываться — ошибка 502 Bad Gateway",
            description="Сайт возвращает 502 Bad Gateway.",
            ai_review_context={
                "root_cause": (
                    "В конфигурации Nginx был указан неверный порт "
                    "приложения: 9001 вместо 9000."
                ),
                "resolution": (
                    "В конфигурации Nginx порт приложения "
                    "был исправлен на 9000."
                ),
                "result": (
                    "После исправления сайт корректно "
                    "открывается через Nginx."
                ),
                "required_client_facts": [],
            },
        )

    def test_build_review_input_contains_task_context_and_answer(self):
        result = build_review_input(
            self.task,
            "Здравствуйте, Никита. Сейчас сайт работает корректно.",
        )

        self.assertIn("Никита Волков", result)
        self.assertIn("9001 вместо 9000", result)
        self.assertIn(
            "Здравствуйте, Никита. Сейчас сайт работает корректно.",
            result,
        )

    @patch.dict(os.environ, {}, clear=True)
    def test_review_raises_when_agent_id_is_missing(self):
        with self.assertRaisesMessage(
            AIReviewerError,
            "TWC_AI_AGENT_ID is not configured",
        ):
            review_trainee_answer(
                self.task,
                "Здравствуйте, Никита.",
            )

    @patch.dict(
        os.environ,
        {
            "TWC_AI_AGENT_ID": "test-agent-id",
            "TWC_AI_TOKEN": "test-token",
        },
        clear=True,
    )
    @patch("sandbox.services.ai_reviewer.requests.post")
    def test_review_returns_parsed_ai_response(self, post_mock):
        ai_review = {
            "checks": {
                "greeting": {
                    "passed": True,
                    "severity": "ok",
                    "comment": "",
                },
                "problem_description": {
                    "passed": True,
                    "severity": "ok",
                    "comment": "",
                },
                "solution": {
                    "passed": True,
                    "severity": "ok",
                    "comment": "",
                },
                "completeness": {
                    "passed": True,
                    "severity": "ok",
                    "missing_facts": [],
                    "comment": "",
                },
                "direct_answer": {
                    "passed": True,
                    "severity": "ok",
                    "comment": "",
                },
                "client_language": {
                    "passed": True,
                    "severity": "ok",
                    "comment": "",
                },
                "structure_and_grammar": {
                    "passed": True,
                    "severity": "ok",
                    "comment": "",
                },
            },
            "recommendations": [],
        }

        response_mock = MagicMock()
        response_mock.json.return_value = {
            "model": "test-model",
            "usage": {
                "prompt_tokens": 123,
                "completion_tokens": 45,
                "total_tokens": 168,
            },
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            ai_review,
                            ensure_ascii=False,
                        )
                    }
                }
            ],
        }

        post_mock.return_value = response_mock

        result = review_trainee_answer(
            self.task,
            "Здравствуйте, Никита.",
        )

        self.assertEqual(result["review"], ai_review)
        self.assertEqual(result["model"], "test-model")
        self.assertEqual(result["input_tokens"], 123)
        self.assertEqual(result["output_tokens"], 45)
        self.assertEqual(result["raw_response"], response_mock.json.return_value)
        response_mock.raise_for_status.assert_called_once()

    @patch.dict(
        os.environ,
        {
            "TWC_AI_AGENT_ID": "test-agent-id",
            "TWC_AI_TOKEN": "test-token",
        },
        clear=True,
    )
    @patch("sandbox.services.ai_reviewer.requests.post")
    def test_review_raises_for_invalid_ai_response(self, post_mock):
        response_mock = MagicMock()
        response_mock.json.return_value = {
            "choices": [
                {
                    "message": {
                        "content": "not-json",
                    }
                }
            ]
        }

        post_mock.return_value = response_mock

        with self.assertRaisesMessage(
            AIReviewerError,
            "AI reviewer returned an invalid response",
        ):
            review_trainee_answer(
                self.task,
                "Здравствуйте, Никита.",
            )

    def test_validate_review_response_raises_when_check_is_missing(self):
        review = {
            "checks": {
                "greeting": {
                    "passed": True,
                    "severity": "ok",
                    "comment": "",
                }
            },
            "recommendations": [],
        }

        with self.assertRaisesMessage(
            AIReviewerError,
            "AI reviewer returned an invalid response structure",
        ):
            validate_review_response(review)

    def test_validate_review_response_raises_for_invalid_severity(self):
        checks = {
            check_name: {
                "passed": True,
                "severity": "ok",
                "comment": "",
            }
            for check_name in (
                "greeting",
                "problem_description",
                "solution",
                "completeness",
                "direct_answer",
                "client_language",
                "structure_and_grammar",
            )
        }

        checks["completeness"]["missing_facts"] = []
        checks["solution"]["severity"] = "warning"

        review = {
            "checks": checks,
            "recommendations": [],
        }

        with self.assertRaisesMessage(
            AIReviewerError,
            "AI reviewer returned an invalid response structure",
        ):
            validate_review_response(review)

    def test_build_review_input_uses_explicit_review_context(self):
        review_context = {
            "root_cause": "Старая причина из snapshot.",
            "resolution": "Старое решение из snapshot.",
            "result": "Старый результат из snapshot.",
            "required_client_facts": [],
        }

        result = build_review_input(
            self.task,
            "Здравствуйте, Никита.",
            review_context=review_context,
        )

        self.assertIn("Старая причина из snapshot.", result)
        self.assertNotIn("9001 вместо 9000", result)


class AIReviewDatabaseTests(SandboxTestCase):
    def setUp(self):
        self.user = self.create_user(
            username="ai-review-trainee",
            level="l1",
        )

        self.queue = self.create_queue(
            slug="l1",
            name="L1",
            order=1,
            required_level="l1",
        )

        self.task = self.create_task(
            queue=self.queue,
            slug="nginx-upstream-wrong-port",
            title="Nginx wrong upstream port",
        )

        self.task.ai_review_context = {
            "root_cause": "Неверный порт приложения.",
            "resolution": "Порт исправлен.",
            "result": "Сайт работает.",
            "required_client_facts": [],
        }
        self.task.save(update_fields=["ai_review_context"])

        self.attempt = TaskAttempt.objects.create(
            user=self.user,
            task=self.task,
            client_answer="Здравствуйте! Сайт снова работает.",
        )

    def test_create_ai_review_saves_snapshots(self):
        ai_review = create_ai_review(self.attempt)

        self.assertEqual(
            ai_review.client_answer,
            "Здравствуйте! Сайт снова работает.",
        )
        self.assertEqual(
            ai_review.task_context,
            self.task.ai_review_context,
        )
        self.assertEqual(
            ai_review.status,
            AIReview.Status.PENDING,
        )
        self.assertEqual(ai_review.prompt_version, "v1")

        self.attempt.client_answer = "Изменённый ответ"
        self.attempt.save(update_fields=["client_answer"])

        self.task.ai_review_context = {
            "root_cause": "Новая причина",
        }
        self.task.save(update_fields=["ai_review_context"])

        ai_review.refresh_from_db()

        self.assertEqual(
            ai_review.client_answer,
            "Здравствуйте! Сайт снова работает.",
        )
        self.assertEqual(
            ai_review.task_context["root_cause"],
            "Неверный порт приложения.",
        )

    @patch("sandbox.services.ai_reviewer.review_trainee_answer")
    def test_run_ai_review_saves_completed_result(self, review_mock):
        ai_review = create_ai_review(self.attempt)

        review_mock.return_value = {
            "review": {
                "checks": {
                    "greeting": {
                        "passed": True,
                        "severity": "ok",
                        "comment": "",
                    }
                },
                "recommendations": [],
            },
            "raw_response": {
                "model": "test-model",
            },
            "model": "test-model",
            "input_tokens": 100,
            "output_tokens": 25,
        }

        run_ai_review(ai_review)

        ai_review.refresh_from_db()

        self.assertEqual(
            ai_review.status,
            AIReview.Status.COMPLETED,
        )
        self.assertEqual(ai_review.model, "test-model")
        self.assertEqual(ai_review.input_tokens, 100)
        self.assertEqual(ai_review.output_tokens, 25)
        self.assertEqual(
            ai_review.checks["greeting"]["severity"],
            "ok",
        )
        self.assertEqual(ai_review.recommendations, [])
        self.assertEqual(ai_review.error_message, "")
        self.assertIsNotNone(ai_review.started_at)
        self.assertIsNotNone(ai_review.finished_at)

        review_mock.assert_called_once_with(
            task=self.task,
            client_answer="Здравствуйте! Сайт снова работает.",
            review_context={
                "root_cause": "Неверный порт приложения.",
                "resolution": "Порт исправлен.",
                "result": "Сайт работает.",
                "required_client_facts": [],
            },
        )

    @patch("sandbox.services.ai_reviewer.review_trainee_answer")
    def test_run_ai_review_saves_error(self, review_mock):
        ai_review = create_ai_review(self.attempt)

        review_mock.side_effect = AIReviewerError(
            "Timeweb AI is unavailable"
        )

        with self.assertRaisesMessage(
            AIReviewerError,
            "Timeweb AI is unavailable",
        ):
            run_ai_review(ai_review)

        ai_review.refresh_from_db()

        self.assertEqual(
            ai_review.status,
            AIReview.Status.ERROR,
        )
        self.assertEqual(
            ai_review.error_message,
            "Timeweb AI is unavailable",
        )
        self.assertIsNotNone(ai_review.started_at)
        self.assertIsNotNone(ai_review.finished_at)

    @patch("sandbox.tasks.run_ai_review_task.delay")
    def test_start_ai_review_in_background_enqueues_celery_task(self, delay_mock):
        from sandbox.services.ai_reviewer import (
            start_ai_review_in_background,
        )

        ai_review = create_ai_review(self.attempt)

        start_ai_review_in_background(ai_review)

        delay_mock.assert_called_once_with(ai_review.id)
