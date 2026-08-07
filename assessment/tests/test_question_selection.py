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
from assessment.services.question_selection import (
    select_questions_for_blueprint,
)


class QuestionSelectionTests(TestCase):
    def setUp(self):
        self.topic = Topic.objects.create(
            name="Тестовая тема выбора",
            slug="test-selection-topic",
            order=300,
        )

        self.skill = Skill.objects.create(
            topic=self.topic,
            name="Тестовый навык выбора",
            slug="test-selection-skill",
            order=10,
        )

        self.blueprint = ExamBlueprint.objects.create(
            name="Тестовый шаблон выбора",
            slug="test-selection-blueprint",
            level=SupportLevel.L1,
            shuffle_questions=True,
        )

        BlueprintSkillQuota.objects.create(
            blueprint=self.blueprint,
            skill=self.skill,
            question_count=2,
            order=10,
        )

        self.first_family = (
            QuestionFamily.objects.create(
                skill=self.skill,
                name="Первое семейство",
                slug="test-selection-family-one",
                assessment_goal="Первое знание.",
                order=10,
            )
        )

        self.second_family = (
            QuestionFamily.objects.create(
                skill=self.skill,
                name="Второе семейство",
                slug="test-selection-family-two",
                assessment_goal="Второе знание.",
                order=20,
            )
        )

        self.third_family = (
            QuestionFamily.objects.create(
                skill=self.skill,
                name="Третье семейство",
                slug="test-selection-family-three",
                assessment_goal="Третье знание.",
                order=30,
            )
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
            prompt="Что необходимо сделать?",
        )

    def seed_question_bank(self):
        self.create_question(
            family=self.first_family,
            slug="family-one-variant-one",
        )

        self.create_question(
            family=self.first_family,
            slug="family-one-variant-two",
        )

        self.create_question(
            family=self.second_family,
            slug="family-two-variant-one",
        )

        self.create_question(
            family=self.second_family,
            slug="family-two-variant-two",
        )

        self.create_question(
            family=self.third_family,
            slug="family-three-variant-one",
        )

    def test_selection_respects_skill_quota(self):
        self.seed_question_bank()

        selected = select_questions_for_blueprint(
            self.blueprint,
            seed="attempt-1",
        )

        self.assertEqual(
            len(selected),
            2,
        )

    def test_selection_uses_distinct_families(self):
        self.seed_question_bank()

        selected = select_questions_for_blueprint(
            self.blueprint,
            seed="attempt-2",
        )

        family_ids = {
            question.family_id
            for question in selected
        }

        self.assertEqual(
            len(family_ids),
            2,
        )

    def test_same_seed_returns_same_questions(self):
        self.seed_question_bank()

        first_selection = (
            select_questions_for_blueprint(
                self.blueprint,
                seed="same-attempt",
            )
        )

        second_selection = (
            select_questions_for_blueprint(
                self.blueprint,
                seed="same-attempt",
            )
        )

        self.assertEqual(
            [
                question.id
                for question in first_selection
            ],
            [
                question.id
                for question in second_selection
            ],
        )

    def test_draft_questions_are_not_selected(self):
        self.create_question(
            family=self.first_family,
            slug="active-one",
        )

        self.create_question(
            family=self.second_family,
            slug="active-two",
        )

        draft_question = self.create_question(
            family=self.third_family,
            slug="draft-question",
            status=QuestionStatus.DRAFT,
        )

        selected = select_questions_for_blueprint(
            self.blueprint,
            seed="draft-check",
        )

        self.assertNotIn(
            draft_question,
            selected,
        )

    def test_question_for_another_level_is_not_selected(
        self,
    ):
        self.create_question(
            family=self.first_family,
            slug="active-l1-one",
        )

        self.create_question(
            family=self.second_family,
            slug="active-l1-two",
        )

        l2_question = self.create_question(
            family=self.third_family,
            slug="l2-question",
            level=SupportLevel.L2,
        )

        selected = select_questions_for_blueprint(
            self.blueprint,
            seed="level-check",
        )

        self.assertNotIn(
            l2_question,
            selected,
        )

    def test_inactive_family_is_not_selected(self):
        self.create_question(
            family=self.first_family,
            slug="active-family-one",
        )

        self.create_question(
            family=self.second_family,
            slug="active-family-two",
        )

        self.third_family.is_active = False
        self.third_family.save(
            update_fields=["is_active"]
        )

        inactive_family_question = (
            self.create_question(
                family=self.third_family,
                slug="inactive-family-question",
            )
        )

        selected = select_questions_for_blueprint(
            self.blueprint,
            seed="inactive-family-check",
        )

        self.assertNotIn(
            inactive_family_question,
            selected,
        )

    def test_insufficient_bank_raises_validation_error(
        self,
    ):
        self.create_question(
            family=self.first_family,
            slug="only-question",
        )

        with self.assertRaises(ValidationError):
            select_questions_for_blueprint(
                self.blueprint,
                seed="not-enough",
            )


class QuestionSelectionOrderingTests(TestCase):
    def setUp(self):
        self.topic = Topic.objects.create(
            name="Тестовая тема порядка",
            slug="test-selection-order-topic",
            order=400,
        )

        self.first_skill = Skill.objects.create(
            topic=self.topic,
            name="Первый навык",
            slug="test-selection-first-skill",
            order=10,
        )

        self.second_skill = Skill.objects.create(
            topic=self.topic,
            name="Второй навык",
            slug="test-selection-second-skill",
            order=20,
        )

        self.blueprint = ExamBlueprint.objects.create(
            name="Шаблон без перемешивания",
            slug="test-selection-no-shuffle",
            level=SupportLevel.L1,
            shuffle_questions=False,
        )

        BlueprintSkillQuota.objects.create(
            blueprint=self.blueprint,
            skill=self.first_skill,
            question_count=1,
            order=10,
        )

        BlueprintSkillQuota.objects.create(
            blueprint=self.blueprint,
            skill=self.second_skill,
            question_count=1,
            order=20,
        )

        first_family = QuestionFamily.objects.create(
            skill=self.first_skill,
            name="Семейство первого навыка",
            slug="test-first-skill-family",
            assessment_goal="Первый навык.",
        )

        second_family = QuestionFamily.objects.create(
            skill=self.second_skill,
            name="Семейство второго навыка",
            slug="test-second-skill-family",
            assessment_goal="Второй навык.",
        )

        self.first_question = Question.objects.create(
            family=first_family,
            title="Первый вопрос",
            slug="test-first-skill-question",
            level=SupportLevel.L1,
            status=QuestionStatus.ACTIVE,
            prompt="Первый вопрос.",
        )

        self.second_question = Question.objects.create(
            family=second_family,
            title="Второй вопрос",
            slug="test-second-skill-question",
            level=SupportLevel.L1,
            status=QuestionStatus.ACTIVE,
            prompt="Второй вопрос.",
        )

    def test_questions_keep_quota_order_when_shuffle_disabled(
        self,
    ):
        selected = select_questions_for_blueprint(
            self.blueprint,
            seed="ordered-attempt",
        )

        self.assertEqual(
            selected,
            [
                self.first_question,
                self.second_question,
            ],
        )
