from unittest.mock import patch

from django.test import SimpleTestCase
from django.urls import reverse
from django.utils import timezone
from django.utils.html import escape
from django.utils.safestring import mark_safe

from sandbox.models import AIReview, TaskAttempt
from sandbox.services.ai_reviewer import build_review_input
from sandbox.templatetags.answer_formatting import render_client_answer
from sandbox.tests.base import SandboxTestCase


class ClientAnswerRendererTests(SimpleTestCase):
    def test_plain_text_preserves_line_breaks(self):
        self.assertEqual(render_client_answer("Первая строка.\n\nПоследняя."),
                         "Первая строка.<br><br>Последняя.")

    def test_multiline_code_preserves_indentation_and_line_breaks(self):
        self.assertEqual(render_client_answer("[code]\nnginx -t\n  systemctl reload nginx\n[/code]"),
                         '<pre class="client-answer-code"><code>\nnginx -t\n  systemctl reload nginx\n</code></pre>')

    def test_multiple_blocks_with_text_before_between_and_after(self):
        self.assertEqual(render_client_answer("До\n[code]one[/code]\nМежду\n[code]two[/code]\nПосле"),
                         'До<br><pre class="client-answer-code"><code>one</code></pre><br>Между<br>'
                         '<pre class="client-answer-code"><code>two</code></pre><br>После')

    def test_html_and_xss_outside_code_are_escaped(self):
        self.assertEqual(render_client_answer('<script>alert("x")</script>\n<img src=x onerror="alert(1)">'),
                         '&lt;script&gt;alert(&quot;x&quot;)&lt;/script&gt;<br>&lt;img src=x onerror=&quot;alert(1)&quot;&gt;')

    def test_html_xss_and_special_characters_inside_code_are_escaped(self):
        self.assertEqual(render_client_answer('[code]<script>alert("x")</script>\n< > & " \'[/code]'),
                         '<pre class="client-answer-code"><code>&lt;script&gt;alert(&quot;x&quot;)&lt;/script&gt;'
                         '\n&lt; &gt; &amp; &quot; &#x27;</code></pre>')

    def test_unclosed_code_stays_literal_and_escaped(self):
        self.assertEqual(render_client_answer("До\n[code]\nsomething <script>"),
                         "До<br>[code]<br>something &lt;script&gt;")

    def test_empty_code_block(self):
        self.assertEqual(render_client_answer("[code][/code]"),
                         '<pre class="client-answer-code"><code></code></pre>')

    def test_windows_and_unix_newlines_are_rendered_identically(self):
        unix = "До\n[code]\na\nb\n[/code]\nПосле"
        expected = render_client_answer(unix)
        for ending in ("\r\n", "\r"):
            with self.subTest(ending=ending):
                self.assertEqual(render_client_answer(unix.replace("\n", ending)), expected)

    def test_safe_string_input_is_still_escaped(self):
        self.assertEqual(render_client_answer(mark_safe('<b>outside</b>[code]</code><script>bad()</script>[/code]')),
                         '&lt;b&gt;outside&lt;/b&gt;<pre class="client-answer-code"><code>'
                         '&lt;/code&gt;&lt;script&gt;bad()&lt;/script&gt;</code></pre>')

    def test_unmatched_tag_after_a_valid_block_remains_literal(self):
        self.assertEqual(render_client_answer("[code]ok[/code][code]<img>"),
                         '<pre class="client-answer-code"><code>ok</code></pre>[code]&lt;img&gt;')

    def test_other_markup_is_not_interpreted(self):
        self.assertEqual(render_client_answer("[b]bold[/b] **text** [CODE]x[/CODE]"),
                         "[b]bold[/b] **text** [CODE]x[/CODE]")

    def test_empty_answer(self):
        self.assertEqual(render_client_answer(""), "")
        self.assertEqual(render_client_answer(None), "")


