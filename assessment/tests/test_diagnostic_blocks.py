from django.test import TestCase

from assessment.constants import (
    DiagnosticBlockType,
    QuestionDifficulty,
    QuestionStatus,
    QuestionType,
    SupportLevel,
)
from assessment.models import (
    Question,
    QuestionDiagnosticBlock,
    QuestionFamily,
    Skill,
    Topic,
)


class QuestionDiagnosticBlockTests(TestCase):
    def setUp(self):
        self.topic = Topic.objects.create(
            name="Тестовая диагностика",
            slug="test-diagnostic-topic",
            order=900,
        )

        self.skill = Skill.objects.create(
            topic=self.topic,
            name="Тестовый навык",
            slug="test-diagnostic-skill",
            order=900,
        )

        self.family = QuestionFamily.objects.create(
            skill=self.skill,
            name="Тестовое семейство",
            slug="test-diagnostic-family",
            assessment_goal=(
                "Проверка диагностических блоков."
            ),
            order=900,
        )

        self.question = Question.objects.create(
            family=self.family,
            title="Тестовый вопрос",
            slug="test-diagnostic-question",
            level=SupportLevel.L1,
            difficulty=QuestionDifficulty.MEDIUM,
            answer_type=QuestionType.SINGLE_CHOICE,
            status=QuestionStatus.DRAFT,
            prompt="Что произошло?",
        )

    def test_blocks_are_ordered(self):
        second = (
            QuestionDiagnosticBlock.objects.create(
                question=self.question,
                block_type=DiagnosticBlockType.CODE,
                content="$ systemctl status nginx",
                order=20,
            )
        )

        first = (
            QuestionDiagnosticBlock.objects.create(
                question=self.question,
                block_type=DiagnosticBlockType.TEXT,
                content="Состояние nginx:",
                order=10,
            )
        )

        blocks = list(
            self.question.diagnostic_blocks.all()
        )

        self.assertEqual(
            blocks,
            [
                first,
                second,
            ],
        )

    def test_blocks_are_deleted_with_question(self):
        QuestionDiagnosticBlock.objects.create(
            question=self.question,
            block_type=DiagnosticBlockType.CODE,
            content="$ free -h",
            order=10,
        )

        self.question.delete()

        self.assertFalse(
            QuestionDiagnosticBlock.objects.exists()
        )
