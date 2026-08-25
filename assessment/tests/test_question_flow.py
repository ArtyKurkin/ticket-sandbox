from datetime import timedelta

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from assessment.constants import (
    ExamAttemptStatus,
    QuestionDifficulty,
    QuestionType,
    SupportLevel,
)
from assessment.models import (
    AssessmentCampaign,
    ExamAssignment,
    ExamAttempt,
    ExamBlueprint,
    ExamQuestionSnapshot,
    SupportProfile,
)
from assessment.services.question_flow import (
    open_current_question,
)


class QuestionFlowTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="question-flow-user",
            password="test-password",
            first_name="Иван",
        )

        employee = SupportProfile.objects.create(
            user=self.user,
            level=SupportLevel.L1,
        )

        blueprint = ExamBlueprint.objects.create(
            name="Шаблон flow",
            slug="test-question-flow-blueprint",
            level=SupportLevel.L1,
            is_active=True,
        )

        campaign = AssessmentCampaign.objects.create(
            name="Кампания flow",
            slug="test-question-flow-campaign",
            blueprint=blueprint,
            is_active=True,
        )

        assignment = ExamAssignment.objects.create(
            campaign=campaign,
            employee=employee,
        )

        self.attempt = ExamAttempt.objects.create(
            assignment=assignment,
            attempt_number=1,
            status=ExamAttemptStatus.IN_PROGRESS,
            selection_seed="flow-seed",
            campaign_name=campaign.name,
            blueprint_name=blueprint.name,
            level=SupportLevel.L1,
            pass_percentage=85,
            allow_back_navigation=False,
            shuffle_questions=True,
            shuffle_answer_options=True,
        )

        self.first = self.create_snapshot(
            position=1,
            prompt="Первый тестовый вопрос",
        )

        self.second = self.create_snapshot(
            position=2,
            prompt="Второй тестовый вопрос",
        )

        self.client.force_login(
            self.user
        )

    def create_snapshot(
        self,
        *,
        position,
        prompt,
    ):
        return ExamQuestionSnapshot.objects.create(
            attempt=self.attempt,
            position=position,
            topic_name="Linux и VDS",
            topic_slug=f"flow-topic-{position}",
            skill_name=f"Навык {position}",
            skill_slug=f"flow-skill-{position}",
            family_name=f"Семейство {position}",
            family_slug=f"flow-family-{position}",
            question_title=f"Вопрос {position}",
            question_slug=f"flow-question-{position}",
            question_type=QuestionType.SINGLE_CHOICE,
            difficulty=QuestionDifficulty.HARD,
            scenario="Есть проблема на сервере.",
            diagnostic_data=(
                "systemctl status nginx\n"
                "failed"
            ),
            diagnostic_blocks=[],
            prompt=prompt,
            time_limit_seconds=90,
            visible_payload={
                "options": [
                    {
                        "key": "option-1",
                        "text": "Правильный",
                    },
                    {
                        "key": "option-2",
                        "text": "Неправильный",
                    },
                ],
            },
            grading_payload={
                "correct_keys": [
                    "option-1",
                ],
            },
        )

    def test_opening_question_starts_server_timer(
        self,
    ):
        self.assertIsNone(
            self.first.started_at
        )

        response = self.client.get(
            reverse(
                "assessment:attempt_question",
                args=[self.attempt.pk],
            )
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        self.first.refresh_from_db()

        self.assertIsNotNone(
            self.first.started_at
        )

        self.assertContains(
            response,
            "Первый тестовый вопрос",
        )

        self.assertContains(
            response,
            "systemctl status nginx",
        )

    def test_question_renders_diagnostic_blocks(
        self,
    ):
        self.first.diagnostic_data = (
            "СТАРЫЕ ДАННЫЕ НЕ ПОКАЗЫВАТЬ"
        )

        self.first.diagnostic_blocks = [
            {
                "type": "text",
                "content": (
                    "В журнале nginx "
                    "во время проблемы:"
                ),
            },
            {
                "type": "code",
                "content": (
                    "2026/08/21 14:03:18 "
                    "upstream timed out"
                ),
            },
            {
                "type": "text",
                "content": "Параметры пула:",
            },
            {
                "type": "code",
                "content": (
                    "pm = dynamic\n"
                    "pm.max_children = 5"
                ),
            },
        ]

        self.first.save(
            update_fields=[
                "diagnostic_data",
                "diagnostic_blocks",
            ]
        )

        response = self.client.get(
            reverse(
                "assessment:attempt_question",
                args=[self.attempt.pk],
            )
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        self.assertContains(
            response,
            "В журнале nginx",
        )

        self.assertContains(
            response,
            "upstream timed out",
        )

        self.assertContains(
            response,
            "Параметры пула:",
        )

        self.assertContains(
            response,
            "pm.max_children = 5",
        )

        self.assertNotContains(
            response,
            "СТАРЫЕ ДАННЫЕ НЕ ПОКАЗЫВАТЬ",
        )

    def test_question_falls_back_to_legacy_diagnostic_data(
        self,
    ):
        self.first.diagnostic_blocks = []

        self.first.diagnostic_data = (
            "legacy diagnostic output\n"
            "nginx failed"
        )

        self.first.save(
            update_fields=[
                "diagnostic_blocks",
                "diagnostic_data",
            ]
        )

        response = self.client.get(
            reverse(
                "assessment:attempt_question",
                args=[self.attempt.pk],
            )
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        self.assertContains(
            response,
            "legacy diagnostic output",
        )

        self.assertContains(
            response,
            "nginx failed",
        )

    def test_answer_moves_to_next_question(
        self,
    ):
        self.first.started_at = timezone.now()

        self.first.save(
            update_fields=["started_at"]
        )

        response = self.client.post(
            reverse(
                "assessment:submit_question_answer",
                args=[
                    self.attempt.pk,
                    self.first.pk,
                ],
            ),
            {
                "selected_keys": "option-1",
            },
        )

        self.assertRedirects(
            response,
            reverse(
                "assessment:attempt_question",
                args=[self.attempt.pk],
            ),
        )

        self.assertTrue(
            hasattr(
                self.first,
                "answer",
            )
        )

    def test_expired_question_gets_timeout_and_moves_on(
        self,
    ):
        now = timezone.now()

        self.first.started_at = (
            now - timedelta(seconds=100)
        )

        self.first.save(
            update_fields=["started_at"]
        )

        current = open_current_question(
            self.attempt,
            now=now,
        )

        self.first.refresh_from_db()
        self.second.refresh_from_db()

        answer = self.first.answer

        self.assertTrue(
            answer.timed_out,
        )

        self.assertEqual(
            str(answer.score_percentage),
            "0.00",
        )

        self.assertEqual(
            current.pk,
            self.second.pk,
        )

        self.assertIsNotNone(
            self.second.started_at,
        )

    def test_last_answer_completes_attempt(
        self,
    ):
        self.first.started_at = timezone.now()

        self.first.save(
            update_fields=["started_at"]
        )

        self.client.post(
            reverse(
                "assessment:submit_question_answer",
                args=[
                    self.attempt.pk,
                    self.first.pk,
                ],
            ),
            {
                "selected_keys": "option-1",
            },
        )

        self.second.started_at = timezone.now()

        self.second.save(
            update_fields=["started_at"]
        )

        response = self.client.post(
            reverse(
                "assessment:submit_question_answer",
                args=[
                    self.attempt.pk,
                    self.second.pk,
                ],
            ),
            {
                "selected_keys": "option-1",
            },
        )

        self.assertRedirects(
            response,
            reverse(
                "assessment:attempt_overview",
                args=[self.attempt.pk],
            ),
        )

        self.attempt.refresh_from_db()

        self.assertEqual(
            self.attempt.status,
            ExamAttemptStatus.COMPLETED,
        )

        self.assertTrue(
            hasattr(
                self.attempt,
                "result",
            )
        )
