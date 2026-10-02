import json
import os
import subprocess
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase, override_settings

from sandbox.models import AIReview, TaskAttempt
from sandbox.tests.base import SandboxTestCase
from sandbox.services.ai_reviewer import (
    AIReviewerError,
    REQUIRED_CHECKS,
    build_review_input,
    create_ai_review,
    review_trainee_answer,
    run_ai_review,
    validate_review_response,
)


@override_settings(TWC_AI_PROMPT_VERSION="v1")
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

    def test_prompt_version_setting_defaults_to_v1_and_reads_environment(self):
        # Import real settings in an isolated process, without loading a local
        # .env or changing the environment of the running test suite.
        for value, expected in ((None, "v1"), ("v1", "v1"), ("v2", "v2"), ("v3", "v3"), (" ", "v1")):
            with self.subTest(value=value):
                env = {**os.environ, "SENTRY_DSN": ""}
                env.pop("TWC_AI_PROMPT_VERSION", None)
                if value is not None:
                    env["TWC_AI_PROMPT_VERSION"] = value
                result = subprocess.run(
                    [
                        sys.executable,
                        "-B",
                        "-c",
                        "from unittest.mock import patch\n"
                        "with patch('dotenv.load_dotenv'):\n"
                        "    from config.settings import TWC_AI_PROMPT_VERSION\n"
                        "    print(TWC_AI_PROMPT_VERSION)\n",
                    ],
                    env=env,
                    capture_output=True,
                    text=True,
                    check=True,
                )
                self.assertEqual(result.stdout.strip(), expected)

    def test_v1_message_is_unchanged_including_whitespace(self):
        expected = (
            "Условие задания:\n"
            "Имя клиента: Никита Волков\n"
            "Тема обращения: Сайт перестал открываться — ошибка 502 Bad Gateway\n\n"
            "Сообщение клиента:\n"
            "Сайт возвращает 502 Bad Gateway.\n\n"
            "Известные факты:\n"
            "Причина проблемы: В конфигурации Nginx был указан неверный порт "
            "приложения: 9001 вместо 9000.\n"
            "Выполненное решение: В конфигурации Nginx порт приложения "
            "был исправлен на 9000.\n"
            "Итоговое состояние: После исправления сайт корректно "
            "открывается через Nginx.\n"
            "Обязательные факты для клиента:\n"
            "Нет.\n\n"
            "Ответ стажёра:\n"
            "Здравствуйте!\r\nСайт работает."
        )
        for facts, facts_text in (
            ([], "Нет."),
            (["Первый факт.", "Второй факт."], "- Первый факт.\n- Второй факт."),
        ):
            with self.subTest(facts=facts):
                self.task.ai_review_context["required_client_facts"] = facts
                actual = build_review_input(
                    self.task, "Здравствуйте!\r\nСайт работает.",
                )
                self.assertEqual(actual, expected.replace("Нет.", facts_text))
                self.assertNotIn("Эталонный вариант решения", actual)
                self.assertNotIn("исчерпывающим списком", actual)

    @override_settings(TWC_AI_PROMPT_VERSION="v2")
    def test_v2_message_explains_reference_context_and_preserves_required_facts(self):
        context = {
            "root_cause": "Причина из snapshot.",
            "resolution": "Решение из snapshot.",
            "result": "Результат из snapshot.",
            "required_client_facts": [
                "Занимаемое логом место освобождено.",
                "Важные конфигурационные файлы не затронуты.",
            ],
        }
        result = build_review_input(
            self.task, "Здравствуйте!\r\nМой ответ.", review_context=context,
        )
        self.assertIn("Имя клиента: Никита Волков\n", result)
        self.assertIn("Сообщение клиента:\nСайт возвращает 502 Bad Gateway.\n", result)
        self.assertIn("Эталонный контекст задания:\n", result)
        self.assertIn("Причина проблемы:\nПричина из snapshot.\n", result)
        self.assertIn("Эталонный вариант решения:\nРешение из snapshot.\n", result)
        self.assertIn("Ожидаемый результат:\nРезультат из snapshot.\n", result)
        self.assertIn(
            "не является исчерпывающим списком допустимых действий "
            "или журналом действий стажёра",
            result,
        )
        self.assertIn(
            "Не считай дополнительное действие ошибочным только потому, "
            "что оно отсутствует в эталонном варианте.",
            result,
        )
        self.assertIn(
            "Обязательные факты для ответа клиенту:\n"
            "- Занимаемое логом место освобождено.\n"
            "- Важные конфигурационные файлы не затронуты.\n\n",
            result,
        )
        self.assertTrue(result.endswith("Ответ стажёра:\nЗдравствуйте!\r\nМой ответ."))
        self.assertNotIn("Выполненное решение", result)
        self.assertNotIn("Известные факты", result)
        self.assertNotIn("Итоговое состояние", result)
        self.assertNotIn("9001 вместо 9000", result)

    @override_settings(TWC_AI_PROMPT_VERSION="v2")
    def test_v2_message_handles_empty_required_facts(self):
        result = build_review_input(self.task, "Ответ.")
        self.assertIn("Обязательные факты для ответа клиенту:\nНет.\n\n", result)

    def test_explicit_version_overrides_current_setting_for_message(self):
        for saved, current, label in (
            ("v1", "v2", "Известные факты:"),
            ("v2", "v1", "Эталонный контекст задания:"),
            ("v1", "v3", "Известные факты:"),
            ("v2", "v3", "Эталонный контекст задания:"),
        ):
            with self.subTest(saved=saved), self.settings(TWC_AI_PROMPT_VERSION=current):
                result = build_review_input(self.task, "Ответ.", prompt_version=saved)
                self.assertIn(label, result)

    def test_unsupported_version_is_not_silently_formatted_as_v1_or_v2(self):
        with self.assertRaisesMessage(AIReviewerError, "Unsupported AI review prompt version"):
            build_review_input(self.task, "Ответ.", prompt_version="v999")


