"""Offline prompt/transport regressions, not simulated evidence of LLM quality."""
import hashlib
import json
import os
from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase, override_settings
from django.utils import timezone

from sandbox.models import AIReview, TaskAttempt
from sandbox.services.ai_reviewer import (
    AIReviewerError, REQUIRED_CHECKS, create_ai_review, load_system_prompt,
    review_trainee_answer, run_ai_review, validate_review_response,
)
from sandbox.tests.base import SandboxTestCase


def valid_response():
    checks = {name: {"passed": True, "severity": "ok", "comment": ""}
              for name in REQUIRED_CHECKS}
    checks["completeness"]["missing_facts"] = []
    return {"checks": checks, "recommendations": []}


@override_settings(TWC_AI_PROMPT_VERSION="v3")
class PromptV3Tests(SimpleTestCase):
    def setUp(self):
        self.task = SimpleNamespace(
            slug="test", client_name="Алексей", ticket_title="Приложение",
            description="Добрый день. Приложение недоступно.",
            ai_review_context={"root_cause": "bind", "resolution": "Штатный restart",
                               "result": "Работает", "required_client_facts": []},
        )

    @patch.dict(os.environ, {"TWC_AI_AGENT_ID": "test", "TWC_AI_TOKEN": "test"})
    @patch("sandbox.services.ai_reviewer.requests.post")
    def test_regression_inputs_include_the_relevant_system_rules(self, post):
        # Each case locks a known regression's instructions and preserves the
        # evidence in the user message. The mocked result tests JSON transport only.
        cases = [
            ("Добрый день.", "Добрый день, Алексей!", "greeting",
             "на «Добрый день.» корректно ответить «Добрый день, Алексей!»"),
            ("Добрый вечер.", "Добрый вечер, Алексей!", "greeting",
             "на «Добрый вечер» — «Добрый вечер, Алексей!»"),
            ("Доброе утро.", "Доброе утро, Алексей!", "greeting",
             "на «Доброе утро» — «Доброе утро, Алексей!»"),
            ("Добрый день.", "Добрый день, Алексей! Добавила настройку.", "greeting",
             "Слова «добавил» / «Добавила» дальше по тексту не влияют на greeting"),
            ("Приложение недоступно.", "Здравствуйте, Алексей! Перезапустил вручную с bind 0.0.0.0.",
             "solution", "Альтернативные и дополнительные технически корректные действия допустимы"),
            ("Нужно хотя бы 10 МБ.", "Здравствуйте, Алексей! Успешно проверил загрузку файла 11 МБ.",
             "completeness", "требование 10 МБ подтверждено"),
            ("Приложение недоступно.", "Здравствуйте, Алексей! Выполнил kill 9 и перезапустил приложение.",
             "solution", "«kill 9» отправляет сигнал по умолчанию (обычно SIGTERM) процессу PID 9"),
            ("Сайт не работает.", "Здравствуйте, Алексей! Сайт работает. Проверьте со своей стороны.",
             "direct_answer", "Просьба «проверьте со своей стороны» не отменяет уже сообщённый результат"),
        ]
        post.return_value.json.return_value = {
            "choices": [{"message": {"content": json.dumps(valid_response())}}],
        }
        for description, answer, criterion, rule in cases:
            with self.subTest(criterion=criterion, answer=answer):
                self.task.description = description
                result = review_trainee_answer(self.task, answer)
                payload = post.call_args.kwargs["json"]
                self.assertEqual([m["role"] for m in payload["messages"]], ["system", "user"])
                system, user = [m["content"] for m in payload["messages"]]
                self.assertEqual(system, load_system_prompt("v3"))
                self.assertIn(rule, system)
                self.assertIn(description, user)
                self.assertTrue(user.endswith(answer))
                self.assertEqual(result["review"], valid_response())
                self.assertIn("НЕ то же самое, что «kill -9 <PID>»", system)

    def test_embedded_json_example_matches_existing_contract(self):
        prompt = load_system_prompt("v3")
        example = json.loads(prompt[prompt.index('{\n  "checks"'):])
        validate_review_response(example)
        self.assertEqual(set(example), {"checks", "recommendations"})

    def test_released_prompt_bytes_are_immutable(self):
        digest = hashlib.sha256(load_system_prompt("v3").encode("utf-8")).hexdigest()
        self.assertEqual(digest, "0542f1bc0ff037b39fd000d1b998307d3eab9466fd7ff3415b04dd5bf30d3ee0")

    @patch("sandbox.services.ai_reviewer.Path.read_bytes", side_effect=OSError("missing"))
    def test_missing_prompt_fails_explicitly(self, read):
        with self.assertRaisesMessage(AIReviewerError, "Cannot load"):
            load_system_prompt("v3")

    @patch("sandbox.services.ai_reviewer.Path.read_bytes", return_value=b" \n")
    def test_empty_prompt_fails_explicitly(self, read):
        with self.assertRaisesMessage(AIReviewerError, "empty"):
            load_system_prompt("v3")


@override_settings(TWC_AI_PROMPT_VERSION="v3")
class PromptV3PersistenceTests(SandboxTestCase):
    def setUp(self):
        user = self.create_user("v3-review", level="l1")
        task = self.create_task(self.create_queue("l1"), "v3-task")
        task.ai_review_context = {"root_cause": "bind", "required_client_facts": []}
        task.save(update_fields=["ai_review_context"])
        self.attempt = TaskAttempt.objects.create(
            user=user, task=task, client_answer="Здравствуйте! Работает.",
            technical_passed_at=timezone.now(),
        )

    @patch.dict(os.environ, {"TWC_AI_AGENT_ID": "test", "TWC_AI_TOKEN": "test"})
    @patch("sandbox.services.ai_reviewer.requests.post")
    def test_saved_version_hash_and_passed_check_reach_worker(self, post):
        from sandbox.tasks import run_ai_review_task
        review = create_ai_review(self.attempt)
        self.assertNotIn("_review_metadata", self.attempt.task.ai_review_context)
        post.return_value.json.return_value = {
            "choices": [{"message": {"content": json.dumps(valid_response())}}],
        }
        with self.settings(TWC_AI_PROMPT_VERSION="v1"):
            run_ai_review_task.run(review.pk)
        review.refresh_from_db()
        messages = post.call_args.kwargs["json"]["messages"]
        self.assertEqual(review.prompt_version, "v3")
        self.assertEqual(review.status, AIReview.Status.COMPLETED)
        self.assertEqual(review.task_context["_review_metadata"]["system_prompt_sha256"],
                         hashlib.sha256(messages[0]["content"].encode()).hexdigest())
        self.assertIn("автопроверки платформы: passed", messages[1]["content"])

    @patch.dict(os.environ, {"TWC_AI_AGENT_ID": "test", "TWC_AI_TOKEN": "test"})
    @patch("sandbox.services.ai_reviewer.requests.post")
    def test_changed_prompt_fails_before_http(self, post):
        review = create_ai_review(self.attempt)
        with patch("sandbox.services.ai_reviewer.load_system_prompt", return_value="changed"):
            with self.assertRaisesMessage(AIReviewerError, "hash mismatch"):
                run_ai_review(review)
        post.assert_not_called()
        review.refresh_from_db()
        self.assertEqual(review.status, AIReview.Status.ERROR)
