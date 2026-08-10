from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from assessment.constants import (
    QuestionDifficulty,
    QuestionStatus,
    QuestionType,
    SupportLevel,
)
from assessment.models import (
    Question,
    QuestionFamily,
    Skill,
    Topic,
)
from assessment.forms import (
    QuestionEditorForm,
)


class MentorQuestionEditorTests(TestCase):
    def setUp(self):
        self.staff = User.objects.create_user(
            username="question-editor-staff",
            password="test-password",
            is_staff=True,
        )

        self.topic = Topic.objects.create(
            name="Тема редактора",
            slug="test-editor-topic",
            order=800,
        )

        self.skill = Skill.objects.create(
            topic=self.topic,
            name="Навык редактора",
            slug="test-editor-skill",
        )

        self.family = QuestionFamily.objects.create(
            skill=self.skill,
            name="Семейство редактора",
            slug="test-editor-family",
            assessment_goal=(
                "Проверить создание вопроса."
            ),
        )

        self.client.force_login(
            self.staff
        )

    def test_create_page_is_available(self):
        response = self.client.get(
            reverse(
                "assessment:mentor_question_create"
            )
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        self.assertContains(
            response,
            "Создание вопроса",
        )

    def test_single_choice_question_can_be_created(
        self,
    ):
        response = self.client.post(
            reverse(
                "assessment:mentor_question_create"
            ),
            {
                "family": self.family.pk,
                "title": "Тестовый вопрос редактора",
                "level": SupportLevel.L1,
                "difficulty": (
                    QuestionDifficulty.HARD
                ),
                "scenario": (
                    "На сервере возникла проблема."
                ),
                "diagnostic_data": "",
                "prompt": (
                    "Что нужно проверить?"
                ),
                "answer_type": (
                    QuestionType.SINGLE_CHOICE
                ),
                "time_limit_seconds": 90,
                "explanation": "",
                "status": QuestionStatus.ACTIVE,
                "order": 10,

                "options-TOTAL_FORMS": 4,
                "options-INITIAL_FORMS": 0,
                "options-MIN_NUM_FORMS": 0,
                "options-MAX_NUM_FORMS": 1000,

                "options-0-text": (
                    "Правильный ответ"
                ),
                "options-0-is_correct": "on",
                "options-0-order": 10,

                "options-1-text": (
                    "Неправильный ответ"
                ),
                "options-1-order": 20,

                "options-2-text": "",
                "options-2-order": 0,

                "options-3-text": "",
                "options-3-order": 0,
            },
        )

        question = Question.objects.get(
            title="Тестовый вопрос редактора"
        )

        self.assertRedirects(
            response,
            reverse(
                "assessment:mentor_question_edit",
                args=[question.pk],
            ),
        )

        self.assertEqual(
            question.answer_options.count(),
            2,
        )

        self.assertEqual(
            question.answer_options.filter(
                is_correct=True
            ).count(),
            1,
        )

    def test_family_choice_contains_full_path(self):
        family = QuestionFamily.objects.create(
            skill=self.skill,
            name="Высокий load из-за I/O",
            slug="test-editor-io-family",
            assessment_goal="Проверить I/O wait.",
        )

        form = QuestionEditorForm()

        choices = dict(
            form.fields["family"].choices
        )

        self.assertEqual(
            choices[family.pk],
            (
                "Тема редактора → "
                "Навык редактора → "
                "Высокий load из-за I/O"
            ),
        )

    def test_inactive_family_is_hidden_for_new_question(
        self,
    ):
        family = QuestionFamily.objects.create(
            skill=self.skill,
            name="Старое семейство",
            slug="test-editor-inactive-family",
            assessment_goal="Старая проверка.",
            is_active=False,
        )

        form = QuestionEditorForm()

        self.assertNotIn(
            family,
            form.fields["family"].queryset,
        )

    def test_existing_question_keeps_inactive_family_available(
        self,
    ):
        family = QuestionFamily.objects.create(
            skill=self.skill,
            name="Отключённое семейство",
            slug="test-editor-existing-family",
            assessment_goal="Старая проверка.",
            is_active=False,
        )

        question = Question.objects.create(
            family=family,
            title="Старый вопрос",
            slug="test-existing-inactive-family-question",
            level=SupportLevel.L1,
            difficulty=QuestionDifficulty.HARD,
            answer_type=QuestionType.SINGLE_CHOICE,
            status=QuestionStatus.DRAFT,
            prompt="Старый вопрос.",
        )

        form = QuestionEditorForm(
            instance=question
        )

        self.assertIn(
            family,
            form.fields["family"].queryset,
        )

    def test_create_page_has_dynamic_answer_controls(
        self,
    ):
        response = self.client.get(
            reverse(
                "assessment:mentor_question_create"
            )
        )

        self.assertContains(
            response,
            "Добавить вариант",
        )

        self.assertContains(
            response,
            "Добавить пару",
        )

        self.assertContains(
            response,
            "Добавить шаг",
        )

        self.assertContains(
            response,
            "Добавить строку",
        )

        self.assertContains(
            response,
            "data-formset",
        )
