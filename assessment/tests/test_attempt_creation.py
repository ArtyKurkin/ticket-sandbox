from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.test import TestCase

from assessment.constants import (
    QuestionStatus,
    SupportLevel,
)
from assessment.models import (
    AnswerOption,
    AssessmentCampaign,
    BlueprintSkillQuota,
    ExamAssignment,
    ExamBlueprint,
    Question,
    QuestionFamily,
    Skill,
    SupportProfile,
    Topic,
)
from assessment.services.attempts import (
    start_exam_attempt,
)


class ExamAttemptCreationTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="attempt-user",
            first_name="Иван",
            last_name="Иванов",
        )

        self.employee = SupportProfile.objects.create(
            user=self.user,
            level=SupportLevel.L1,
        )

        self.topic = Topic.objects.create(
            name="Тестовая тема попытки",
            slug="test-attempt-topic",
            order=500,
        )

        self.skill = Skill.objects.create(
            topic=self.topic,
            name="Тестовый навык попытки",
            slug="test-attempt-skill",
        )

        self.family = QuestionFamily.objects.create(
            skill=self.skill,
            name="Тестовое семейство попытки",
            slug="test-attempt-family",
            assessment_goal="Проверить создание попытки.",
        )

        self.question = Question.objects.create(
            family=self.family,
            title="Тестовый вопрос попытки",
            slug="test-attempt-question",
            level=SupportLevel.L1,
            status=QuestionStatus.ACTIVE,
            scenario="Сайт недоступен.",
            prompt="Что проверим?",
        )

        AnswerOption.objects.create(
            question=self.question,
            text="Правильный ответ",
            is_correct=True,
            order=10,
        )

        AnswerOption.objects.create(
            question=self.question,
            text="Неправильный ответ",
            is_correct=False,
            order=20,
        )

        self.blueprint = ExamBlueprint.objects.create(
            name="Активный тестовый шаблон",
            slug="test-active-attempt-blueprint",
            level=SupportLevel.L1,
            is_active=True,
        )

        BlueprintSkillQuota.objects.create(
            blueprint=self.blueprint,
            skill=self.skill,
            question_count=1,
        )

        self.campaign = AssessmentCampaign.objects.create(
            name="Активная тестовая кампания",
            slug="test-active-attempt-campaign",
            blueprint=self.blueprint,
            is_active=True,
        )

        self.assignment = ExamAssignment.objects.create(
            campaign=self.campaign,
            employee=self.employee,
        )

    def test_start_creates_attempt(self):
        attempt, created = start_exam_attempt(
            self.assignment,
            seed="attempt-seed",
        )

        self.assertTrue(created)
        self.assertEqual(
            attempt.attempt_number,
            1,
        )

    def test_start_creates_question_snapshot(self):
        attempt, _ = start_exam_attempt(
            self.assignment,
            seed="snapshot-seed",
        )

        self.assertEqual(
            attempt.question_snapshots.count(),
            1,
        )

        snapshot = (
            attempt.question_snapshots.get()
        )

        self.assertEqual(
            snapshot.prompt,
            "Что проверим?",
        )

        self.assertEqual(
            snapshot.skill_slug,
            "test-attempt-skill",
        )

    def test_snapshot_does_not_change_with_source_question(
        self,
    ):
        attempt, _ = start_exam_attempt(
            self.assignment,
            seed="immutable-seed",
        )

        snapshot = (
            attempt.question_snapshots.get()
        )

        self.question.prompt = (
            "Полностью новый текст вопроса."
        )

        self.question.save(
            update_fields=["prompt"]
        )

        snapshot.refresh_from_db()

        self.assertEqual(
            snapshot.prompt,
            "Что проверим?",
        )

    def test_second_start_returns_existing_attempt(self):
        first_attempt, first_created = (
            start_exam_attempt(
                self.assignment,
                seed="first-seed",
            )
        )

        second_attempt, second_created = (
            start_exam_attempt(
                self.assignment,
                seed="second-seed",
            )
        )

        self.assertTrue(first_created)
        self.assertFalse(second_created)

        self.assertEqual(
            first_attempt.pk,
            second_attempt.pk,
        )

        self.assertEqual(
            self.assignment.attempts.count(),
            1,
        )

    def test_attempt_limit_is_enforced(self):
        attempt, _ = start_exam_attempt(
            self.assignment,
            seed="first-attempt",
        )

        attempt.status = "completed"
        attempt.save(
            update_fields=["status"]
        )

        with self.assertRaises(ValidationError):
            start_exam_attempt(
                self.assignment,
                seed="second-attempt",
            )

    def test_inactive_campaign_cannot_start_attempt(self):
        self.campaign.is_active = False
        self.campaign.save(
            update_fields=["is_active"]
        )

        with self.assertRaises(ValidationError):
            start_exam_attempt(
                self.assignment,
                seed="inactive-campaign",
            )
