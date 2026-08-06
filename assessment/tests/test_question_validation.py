from django.core.exceptions import ValidationError
from django.test import SimpleTestCase

from assessment.constants import QuestionType
from assessment.question_validation import (
    validate_answer_configuration,
    validate_line_selection_configuration,
    validate_matching_configuration,
    validate_ordering_configuration,
)


class QuestionAnswerValidationTests(SimpleTestCase):
    def test_valid_single_choice_configuration(self):
        validate_answer_configuration(
            answer_type=QuestionType.SINGLE_CHOICE,
            options=[
                {
                    "text": "Правильный ответ",
                    "is_correct": True,
                },
                {
                    "text": "Неправильный ответ",
                    "is_correct": False,
                },
            ],
        )

    def test_single_choice_requires_exactly_one_correct_answer(
        self,
    ):
        with self.assertRaises(ValidationError):
            validate_answer_configuration(
                answer_type=QuestionType.SINGLE_CHOICE,
                options=[
                    {
                        "text": "Первый ответ",
                        "is_correct": True,
                    },
                    {
                        "text": "Второй ответ",
                        "is_correct": True,
                    },
                ],
            )

    def test_question_requires_at_least_two_options(self):
        with self.assertRaises(ValidationError):
            validate_answer_configuration(
                answer_type=QuestionType.SINGLE_CHOICE,
                options=[
                    {
                        "text": "Единственный ответ",
                        "is_correct": True,
                    },
                ],
            )

    def test_duplicate_options_are_not_allowed(self):
        with self.assertRaises(ValidationError):
            validate_answer_configuration(
                answer_type=QuestionType.SINGLE_CHOICE,
                options=[
                    {
                        "text": "Проверить журнал",
                        "is_correct": True,
                    },
                    {
                        "text": "  проверить   журнал ",
                        "is_correct": False,
                    },
                ],
            )

    def test_valid_multiple_choice_configuration(self):
        validate_answer_configuration(
            answer_type=QuestionType.MULTIPLE_CHOICE,
            options=[
                {
                    "text": "Первый правильный",
                    "is_correct": True,
                },
                {
                    "text": "Второй правильный",
                    "is_correct": True,
                },
                {
                    "text": "Неправильный",
                    "is_correct": False,
                },
            ],
        )

    def test_multiple_choice_requires_two_correct_answers(
        self,
    ):
        with self.assertRaises(ValidationError):
            validate_answer_configuration(
                answer_type=QuestionType.MULTIPLE_CHOICE,
                options=[
                    {
                        "text": "Правильный",
                        "is_correct": True,
                    },
                    {
                        "text": "Неправильный",
                        "is_correct": False,
                    },
                ],
            )

    def test_multiple_choice_requires_incorrect_option(
        self,
    ):
        with self.assertRaises(ValidationError):
            validate_answer_configuration(
                answer_type=QuestionType.MULTIPLE_CHOICE,
                options=[
                    {
                        "text": "Первый правильный",
                        "is_correct": True,
                    },
                    {
                        "text": "Второй правильный",
                        "is_correct": True,
                    },
                ],
            )

    def test_valid_matching_configuration(self):
        validate_matching_configuration(
            pairs=[
                {
                    "left_text": "Высокий await",
                    "right_text": "Проблема с диском",
                },
                {
                    "left_text": "Сработал OOM Killer",
                    "right_text": "Нехватка памяти",
                },
            ],
        )

    def test_matching_requires_two_pairs(self):
        with self.assertRaises(ValidationError):
            validate_matching_configuration(
                pairs=[
                    {
                        "left_text": "Симптом",
                        "right_text": "Причина",
                    },
                ],
            )

    def test_matching_right_parts_must_be_unique(self):
        with self.assertRaises(ValidationError):
            validate_matching_configuration(
                pairs=[
                    {
                        "left_text": "Первый симптом",
                        "right_text": "Одна причина",
                    },
                    {
                        "left_text": "Второй симптом",
                        "right_text": "Одна причина",
                    },
                ],
            )

    def test_valid_ordering_configuration(self):
        validate_ordering_configuration(
            items=[
                {"text": "Изменить конфигурацию"},
                {"text": "Проверить конфигурацию"},
                {"text": "Применить изменения"},
            ],
        )

    def test_ordering_requires_three_items(self):
        with self.assertRaises(ValidationError):
            validate_ordering_configuration(
                items=[
                    {"text": "Первый шаг"},
                    {"text": "Второй шаг"},
                ],
            )

    def test_valid_line_selection_configuration(self):
        validate_line_selection_configuration(
            lines=[
                {
                    "text": "Первая строка",
                    "is_correct": False,
                },
                {
                    "text": "Строка с ошибкой",
                    "is_correct": True,
                },
                {
                    "text": "Третья строка",
                    "is_correct": False,
                },
            ],
        )

    def test_line_selection_requires_correct_line(self):
        with self.assertRaises(ValidationError):
            validate_line_selection_configuration(
                lines=[
                    {
                        "text": "Первая строка",
                        "is_correct": False,
                    },
                    {
                        "text": "Вторая строка",
                        "is_correct": False,
                    },
                ],
            )
