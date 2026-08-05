from django.core.exceptions import ValidationError
from django.test import TestCase

from assessment.constants import (
    QuestionDifficulty,
    QuestionStatus,
    QuestionType,
    SupportLevel,
)
from assessment.models import (
    AnswerOption,
    Question,
    QuestionFamily,
    Skill,
    Topic,
)


class QuestionModelTests(TestCase):
    def setUp(self):
        self.topic = Topic.objects.create(
            name="Тестовая тематика вопросов",
            slug="test-question-topic",
            order=100,
        )

        self.skill = Skill.objects.create(
            topic=self.topic,
            name="Тестовый навык",
            slug="test-question-skill",
        )

        self.family = QuestionFamily.objects.create(
            skill=self.skill,
            name="Тестовое семейство",
            slug="test-question-family",
            assessment_goal=(
                "Проверить работу модели вопроса."
            ),
        )

        self.question = Question.objects.create(
            family=self.family,
            title="Удалённый открытый файл",
            slug="deleted-open-file",
            level=SupportLevel.L1,
            scenario=(
                "После удаления большого журнала "
                "место на диске не освободилось."
            ),
            diagnostic_data=(
                "df -h: 100%\n"
                "du -sh /var/log: 2G"
            ),
            prompt=(
                "Что необходимо проверить дальше?"
            ),
        )

    def test_question_is_draft_by_default(self):
        self.assertEqual(
            self.question.status,
            QuestionStatus.DRAFT,
        )

    def test_question_is_hard_by_default(self):
        self.assertEqual(
            self.question.difficulty,
            QuestionDifficulty.HARD,
        )

    def test_question_uses_single_choice_by_default(self):
        self.assertEqual(
            self.question.answer_type,
            QuestionType.SINGLE_CHOICE,
        )

    def test_question_uses_ninety_second_limit_by_default(self):
        self.assertEqual(
            self.question.time_limit_seconds,
            90,
        )

    def test_question_string_contains_full_path(self):
        self.assertEqual(
            str(self.question),
            (
                "Тестовая тематика вопросов "
                "→ Тестовый навык "
                "→ Тестовое семейство "
                "→ Удалённый открытый файл"
            ),
        )

    def test_time_limit_cannot_be_lower_than_thirty_seconds(self):
        self.question.time_limit_seconds = 10

        with self.assertRaises(ValidationError):
            self.question.full_clean()

    def test_time_limit_cannot_be_greater_than_five_minutes(self):
        self.question.time_limit_seconds = 301

        with self.assertRaises(ValidationError):
            self.question.full_clean()

    def test_answer_options_use_configured_order(self):
        second_option = AnswerOption.objects.create(
            question=self.question,
            text="Перезапустить сервер.",
            order=20,
        )

        first_option = AnswerOption.objects.create(
            question=self.question,
            text="Проверить открытые удалённые файлы.",
            is_correct=True,
            order=10,
        )

        self.assertEqual(
            list(self.question.answer_options.all()),
            [
                first_option,
                second_option,
            ],
        )

    def test_answer_option_string_contains_text(self):
        option = AnswerOption.objects.create(
            question=self.question,
            text="Проверить lsof.",
            is_correct=True,
        )

        self.assertEqual(
            str(option),
            "Проверить lsof.",
        )

    def test_all_question_levels_are_available(self):
        self.assertEqual(
            set(SupportLevel.values),
            {
                SupportLevel.L1,
                SupportLevel.L2,
                SupportLevel.PRIME,
            },
        )
