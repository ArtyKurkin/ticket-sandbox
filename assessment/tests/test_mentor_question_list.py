from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from assessment.constants import (
    QuestionStatus,
    SupportLevel,
)
from assessment.models import (
    Question,
    QuestionFamily,
    Skill,
    Topic,
)


class MentorQuestionListTests(TestCase):
    def setUp(self):
        self.staff = User.objects.create_user(
            username="question-mentor",
            password="test-password",
            is_staff=True,
        )

        self.regular_user = User.objects.create_user(
            username="question-regular",
            password="test-password",
        )

        self.topic = Topic.objects.create(
            name="Тестовая тема банка",
            slug="test-question-bank-topic",
            order=700,
        )

        self.skill = Skill.objects.create(
            topic=self.topic,
            name="Тестовый навык банка",
            slug="test-question-bank-skill",
        )

        self.family = QuestionFamily.objects.create(
            skill=self.skill,
            name="Тестовое семейство банка",
            slug="test-question-bank-family",
            assessment_goal="Проверка списка.",
        )

        self.question = Question.objects.create(
            family=self.family,
            title="Диагностика тестового сервера",
            slug="test-question-bank-question",
            level=SupportLevel.L1,
            status=QuestionStatus.ACTIVE,
            prompt=(
                "Что нужно проверить "
                "в первую очередь?"
            ),
        )

    def test_staff_can_open_question_bank(self):
        self.client.force_login(
            self.staff
        )

        response = self.client.get(
            reverse(
                "assessment:mentor_question_list"
            )
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        self.assertContains(
            response,
            "Диагностика тестового сервера",
        )

    def test_regular_user_cannot_open_question_bank(
        self,
    ):
        self.client.force_login(
            self.regular_user
        )

        response = self.client.get(
            reverse(
                "assessment:mentor_question_list"
            )
        )

        self.assertEqual(
            response.status_code,
            302,
        )

    def test_search_filters_questions(self):
        self.client.force_login(
            self.staff
        )

        response = self.client.get(
            reverse(
                "assessment:mentor_question_list"
            ),
            {
                "q": "тестового сервера",
            },
        )

        self.assertContains(
            response,
            "Диагностика тестового сервера",
        )

        response = self.client.get(
            reverse(
                "assessment:mentor_question_list"
            ),
            {
                "q": "такого вопроса нет",
            },
        )

        self.assertNotContains(
            response,
            "Диагностика тестового сервера",
        )

    def test_level_filter(self):
        self.client.force_login(
            self.staff
        )

        response = self.client.get(
            reverse(
                "assessment:mentor_question_list"
            ),
            {
                "level": "l1",
            },
        )

        self.assertContains(
            response,
            "Диагностика тестового сервера",
        )

        response = self.client.get(
            reverse(
                "assessment:mentor_question_list"
            ),
            {
                "level": "l2",
            },
        )

        self.assertNotContains(
            response,
            "Диагностика тестового сервера",
        )

    def test_topic_filter(self):
        self.client.force_login(
            self.staff
        )

        response = self.client.get(
            reverse(
                "assessment:mentor_question_list"
            ),
            {
                "topic": self.topic.slug,
            },
        )

        self.assertContains(
            response,
            "Диагностика тестового сервера",
        )
