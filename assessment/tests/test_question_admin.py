from django.contrib import admin
from django.test import SimpleTestCase

from assessment.admin import (
    AnswerOptionInline,
    AnswerOptionInlineFormSet,
)
from assessment.models import Question


class QuestionAdminTests(SimpleTestCase):
    def setUp(self):
        self.question_admin = admin.site._registry[
            Question
        ]

    def test_question_is_registered_in_admin(self):
        self.assertIsNotNone(
            self.question_admin,
        )

    def test_answer_options_are_available_inline(self):
        self.assertIn(
            AnswerOptionInline,
            self.question_admin.inlines,
        )

    def test_slug_is_prepopulated_from_title(self):
        self.assertEqual(
            self.question_admin.prepopulated_fields,
            {
                "slug": (
                    "title",
                ),
            },
        )

    def test_question_can_be_filtered_by_level(self):
        self.assertIn(
            "level",
            self.question_admin.list_filter,
        )

    def test_question_can_be_filtered_by_topic(self):
        self.assertIn(
            "family__skill__topic",
            self.question_admin.list_filter,
        )

    def test_answer_inline_uses_validation_formset(self):
        self.assertIs(
            AnswerOptionInline.formset,
            AnswerOptionInlineFormSet,
        )
