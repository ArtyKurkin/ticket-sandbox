import json
import os
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from sandbox.services.ai_reviewer import (
    AIReviewerError,
    build_review_input,
    review_trainee_answer,
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
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            ai_review,
                            ensure_ascii=False,
                        )
                    }
                }
            ]
        }

        post_mock.return_value = response_mock

        result = review_trainee_answer(
            self.task,
            "Здравствуйте, Никита.",
        )

        self.assertEqual(result, ai_review)
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
