from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from assessment.models import (
    QuestionFamily,
    Skill,
    Topic,
)


class MentorFamilyTests(TestCase):
    def setUp(self):
        self.staff = User.objects.create_user(
            username="family-mentor",
            password="test-password",
            is_staff=True,
        )

        self.regular_user = User.objects.create_user(
            username="family-regular",
            password="test-password",
        )

        self.topic = Topic.objects.create(
            name="Тестовая тема семейства",
            slug="test-family-topic",
            order=900,
        )

        self.skill = Skill.objects.create(
            topic=self.topic,
            name="Тестовый навык семейства",
            slug="test-family-skill",
        )

        self.client.force_login(
            self.staff
        )

    def test_family_list_is_available(self):
        response = self.client.get(
            reverse(
                "assessment:mentor_family_list"
            )
        )

        self.assertEqual(
            response.status_code,
            200,
        )

    def test_family_can_be_created(self):
        response = self.client.post(
            reverse(
                "assessment:mentor_family_create"
            ),
            {
                "skill": self.skill.pk,
                "name": (
                    "Высокий load из-за I/O"
                ),
                "assessment_goal": (
                    "Проверить диагностику "
                    "I/O wait."
                ),
                "is_active": "on",
            },
        )

        family = QuestionFamily.objects.get(
            name="Высокий load из-за I/O"
        )

        self.assertRedirects(
            response,
            reverse(
                "assessment:mentor_family_edit",
                args=[family.pk],
            ),
        )

        self.assertEqual(
            family.skill,
            self.skill,
        )

        self.assertTrue(
            family.is_active,
        )

    def test_family_can_be_deactivated(self):
        family = QuestionFamily.objects.create(
            skill=self.skill,
            name="Старое семейство",
            slug="test-old-family",
            assessment_goal="Старая проверка.",
        )

        response = self.client.post(
            reverse(
                "assessment:mentor_family_edit",
                args=[family.pk],
            ),
            {
                "skill": self.skill.pk,
                "name": family.name,
                "assessment_goal": (
                    family.assessment_goal
                ),
            },
        )

        self.assertRedirects(
            response,
            reverse(
                "assessment:mentor_family_edit",
                args=[family.pk],
            ),
        )

        family.refresh_from_db()

        self.assertFalse(
            family.is_active,
        )

    def test_regular_user_cannot_open_family_list(
        self,
    ):
        self.client.force_login(
            self.regular_user
        )

        response = self.client.get(
            reverse(
                "assessment:mentor_family_list"
            )
        )

        self.assertEqual(
            response.status_code,
            302,
        )
