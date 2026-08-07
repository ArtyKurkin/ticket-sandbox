from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.test import TestCase
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
from assessment.services.answers import (
    submit_exam_answer,
)


class ExamAnswerSubmissionTests(TestCase):
    def setUp(self):
        user = User.objects.create_user(
            username="answer-user",
        )

        employee = SupportProfile.objects.create(
            user=user,
            level=SupportLevel.L1,
        )

        blueprint = ExamBlueprint.objects.create(
            name="Шаблон ответа",
            slug="test-answer-blueprint",
            level=SupportLevel.L1,
        )

        campaign = AssessmentCampaign.objects.create(
            name="Кампания ответа",
            slug="test-answer-campaign",
            blueprint=blueprint,
        )

        assignment = ExamAssignment.objects.create(
            campaign=campaign,
            employee=employee,
        )

        self.attempt = ExamAttempt.objects.create(
            assignment=assignment,
            attempt_number=1,
            selection_seed="answer-seed",
            campaign_name=campaign.name,
            blueprint_name=blueprint.name,
            level=SupportLevel.L1,
            pass_percentage=85,
            allow_back_navigation=False,
            shuffle_questions=True,
            shuffle_answer_options=True,
        )

        self.snapshot = ExamQuestionSnapshot.objects.create(
            attempt=self.attempt,
            position=1,
            topic_name="Linux",
            topic_slug="test-answer-linux",
            skill_name="Тестовый навык",
            skill_slug="test-answer-skill",
            family_name="Тестовое семейство",
            family_slug="test-answer-family",
            question_title="Тестовый вопрос",
            question_slug="test-answer-question",
            question_type=QuestionType.SINGLE_CHOICE,
            difficulty=QuestionDifficulty.HARD,
            prompt="Выбери ответ.",
            time_limit_seconds=90,
            started_at=timezone.now(),
            visible_payload={
                "options": [
                    {
                        "key": "option-1",
                        "text": "Правильно",
                    },
                    {
                        "key": "option-2",
                        "text": "Неправильно",
                    },
                ],
            },
            grading_payload={
                "correct_keys": [
                    "option-1",
                ],
            },
        )

    def test_correct_answer_is_saved(self):
        answer, created = submit_exam_answer(
            self.snapshot,
            response_payload={
                "selected_keys": [
                    "option-1",
                ],
            },
        )

        self.assertTrue(created)
        self.assertTrue(answer.is_correct)

        self.assertEqual(
            str(answer.score_percentage),
            "100.00",
        )

    def test_incorrect_answer_is_saved(self):
        answer, _ = submit_exam_answer(
            self.snapshot,
            response_payload={
                "selected_keys": [
                    "option-2",
                ],
            },
        )

        self.assertFalse(answer.is_correct)

        self.assertEqual(
            str(answer.score_percentage),
            "0.00",
        )

    def test_answer_cannot_be_submitted_twice(self):
        submit_exam_answer(
            self.snapshot,
            response_payload={
                "selected_keys": [
                    "option-1",
                ],
            },
        )

        with self.assertRaises(ValidationError):
            submit_exam_answer(
                self.snapshot,
                response_payload={
                    "selected_keys": [
                        "option-2",
                    ],
                },
            )

    def test_completed_attempt_rejects_answers(self):
        self.attempt.status = (
            ExamAttemptStatus.COMPLETED
        )

        self.attempt.save(
            update_fields=["status"]
        )

        with self.assertRaises(ValidationError):
            submit_exam_answer(
                self.snapshot,
                response_payload={
                    "selected_keys": [
                        "option-1",
                    ],
                },
            )

    def test_back_navigation_allows_answer_update(self):
        self.attempt.allow_back_navigation = True

        self.attempt.save(
            update_fields=[
                "allow_back_navigation",
            ]
        )

        first_answer, first_created = (
            submit_exam_answer(
                self.snapshot,
                response_payload={
                    "selected_keys": [
                        "option-2",
                    ],
                },
            )
        )

        second_answer, second_created = (
            submit_exam_answer(
                self.snapshot,
                response_payload={
                    "selected_keys": [
                        "option-1",
                    ],
                },
            )
        )

        self.assertTrue(first_created)
        self.assertFalse(second_created)

        self.assertEqual(
            first_answer.pk,
            second_answer.pk,
        )

        self.assertTrue(
            second_answer.is_correct,
        )
