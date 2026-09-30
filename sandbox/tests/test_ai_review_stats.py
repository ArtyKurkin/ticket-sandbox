from datetime import timedelta
from unittest.mock import patch

from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone

from sandbox.ai_review_constants import AI_REVIEW_CHECK_LABELS
from sandbox.models import AIReview, TaskAttempt
from sandbox.services.ai_review_stats import build_ai_review_stats_context
from sandbox.tests.base import SandboxTestCase


class AIReviewStatsTests(SandboxTestCase):
    def setUp(self):
        self.mentor = self.create_user("stats-mentor", is_staff=True)
        self.trainee = self.create_user("stats-trainee", level="l1")
        self.queue = self.create_queue("l1")
        self.task = self.create_task(self.queue, "stats-task", title="Статистика Nginx")
        self.attempt = TaskAttempt.objects.create(
            user=self.trainee, task=self.task,
        )
        self.url = reverse("sandbox:ai_review_stats")

    def create_review(self, severities=None, **overrides):
        checks = {
            key: {"severity": "ok", "passed": True, "comment": ""}
            for key in AI_REVIEW_CHECK_LABELS
        }
        for key, severity in (severities or {}).items():
            checks[key].update(severity=severity, passed=severity == "ok")
        fields = {
            "attempt": self.attempt,
            "client_answer": "Полный ответ, который не нужен в статистике.",
            "checks": checks,
            "status": AIReview.Status.COMPLETED,
            "mentor_decision": AIReview.MentorDecision.APPROVED,
            "prompt_version": "v1",
            "model": "test-model",
        }
        fields.update(overrides)
        return AIReview.objects.create(**fields)

    def test_anonymous_redirected_to_sandbox_login(self):
        response = self.client.get(self.url)
        self.assertRedirects(response, f"{reverse('login')}?next={self.url}")

    @patch("sandbox.views.build_ai_review_stats_context")
    def test_non_staff_cannot_access_statistics(self, build_context):
        self.client.force_login(self.trainee)
        response = self.client.get(self.url)
        self.assertRedirects(response, reverse("sandbox:dashboard"))
        build_context.assert_not_called()

    def test_staff_access_and_navigation(self):
        self.client.force_login(self.mentor)
        response = self.client.get(self.url)
        self.assertContains(response, "AI Reviewer — статистика")
        self.assertContains(response, f'href="{reverse("sandbox:dashboard")}"')
        response = self.client.get(reverse("sandbox:dashboard"))
        self.assertContains(response, f'href="{self.url}"')
        self.client.force_login(self.trainee)
        response = self.client.get(reverse("sandbox:dashboard"))
        self.assertNotContains(response, f'href="{self.url}"')

    def test_empty_statistics(self):
        self.client.force_login(self.mentor)
        response = self.client.get(self.url)
        stats = response.context["stats"]
        for key in ("total", "completed", "comparisons", "agreement",
                    "false_critical", "missed_revision"):
            self.assertEqual(stats[key], 0)
        for key in ("agreement", "false_critical", "missed_revision"):
            self.assertIsNone(stats[f"{key}_percent"])
        self.assertEqual(response.context["matrix"], {
            "approved": {"approved": 0, "needs_revision": 0},
            "needs_revision": {"approved": 0, "needs_revision": 0},
        })
        self.assertEqual(response.context["prompt_stats"], [])
        self.assertEqual(response.context["model_stats"], [])
        self.assertEqual(response.context["recent_disagreements"], [])
        self.assertContains(response, "Пока нет сравнений")
        self.assertNotContains(response, "None")
        self.assertNotContains(response, "0.0%")

    def assert_outcome(self, severities, mentor, ai, outcome):
        self.create_review(severities, mentor_decision=mentor)
        context = build_ai_review_stats_context()
        self.assertEqual(context["stats"]["comparisons"], 1)
        self.assertEqual(context["stats"][outcome], 1)
        self.assertEqual(context["matrix"][ai][mentor], 1)
        self.assertEqual(sum(sum(row.values()) for row in context["matrix"].values()), 1)
        for key in ("agreement", "false_critical", "missed_revision"):
            if key != outcome:
                self.assertEqual(context["stats"][key], 0)
        return context

    def test_critical_and_mentor_revision_agree(self):
        self.assert_outcome(
            {"solution": "critical"}, "needs_revision", "needs_revision", "agreement",
        )

    def test_no_critical_and_mentor_approved_agree(self):
        self.assert_outcome({}, "approved", "approved", "agreement")

    def test_critical_and_mentor_approved_is_false_critical(self):
        self.assert_outcome(
            {"greeting": "critical"}, "approved", "needs_revision", "false_critical",
        )

    def test_no_critical_and_mentor_revision_is_missed_revision(self):
        self.assert_outcome({}, "needs_revision", "approved", "missed_revision")

    def test_minor_and_mentor_approved_agree_even_when_passed_is_false(self):
        self.assert_outcome(
            {"greeting": "minor"}, "approved", "approved", "agreement",
        )

    def test_minor_and_mentor_revision_is_missed_revision(self):
        self.assert_outcome(
            {"solution": "minor"}, "needs_revision", "approved", "missed_revision",
        )

    def test_multiple_critical_criteria_count_once_each_per_snapshot(self):
        self.create_review({"greeting": "critical", "solution": "critical"})
        self.create_review({"greeting": "critical"})
        self.create_review(
            {"greeting": "critical"}, mentor_decision="needs_revision",
        )
        context = build_ai_review_stats_context()
        counts = {row["label"]: row["false_critical"] for row in context["criteria"]}
        self.assertEqual(counts["Приветствие"], 2)
        self.assertEqual(counts["Решение"], 1)
        self.assertEqual(sum(counts.values()), 3)
        self.assertEqual(context["stats"]["false_critical"], 2)
        self.assertEqual(context["stats"]["comparisons"], 3)

    def test_reviews_without_mentor_decision_are_not_comparisons(self):
        self.create_review({"greeting": "critical"}, mentor_decision="")
        context = build_ai_review_stats_context()
        self.assertEqual(context["stats"]["total"], 1)
        self.assertEqual(context["stats"]["completed"], 1)
        self.assertEqual(context["stats"]["comparisons"], 0)
        self.assertIsNone(context["stats"]["agreement_percent"])
        self.assertEqual(context["prompt_stats"], [])
        self.assertEqual(context["recent_disagreements"], [])

    def test_unfinished_and_failed_reviews_are_not_comparisons(self):
        for status in (AIReview.Status.PENDING, AIReview.Status.RUNNING, AIReview.Status.ERROR):
            self.create_review({"solution": "critical"}, status=status)
        context = build_ai_review_stats_context()
        self.assertEqual(context["stats"]["total"], 3)
        self.assertEqual(context["stats"]["completed"], 0)
        self.assertEqual(context["stats"]["comparisons"], 0)
        self.assertEqual(context["prompt_stats"], [])
        self.assertEqual(context["recent_disagreements"], [])
        self.assertTrue(all(row["critical"] == 0 for row in context["criteria"]))

    def test_percentages_use_only_eligible_comparisons(self):
        for _ in range(32):
            self.create_review()
        for _ in range(2):
            self.create_review({"greeting": "critical"})
        for _ in range(3):
            self.create_review(mentor_decision="needs_revision")
        self.create_review(mentor_decision="")
        self.create_review(status=AIReview.Status.ERROR)
        self.client.force_login(self.mentor)
        response = self.client.get(self.url)
        stats = response.context["stats"]
        self.assertEqual((stats["total"], stats["completed"], stats["comparisons"]), (39, 38, 37))
        self.assertAlmostEqual(stats["agreement_percent"], 32 * 100 / 37)
        self.assertAlmostEqual(stats["false_critical_percent"], 2 * 100 / 37)
        self.assertAlmostEqual(stats["missed_revision_percent"], 3 * 100 / 37)
        self.assertContains(response, "32 из 37 · 86.5%")
        self.assertContains(response, "2 · 5.4%")
        self.assertContains(response, "3 · 8.1%")

    def test_prompt_versions_have_independent_denominators(self):
        self.create_review(prompt_version="v1")
        self.create_review({"greeting": "critical"}, prompt_version="v1")
        self.create_review(mentor_decision="needs_revision", prompt_version="v2")
        self.create_review(prompt_version="")
        self.create_review(prompt_version="  ")
        self.create_review(prompt_version="excluded", mentor_decision="")
        prompts = {row["version"]: row for row in build_ai_review_stats_context()["prompt_stats"]}
        self.assertEqual(set(prompts), {"v1", "v2", ""})
        self.assertEqual(prompts["v1"]["comparisons"], 2)
        self.assertEqual(prompts["v1"]["agreement"], 1)
        self.assertEqual(prompts["v1"]["false_critical"], 1)
        self.assertEqual(prompts["v1"]["agreement_percent"], 50)
        self.assertEqual(prompts["v1"]["false_critical_percent"], 50)
        self.assertEqual(prompts["v2"]["missed_revision"], 1)
        self.assertEqual(prompts["v2"]["missed_revision_percent"], 100)
        self.assertEqual(prompts[""]["comparisons"], 2)
        self.assertEqual(prompts[""]["agreement_percent"], 100)
        self.client.force_login(self.mentor)
        self.assertContains(self.client.get(self.url), "Не указана")

    def test_historical_snapshots_are_independent_of_current_attempt_decision(self):
        self.attempt.mentor_decision = TaskAttempt.MentorDecision.APPROVED
        self.attempt.is_current = False
        self.attempt.save(update_fields=["mentor_decision", "is_current"])
        self.create_review({"solution": "critical"}, mentor_decision="needs_revision")
        self.create_review()
        self.create_review(mentor_decision="needs_revision")
        stats = build_ai_review_stats_context()["stats"]
        self.assertEqual(stats["comparisons"], 3)
        self.assertEqual(stats["agreement"], 2)
        self.assertEqual(stats["missed_revision"], 1)

    def test_severity_distribution_includes_all_completed_reviews(self):
        self.create_review({"greeting": "critical", "solution": "minor"})
        self.create_review({"greeting": "minor"}, mentor_decision="")
        self.create_review({"greeting": "critical"}, status=AIReview.Status.ERROR)
        criteria = {row["label"]: row for row in build_ai_review_stats_context()["criteria"]}
        self.assertEqual(criteria["Приветствие"]["critical"], 1)
        self.assertEqual(criteria["Приветствие"]["minor"], 1)
        self.assertEqual(criteria["Приветствие"]["ok"], 0)
        self.assertEqual(criteria["Решение"]["minor"], 1)
        self.assertEqual(criteria["Решение"]["ok"], 1)
        self.assertEqual(criteria["Полнота ответа"]["ok"], 2)

    def test_models_count_all_reviews_and_group_missing_names(self):
        self.create_review()
        self.create_review(status=AIReview.Status.ERROR)
        self.create_review(model="second-model", mentor_decision="")
        self.create_review(model="", status=AIReview.Status.PENDING)
        self.create_review(model=" ", status=AIReview.Status.RUNNING)
        models = {row["model"]: row["count"] for row in build_ai_review_stats_context()["model_stats"]}
        self.assertEqual(models, {"test-model": 2, "second-model": 1, "": 2})

    def test_recent_disagreements_order_by_snapshot_creation_newest_first(self):
        first = self.create_review({"solution": "critical"})
        second = self.create_review(mentor_decision="needs_revision")
        now = timezone.now()
        AIReview.objects.filter(pk=first.pk).update(created_at=now, mentor_reviewed_at=now - timedelta(days=1))
        AIReview.objects.filter(pk=second.pk).update(created_at=now - timedelta(days=1), mentor_reviewed_at=now)
        self.create_review()  # A newer agreement must not appear.
        recent = build_ai_review_stats_context()["recent_disagreements"]
        self.assertEqual([item["id"] for item in recent], [first.pk, second.pk])
        self.assertEqual(recent[0]["critical_labels"], ["Решение"])
        self.assertEqual(recent[1]["critical_labels"], [])

    def test_recent_disagreements_limit_ten_and_break_date_ties_by_id(self):
        reviews = [self.create_review(mentor_decision="needs_revision") for _ in range(12)]
        AIReview.objects.update(created_at=timezone.now())
        recent = build_ai_review_stats_context()["recent_disagreements"]
        self.assertEqual([item["id"] for item in recent], [review.pk for review in reversed(reviews[-10:])])

    def test_render_has_no_n_plus_one_and_links_to_existing_attempts(self):
        for index in range(10):
            user = self.create_user(f"stats-trainee-{index}", level="l1")
            task = self.create_task(self.queue, f"stats-task-{index}", order=index + 2)
            attempt = TaskAttempt.objects.create(user=user, task=task)
            self.create_review({"solution": "critical"}, attempt=attempt)
        with self.assertNumQueries(2):
            context = build_ai_review_stats_context()
            html = render_to_string("sandbox/ai_review_stats.html", context)
        self.assertIn(reverse("sandbox:task_detail", args=[attempt.pk]), html)
        self.assertIn(user.username, html)
        self.assertIn(task.title, html)
        self.assertNotIn("Полный ответ, который не нужен в статистике.", html)
