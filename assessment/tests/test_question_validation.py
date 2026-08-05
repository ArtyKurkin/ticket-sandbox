from django.core.exceptions import ValidationError
from django.test import SimpleTestCase

from assessment.constants import QuestionType
from assessment.question_validation import (
    validate_answer_configuration,
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
