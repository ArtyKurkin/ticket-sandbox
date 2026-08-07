from decimal import Decimal
from types import SimpleNamespace

from django.core.exceptions import ValidationError
from django.test import SimpleTestCase

from assessment.constants import QuestionType
from assessment.services.answer_grading import (
    grade_snapshot_answer,
)


class AnswerGradingTests(SimpleTestCase):
    def make_snapshot(
        self,
        *,
        question_type,
        visible_payload,
        grading_payload,
    ):
        return SimpleNamespace(
            question_type=question_type,
            visible_payload=visible_payload,
            grading_payload=grading_payload,
        )

    def test_single_choice_correct(self):
        snapshot = self.make_snapshot(
            question_type=QuestionType.SINGLE_CHOICE,
            visible_payload={
                "options": [
                    {
                        "key": "option-1",
                        "text": "Первый",
                    },
                    {
                        "key": "option-2",
                        "text": "Второй",
                    },
                ],
            },
            grading_payload={
                "correct_keys": [
                    "option-2",
                ],
            },
        )

        score = grade_snapshot_answer(
            snapshot,
            {
                "selected_keys": [
                    "option-2",
                ],
            },
        )

        self.assertEqual(
            score,
            Decimal("100.00"),
        )

    def test_single_choice_incorrect(self):
        snapshot = self.make_snapshot(
            question_type=QuestionType.SINGLE_CHOICE,
            visible_payload={
                "options": [
                    {"key": "option-1"},
                    {"key": "option-2"},
                ],
            },
            grading_payload={
                "correct_keys": [
                    "option-2",
                ],
            },
        )

        score = grade_snapshot_answer(
            snapshot,
            {
                "selected_keys": [
                    "option-1",
                ],
            },
        )

        self.assertEqual(
            score,
            Decimal("0.00"),
        )

    def test_multiple_choice_requires_exact_set(self):
        snapshot = self.make_snapshot(
            question_type=QuestionType.MULTIPLE_CHOICE,
            visible_payload={
                "options": [
                    {"key": "option-1"},
                    {"key": "option-2"},
                    {"key": "option-3"},
                ],
            },
            grading_payload={
                "correct_keys": [
                    "option-1",
                    "option-3",
                ],
            },
        )

        score = grade_snapshot_answer(
            snapshot,
            {
                "selected_keys": [
                    "option-1",
                    "option-3",
                ],
            },
        )

        self.assertEqual(
            score,
            Decimal("100.00"),
        )

    def test_matching_supports_partial_score(self):
        snapshot = self.make_snapshot(
            question_type=QuestionType.MATCHING,
            visible_payload={
                "left_items": [
                    {"key": "left-1"},
                    {"key": "left-2"},
                    {"key": "left-3"},
                ],
                "right_items": [
                    {"key": "right-1"},
                    {"key": "right-2"},
                    {"key": "right-3"},
                ],
            },
            grading_payload={
                "matches": {
                    "left-1": "right-1",
                    "left-2": "right-2",
                    "left-3": "right-3",
                },
            },
        )

        score = grade_snapshot_answer(
            snapshot,
            {
                "matches": {
                    "left-1": "right-1",
                    "left-2": "right-3",
                    "left-3": "right-2",
                },
            },
        )

        self.assertEqual(
            score,
            Decimal("33.33"),
        )

    def test_ordering_supports_partial_score(self):
        snapshot = self.make_snapshot(
            question_type=QuestionType.ORDERING,
            visible_payload={
                "items": [
                    {"key": "item-1"},
                    {"key": "item-2"},
                    {"key": "item-3"},
                ],
            },
            grading_payload={
                "correct_order": [
                    "item-1",
                    "item-2",
                    "item-3",
                ],
            },
        )

        score = grade_snapshot_answer(
            snapshot,
            {
                "order": [
                    "item-2",
                    "item-1",
                    "item-3",
                ],
            },
        )

        self.assertEqual(
            score,
            Decimal("66.67"),
        )

    def test_line_selection_requires_exact_set(self):
        snapshot = self.make_snapshot(
            question_type=QuestionType.LINE_SELECTION,
            visible_payload={
                "lines": [
                    {"key": "line-1"},
                    {"key": "line-2"},
                    {"key": "line-3"},
                ],
            },
            grading_payload={
                "correct_keys": [
                    "line-2",
                ],
            },
        )

        score = grade_snapshot_answer(
            snapshot,
            {
                "selected_keys": [
                    "line-2",
                ],
            },
        )

        self.assertEqual(
            score,
            Decimal("100.00"),
        )

    def test_unknown_option_is_rejected(self):
        snapshot = self.make_snapshot(
            question_type=QuestionType.SINGLE_CHOICE,
            visible_payload={
                "options": [
                    {"key": "option-1"},
                    {"key": "option-2"},
                ],
            },
            grading_payload={
                "correct_keys": [
                    "option-1",
                ],
            },
        )

        with self.assertRaises(ValidationError):
            grade_snapshot_answer(
                snapshot,
                {
                    "selected_keys": [
                        "hacked-option",
                    ],
                },
            )
