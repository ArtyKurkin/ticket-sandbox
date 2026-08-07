from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.test import TestCase

from assessment.constants import (
    ExamAttemptStatus,
    QuestionDifficulty,
    QuestionType,
    SupportLevel,
)
from assessment.models import (
    AssessmentCampaign,
    ExamAnswer,
    ExamAssignment,
    ExamAttempt,
    ExamBlueprint,
    ExamQuestionSnapshot,
    SupportProfile,
)
from assessment.services.results import (
    complete_exam_attempt,
)


class ExamAttemptCompletionTests(TestCase):
    def setUp(self):
        user = User.objects.create_user(
            username="result-user",
            first_name="Иван",
            last_name="Иванов",
        )

        employee = SupportProfile.objects.create(
            user=user,
            level=SupportLevel.L1,
        )

        blueprint = ExamBlueprint.objects.create(
            name="Шаблон результата",
            slug="test-result-blueprint",
            level=SupportLevel.L1,
            pass_percentage=85,
        )

        campaign = AssessmentCampaign.objects.create(
            name="Кампания результата",
            slug="test-result-campaign",
            blueprint=blueprint,
        )

        assignment = ExamAssignment.objects.create(
            campaign=campaign,
            employee=employee,
        )

        self.attempt = ExamAttempt.objects.create(
            assignment=assignment,
            attempt_number=1,
            selection_seed="result-seed",
            campaign_name=campaign.name,
            blueprint_name=blueprint.name,
            level=SupportLevel.L1,
            pass_percentage=85,
            allow_back_navigation=False,
            shuffle_questions=True,
            shuffle_answer_options=True,
        )

    def create_snapshot(
        self,
        *,
        position,
        topic_name,
        topic_slug,
        skill_name,
        skill_slug,
    ):
        return ExamQuestionSnapshot.objects.create(
            attempt=self.attempt,
            position=position,
            topic_name=topic_name,
            topic_slug=topic_slug,
            skill_name=skill_name,
            skill_slug=skill_slug,
            family_name=f"Семейство {position}",
            family_slug=f"family-{position}",
            question_title=f"Вопрос {position}",
            question_slug=f"question-{position}",
            question_type=QuestionType.SINGLE_CHOICE,
            difficulty=QuestionDifficulty.HARD,
            prompt="Выбери ответ.",
            time_limit_seconds=90,
            visible_payload={
                "options": [
                    {
                        "key": "option-1",
                        "text": "Ответ",
                    },
                ],
            },
            grading_payload={
                "correct_keys": [
                    "option-1",
                ],
            },
        )

    def create_answer(
        self,
        snapshot,
        *,
        score,
    ):
        return ExamAnswer.objects.create(
            snapshot=snapshot,
            response_payload={
                "selected_keys": [
                    "option-1",
                ],
            },
            score_percentage=score,
            is_correct=(score == 100),
        )

    def test_attempt_is_completed_and_result_created(
        self,
    ):
        first = self.create_snapshot(
            position=1,
            topic_name="Linux и VDS",
            topic_slug="linux-vds-test-result",
            skill_name="CPU",
            skill_slug="cpu-test-result",
        )

        second = self.create_snapshot(
            position=2,
            topic_name="Web",
            topic_slug="web-test-result",
            skill_name="PHP",
            skill_slug="php-test-result",
        )

        self.create_answer(
            first,
            score=100,
        )

        self.create_answer(
            second,
            score=100,
        )

        result, created = complete_exam_attempt(
            self.attempt
        )

        self.assertTrue(created)

        self.assertEqual(
            str(result.score_percentage),
            "100.00",
        )

        self.assertTrue(result.passed)

        self.attempt.refresh_from_db()

        self.assertEqual(
            self.attempt.status,
            ExamAttemptStatus.COMPLETED,
        )

        self.assertIsNotNone(
            self.attempt.completed_at,
        )

    def test_result_uses_average_question_score(self):
        first = self.create_snapshot(
            position=1,
            topic_name="Linux и VDS",
            topic_slug="linux-average",
            skill_name="Файловые системы",
            skill_slug="filesystem-average",
        )

        second = self.create_snapshot(
            position=2,
            topic_name="Linux и VDS",
            topic_slug="linux-average",
            skill_name="Нагрузка",
            skill_slug="load-average-result",
        )

        self.create_answer(
            first,
            score=100,
        )

        self.create_answer(
            second,
            score="66.67",
        )

        result, _ = complete_exam_attempt(
            self.attempt
        )

        self.assertEqual(
            str(result.score_percentage),
            "83.34",
        )

        self.assertFalse(
            result.passed,
        )

    def test_topic_breakdown_is_calculated(self):
        first = self.create_snapshot(
            position=1,
            topic_name="Linux и VDS",
            topic_slug="linux-breakdown",
            skill_name="CPU",
            skill_slug="cpu-breakdown",
        )

        second = self.create_snapshot(
            position=2,
            topic_name="Linux и VDS",
            topic_slug="linux-breakdown",
            skill_name="Диск",
            skill_slug="disk-breakdown",
        )

        self.create_answer(
            first,
            score=100,
        )

        self.create_answer(
            second,
            score=50,
        )

        result, _ = complete_exam_attempt(
            self.attempt
        )

        linux = result.topic_breakdown[
            "linux-breakdown"
        ]

        self.assertEqual(
            linux["question_count"],
            2,
        )

        self.assertEqual(
            linux["score_percentage"],
            "75.00",
        )

    def test_skill_breakdown_is_calculated(self):
        snapshot = self.create_snapshot(
            position=1,
            topic_name="Сети",
            topic_slug="networks-breakdown",
            skill_name="MTR",
            skill_slug="mtr-breakdown",
        )

        self.create_answer(
            snapshot,
            score="66.67",
        )

        result, _ = complete_exam_attempt(
            self.attempt
        )

        skill = result.skill_breakdown[
            "mtr-breakdown"
        ]

        self.assertEqual(
            skill["topic_name"],
            "Сети",
        )

        self.assertEqual(
            skill["score_percentage"],
            "66.67",
        )

    def test_unanswered_question_blocks_completion(
        self,
    ):
        self.create_snapshot(
            position=1,
            topic_name="Linux",
            topic_slug="linux-unanswered",
            skill_name="CPU",
            skill_slug="cpu-unanswered",
        )

        with self.assertRaises(ValidationError):
            complete_exam_attempt(
                self.attempt
            )

    def test_completed_attempt_is_idempotent(self):
        snapshot = self.create_snapshot(
            position=1,
            topic_name="Linux",
            topic_slug="linux-idempotent",
            skill_name="CPU",
            skill_slug="cpu-idempotent",
        )

        self.create_answer(
            snapshot,
            score=100,
        )

        first_result, first_created = (
            complete_exam_attempt(
                self.attempt
            )
        )

        second_result, second_created = (
            complete_exam_attempt(
                self.attempt
            )
        )

        self.assertTrue(first_created)
        self.assertFalse(second_created)

        self.assertEqual(
            first_result.pk,
            second_result.pk,
        )

    def test_invalidated_attempt_cannot_be_completed(
        self,
    ):
        self.attempt.status = (
            ExamAttemptStatus.INVALIDATED
        )

        self.attempt.save(
            update_fields=["status"]
        )

        with self.assertRaises(ValidationError):
            complete_exam_attempt(
                self.attempt
            )

    def test_result_uses_attempt_pass_percentage_snapshot(
        self,
    ):
        snapshot = self.create_snapshot(
            position=1,
            topic_name="Linux",
            topic_slug="linux-threshold",
            skill_name="CPU",
            skill_slug="cpu-threshold",
        )

        self.create_answer(
            snapshot,
            score=90,
        )

        self.attempt.assignment.campaign.blueprint.pass_percentage = 95

        self.attempt.assignment.campaign.blueprint.save(
            update_fields=["pass_percentage"]
        )

        result, _ = complete_exam_attempt(
            self.attempt
        )

        self.assertEqual(
            self.attempt.pass_percentage,
            85,
        )

        self.assertTrue(
            result.passed,
        )
