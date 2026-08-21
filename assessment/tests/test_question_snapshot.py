from django.test import TestCase

from assessment.constants import (
    DiagnosticBlockType,
    QuestionStatus,
    QuestionType,
    SupportLevel,
)
from assessment.models import (
    AnswerOption,
    MatchingPair,
    OrderingItem,
    Question,
    QuestionDiagnosticBlock,
    QuestionFamily,
    SelectableLine,
    Skill,
    Topic,
)
from assessment.services.question_snapshot import (
    build_question_snapshot_data,
)


class QuestionSnapshotTests(TestCase):
    def setUp(self):
        topic = Topic.objects.create(
            name="Тема snapshot",
            slug="test-snapshot-topic",
            order=600,
        )

        skill = Skill.objects.create(
            topic=topic,
            name="Навык snapshot",
            slug="test-snapshot-skill",
        )

        self.family = QuestionFamily.objects.create(
            skill=skill,
            name="Семейство snapshot",
            slug="test-snapshot-family",
            assessment_goal="Проверить snapshot.",
        )

    def create_question(
        self,
        *,
        slug,
        answer_type,
    ):
        return Question.objects.create(
            family=self.family,
            title=slug,
            slug=slug,
            level=SupportLevel.L1,
            status=QuestionStatus.ACTIVE,
            answer_type=answer_type,
            prompt="Выполни задание.",
        )

    def test_single_choice_snapshot(self):
        question = self.create_question(
            slug="snapshot-single",
            answer_type=QuestionType.SINGLE_CHOICE,
        )

        AnswerOption.objects.create(
            question=question,
            text="Правильно",
            is_correct=True,
            order=10,
        )

        AnswerOption.objects.create(
            question=question,
            text="Неправильно",
            is_correct=False,
            order=20,
        )

        data = build_question_snapshot_data(
            question,
            seed="single",
            shuffle_answer_options=True,
        )

        self.assertEqual(
            len(
                data["visible_payload"]["options"]
            ),
            2,
        )

        self.assertEqual(
            len(
                data["grading_payload"][
                    "correct_keys"
                ]
            ),
            1,
        )

    def test_matching_snapshot(self):
        question = self.create_question(
            slug="snapshot-matching",
            answer_type=QuestionType.MATCHING,
        )

        MatchingPair.objects.create(
            question=question,
            left_text="OOM Killer",
            right_text="Нехватка памяти",
            order=10,
        )

        MatchingPair.objects.create(
            question=question,
            left_text="Высокий await",
            right_text="Проблема с диском",
            order=20,
        )

        data = build_question_snapshot_data(
            question,
            seed="matching",
            shuffle_answer_options=True,
        )

        self.assertEqual(
            len(
                data["grading_payload"]["matches"]
            ),
            2,
        )

    def test_ordering_snapshot(self):
        question = self.create_question(
            slug="snapshot-ordering",
            answer_type=QuestionType.ORDERING,
        )

        for order, text in (
            (10, "Первый шаг"),
            (20, "Второй шаг"),
            (30, "Третий шаг"),
        ):
            OrderingItem.objects.create(
                question=question,
                text=text,
                order=order,
            )

        data = build_question_snapshot_data(
            question,
            seed="ordering",
            shuffle_answer_options=True,
        )

        self.assertEqual(
            data["grading_payload"][
                "correct_order"
            ],
            [
                "item-1",
                "item-2",
                "item-3",
            ],
        )

    def test_line_selection_keeps_original_order(self):
        question = self.create_question(
            slug="snapshot-lines",
            answer_type=QuestionType.LINE_SELECTION,
        )

        SelectableLine.objects.create(
            question=question,
            text="line 1",
            is_correct=False,
            order=10,
        )

        SelectableLine.objects.create(
            question=question,
            text="line 2 error",
            is_correct=True,
            order=20,
        )

        SelectableLine.objects.create(
            question=question,
            text="line 3",
            is_correct=False,
            order=30,
        )

        data = build_question_snapshot_data(
            question,
            seed="lines",
            shuffle_answer_options=True,
        )

        texts = [
            line["text"]
            for line in data[
                "visible_payload"
            ]["lines"]
        ]

        self.assertEqual(
            texts,
            [
                "line 1",
                "line 2 error",
                "line 3",
            ],
        )

    def test_snapshot_contains_diagnostic_blocks(self):
        question = self.create_question(
            slug="snapshot-diagnostic-blocks",
            answer_type=QuestionType.SINGLE_CHOICE,
        )

        AnswerOption.objects.create(
            question=question,
            text="Правильно",
            is_correct=True,
            order=10,
        )

        AnswerOption.objects.create(
            question=question,
            text="Неправильно",
            is_correct=False,
            order=20,
        )

        QuestionDiagnosticBlock.objects.create(
            question=question,
            block_type=DiagnosticBlockType.TEXT,
            content="В журнале nginx:",
            order=10,
        )

        QuestionDiagnosticBlock.objects.create(
            question=question,
            block_type=DiagnosticBlockType.CODE,
            content=(
                "upstream timed out "
                "while reading response header"
            ),
            order=20,
        )

        data = build_question_snapshot_data(
            question,
            seed="test-seed",
            shuffle_answer_options=False,
        )

        self.assertEqual(
            data["diagnostic_blocks"],
            [
                {
                    "type": DiagnosticBlockType.TEXT,
                    "content": "В журнале nginx:",
                },
                {
                    "type": DiagnosticBlockType.CODE,
                    "content": (
                        "upstream timed out "
                        "while reading response header"
                    ),
                },
            ],
        )