class ClientAnswerPageTests(SandboxTestCase):
    def setUp(self):
        self.trainee = self.create_user("code-trainee", level="l1")
        self.mentor = self.create_user("code-mentor", is_staff=True)
        self.task = self.create_task(self.create_queue("l1"), "code-task")
        self.task.requires_manual_review = True
        self.task.ai_review_context = {"root_cause": "Тестовая причина"}
        self.task.save(update_fields=["requires_manual_review", "ai_review_context"])
        self.answer = 'До <img src=x onerror="alert(1)">\n[code]\n<script>alert(1)</script>\n[/code]\nПосле'
        self.attempt = TaskAttempt.objects.create(
            user=self.trainee, task=self.task, client_answer=self.answer,
            status=TaskAttempt.Status.ON_REVIEW, technical_passed_at=timezone.now(),
        )
        self.url = reverse("sandbox:task_detail", args=[self.attempt.pk])
        self.client.force_login(self.trainee)

    def assert_safe_block(self, response):
        self.assertContains(response, '<pre class="client-answer-code"><code>\n&lt;script&gt;alert(1)&lt;/script&gt;\n</code></pre>')
        self.assertContains(response, 'До &lt;img src=x onerror=&quot;alert(1)&quot;&gt;<br>')
        self.assertNotContains(response, '<script>alert(1)</script>')
        self.assertNotContains(response, '<img src=x onerror="alert(1)">')

    def test_locked_answer_for_trainee_and_mentor(self):
        for user in (self.trainee, self.mentor):
            with self.subTest(user=user.username):
                self.client.force_login(user)
                response = self.client.get(self.url)
                self.assertContains(response, "Ответ зафиксирован")
                self.assert_safe_block(response)

    def test_collapsed_extra_attempt_answer(self):
        self.attempt.attempt_number = 2
        self.attempt.status = TaskAttempt.Status.PASSED
        self.attempt.save(update_fields=["attempt_number", "status"])
        response = self.client.get(self.url)
        self.assertContains(response, "Показать отправленный ответ")
        self.assert_safe_block(response)

    def test_archived_answer_without_manual_review(self):
        self.task.requires_manual_review = False
        self.task.save(update_fields=["requires_manual_review"])
        self.attempt.is_current = False
        self.attempt.save(update_fields=["is_current"])
        self.assert_safe_block(self.client.get(self.url))

    def test_ai_history_uses_the_same_safe_renderer(self):
        self.client.force_login(self.mentor)
        AIReview.objects.create(attempt=self.attempt, client_answer=self.answer,
                                status=AIReview.Status.COMPLETED)
        AIReview.objects.create(attempt=self.attempt, client_answer="Последняя версия.",
                                status=AIReview.Status.COMPLETED)
        self.attempt.client_answer = "Последняя версия."
        self.attempt.save(update_fields=["client_answer"])
        self.assert_safe_block(self.client.get(self.url))

    def test_needs_revision_keeps_literal_tags_in_editable_textarea(self):
        self.attempt.status = TaskAttempt.Status.FAILED
        self.attempt.mentor_decision = TaskAttempt.MentorDecision.NEEDS_REVISION
        self.attempt.save(update_fields=["status", "mentor_decision"])
        response = self.client.get(self.url)
        self.assertContains(response, f'>{escape(self.answer)}</textarea>')
        self.assertContains(response, 'data-code-target="client-answer"')
        self.assertContains(response, 'type="button"\n              class="button secondary answer-code-button"')
        self.assertNotContains(response, '<pre class="client-answer-code">')

    @patch("sandbox.views.cleanup_attempt_environment")
    @patch("sandbox.views.notify_manual_review_required")
    @patch("sandbox.tasks.run_ai_review_task.delay")
    def test_submission_and_ai_snapshot_keep_raw_tags(self, delay, notify, cleanup):
        self.attempt.status = TaskAttempt.Status.IN_PROGRESS
        self.attempt.save(update_fields=["status"])
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(reverse("sandbox:check_task", args=[self.attempt.pk]), {
                "client_answer": self.answer, "trainee_report": "Диагностика.",
            })
        self.assertEqual(response.status_code, 302)
        self.attempt.refresh_from_db()
        review = self.attempt.ai_reviews.get()
        self.assertEqual(self.attempt.client_answer, self.answer)
        self.assertEqual(review.client_answer, self.answer)
        self.assertTrue(build_review_input(self.task, review.client_answer, prompt_version="v3")
                        .endswith("Ответ стажёра:\n" + self.answer))
        delay.assert_called_once_with(review.pk)