@override_settings(TWC_AI_PROMPT_VERSION="v1")
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
            prompt_version="v1",
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

    @override_settings(TWC_AI_PROMPT_VERSION="v2")
    def test_create_ai_review_saves_v2_version(self):
        review = create_ai_review(self.attempt)
        review.refresh_from_db()
        self.assertEqual(review.prompt_version, "v2")
        self.assertEqual(review.task_context, self.task.ai_review_context)
        self.assertEqual(review.client_answer, self.attempt.client_answer)
        self.assertEqual(review.status, AIReview.Status.PENDING)

    @override_settings(TWC_AI_PROMPT_VERSION="v999")
    def test_unsupported_config_does_not_create_mislabeled_review(self):
        with self.assertRaisesMessage(AIReviewerError, "Unsupported AI review prompt version"):
            create_ai_review(self.attempt)
        self.assertFalse(self.attempt.ai_reviews.exists())

    @patch.dict(
        os.environ,
        {"TWC_AI_AGENT_ID": "test-agent-id", "TWC_AI_TOKEN": "test-token"},
    )
    @patch("sandbox.services.ai_reviewer.requests.post")
    def test_worker_uses_snapshot_version_after_settings_change(self, post_mock):
        from sandbox.tasks import run_ai_review_task

        # This response only exercises transport/persistence, not LLM quality.
        checks = {
            key: {"passed": True, "severity": "ok", "comment": ""}
            for key in REQUIRED_CHECKS
        }
        checks["completeness"]["missing_facts"] = []
        post_mock.return_value.json.return_value = {
            "model": "test-model",
            "choices": [{"message": {"content": json.dumps({
                "checks": checks, "recommendations": [],
            })}}],
        }

        for saved, current, expected_label, forbidden_label in (
            ("v1", "v2", "Выполненное решение:", "Эталонный вариант решения:"),
            ("v2", "v1", "Эталонный вариант решения:", "Выполненное решение:"),
            ("v1", "v3", "Выполненное решение:", "Эталонный вариант решения:"),
            ("v2", "v3", "Эталонный вариант решения:", "Выполненное решение:"),
        ):
            for status in (AIReview.Status.PENDING, AIReview.Status.RUNNING):
                with self.subTest(saved=saved, status=status):
                    with self.settings(TWC_AI_PROMPT_VERSION=saved):
                        review = create_ai_review(self.attempt)
                    review.status = status
                    review.save(update_fields=["status"])
                    post_mock.reset_mock()

                    with self.settings(TWC_AI_PROMPT_VERSION=current):
                        # Load the saved record through the real Celery entry
                        # point, but run synchronously with HTTP mocked.
                        run_ai_review_task.run(review.pk)

                    post_mock.assert_called_once()
                    payload = post_mock.call_args.kwargs["json"]
                    self.assertEqual(set(payload), {"messages", "stream"})
                    self.assertIs(payload["stream"], False)
                    self.assertEqual(len(payload["messages"]), 1)
                    self.assertEqual(payload["messages"][0]["role"], "user")
                    content = payload["messages"][0]["content"]
                    self.assertIn(expected_label, content)
                    self.assertNotIn(forbidden_label, content)
                    self.assertIn("Неверный порт приложения.", content)
                    self.assertTrue(content.endswith(review.client_answer))
                    review.refresh_from_db()
                    self.assertEqual(review.prompt_version, saved)
                    self.assertEqual(review.status, AIReview.Status.COMPLETED)

    @patch.dict(
        os.environ,
        {"TWC_AI_AGENT_ID": "test-agent-id", "TWC_AI_TOKEN": "test-token"},
    )
    @patch("sandbox.services.ai_reviewer.requests.post")
    def test_unsupported_saved_version_records_error_without_http_request(self, post_mock):
        review = create_ai_review(self.attempt)
        review.prompt_version = "v999"
        review.save(update_fields=["prompt_version"])
        with self.assertRaisesMessage(AIReviewerError, "Unsupported AI review prompt version"):
            run_ai_review(review)
        post_mock.assert_not_called()
        review.refresh_from_db()
        self.assertEqual(review.prompt_version, "v999")
        self.assertEqual(review.status, AIReview.Status.ERROR)
