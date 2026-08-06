from django.core.exceptions import ValidationError
from django.test import TestCase

from assessment.constants import (
    QuestionStatus,
    SupportLevel,
)
from assessment.models import (
    BlueprintSkillQuota,
    ExamBlueprint,
    Question,
    QuestionFamily,
    Skill,
    Topic,
)
from assessment.services.blueprint_validation import (
    get_blueprint_pool_status,
    validate_blueprint_question_pool,
)


class BlueprintQuestionPoolTests(TestCase):
    def setUp(self):
        self.topic = Topic.objects.create(
            name="Тестовая тема банка",
            slug="test-blueprint-pool-topic",
            order=200,
        )

        self.skill = Skill.objects.create(
            topic=self.topic,
            name="Тестовый навык банка",
            slug="test-blueprint-pool-skill",
        )

        self.first_family = QuestionFamily.objects.create(
            skill=self.skill,
            name="Первое тестовое семейство",
            slug="test-pool-family-one",
            assessment_goal="Первое проверяемое знание.",
        )

        self.second_family = QuestionFamily.objects.create(
            skill=self.skill,
            name="Второе тестовое семейство",
            slug="test-pool-family-two",
            assessment_goal="Второе проверяемое знание.",
        )

        self.blueprint = ExamBlueprint.objects.create(
            name="Тестовый шаблон банка",
            slug="test-pool-blueprint",
            level=SupportLevel.L1,
        )

        self.quota = BlueprintSkillQuota.objects.create(
            blueprint=self.blueprint,
            skill=self.skill,
            question_count=2,
        )

    def create_question(
        self,
        *,
        family,
        slug,
        level=SupportLevel.L1,
        status=QuestionStatus.ACTIVE,
    ):
        return Question.objects.create(
            family=family,
            title=slug,
            slug=slug,
            level=level,
            status=status,
            prompt="Выбери правильный ответ.",
        )

    def test_pool_counts_distinct_families(self):
        self.create_question(
            family=self.first_family,
            slug="first-family-variant-one",
        )

        self.create_question(
            family=self.first_family,
            slug="first-family-variant-two",
        )

        pool_status = get_blueprint_pool_status(
            self.blueprint,
        )

        self.assertEqual(
            pool_status[0]["available_family_count"],
            1,
        )
        self.assertFalse(
            pool_status[0]["is_sufficient"],
        )

    def test_active_questions_from_different_families_are_counted(
        self,
    ):
        self.create_question(
            family=self.first_family,
            slug="first-active-question",
        )

        self.create_question(
            family=self.second_family,
            slug="second-active-question",
        )

        pool_status = get_blueprint_pool_status(
            self.blueprint,
        )

        self.assertEqual(
            pool_status[0]["available_family_count"],
            2,
        )
        self.assertTrue(
            pool_status[0]["is_sufficient"],
        )

    def test_draft_question_is_not_counted(self):
        self.create_question(
            family=self.first_family,
            slug="draft-question",
            status=QuestionStatus.DRAFT,
        )

        pool_status = get_blueprint_pool_status(
            self.blueprint,
        )

        self.assertEqual(
            pool_status[0]["available_family_count"],
            0,
        )

    def test_question_for_another_level_is_not_counted(self):
        self.create_question(
            family=self.first_family,
            slug="l2-question",
            level=SupportLevel.L2,
        )

        pool_status = get_blueprint_pool_status(
            self.blueprint,
        )

        self.assertEqual(
            pool_status[0]["available_family_count"],
            0,
        )

    def test_valid_blueprint_pool_passes_validation(self):
        self.create_question(
            family=self.first_family,
            slug="first-valid-question",
        )

        self.create_question(
            family=self.second_family,
            slug="second-valid-question",
        )

        result = validate_blueprint_question_pool(
            self.blueprint,
        )

        self.assertTrue(
            result[0]["is_sufficient"],
        )

    def test_shortage_raises_validation_error(self):
        self.create_question(
            family=self.first_family,
            slug="only-available-question",
        )

        with self.assertRaises(ValidationError):
            validate_blueprint_question_pool(
                self.blueprint,
            )
