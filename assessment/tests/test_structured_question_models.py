from django.test import TestCase

from assessment.constants import (
    QuestionType,
    SupportLevel,
)
from assessment.models import (
    MatchingPair,
    OrderingItem,
    Question,
    QuestionFamily,
    SelectableLine,
    Skill,
    Topic,
)


class StructuredQuestionModelTests(TestCase):
    def setUp(self):
        topic = Topic.objects.create(
            name="Тестовая структурированная тема",
            slug="test-structured-topic",
            order=200,
        )

        skill = Skill.objects.create(
            topic=topic,
            name="Тестовый структурированный навык",
            slug="test-structured-skill",
        )

        family = QuestionFamily.objects.create(
            skill=skill,
            name="Тестовое структурированное семейство",
            slug="test-structured-family",
            assessment_goal="Проверка новых форматов.",
        )

        self.question = Question.objects.create(
            family=family,
            title="Тестовый структурированный вопрос",
            slug="test-structured-question",
            level=SupportLevel.L1,
            answer_type=QuestionType.MATCHING,
            prompt="Выполни задание.",
        )

    def test_matching_pairs_use_configured_order(self):
        second = MatchingPair.objects.create(
            question=self.question,
            left_text="Второй симптом",
            right_text="Вторая причина",
            order=20,
        )

        first = MatchingPair.objects.create(
            question=self.question,
            left_text="Первый симптом",
            right_text="Первая причина",
            order=10,
        )

        self.assertEqual(
            list(self.question.matching_pairs.all()),
            [
                first,
                second,
            ],
        )

    def test_ordering_items_use_configured_order(self):
        second = OrderingItem.objects.create(
            question=self.question,
            text="Второй шаг",
            order=20,
        )

        first = OrderingItem.objects.create(
            question=self.question,
            text="Первый шаг",
            order=10,
        )

        self.assertEqual(
            list(self.question.ordering_items.all()),
            [
                first,
                second,
            ],
        )

    def test_selectable_lines_store_correct_value(self):
        line = SelectableLine.objects.create(
            question=self.question,
            text="Строка с ошибкой",
            is_correct=True,
            order=10,
        )

        self.assertTrue(line.is_correct)
        self.assertEqual(
            str(line),
            "Строка с ошибкой",
        )
