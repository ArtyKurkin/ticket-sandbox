from django.db import IntegrityError, transaction
from django.test import TestCase

from assessment.models import (
    QuestionFamily,
    Skill,
    Topic,
)


class AssessmentTaxonomyModelTests(TestCase):
    def setUp(self):
        self.linux_topic = Topic.objects.create(
            name="Тестовая тема Linux",
            slug="test-linux-vds",
            order=1,
        )

        self.filesystem_skill = Skill.objects.create(
            topic=self.linux_topic,
            name="Тестовые файловые системы",
            slug="test-filesystems",
            description=(
                "Диагностика дисков, разделов "
                "и файловых систем."
            ),
            order=1,
        )

    def test_topic_string_contains_name(self):
        self.assertEqual(
            str(self.linux_topic),
            "Тестовая тема Linux",
        )

    def test_skill_string_contains_topic_and_name(self):
        self.assertEqual(
            str(self.filesystem_skill),
            (
                "Тестовая тема Linux "
                "→ Тестовые файловые системы"
            ),
        )

    def test_question_family_string_contains_full_path(self):
        family = QuestionFamily.objects.create(
            skill=self.filesystem_skill,
            name="Расхождение df и du",
            slug="test-df-du-difference",
            assessment_goal=(
                "Сотрудник понимает причины "
                "расхождения показателей df и du."
            ),
        )

        self.assertEqual(
            str(family),
            (
                "Тестовая тема Linux "
                "→ Тестовые файловые системы "
                "→ Расхождение df и du"
            ),
        )

    def test_taxonomy_entities_are_active_by_default(self):
        family = QuestionFamily.objects.create(
            skill=self.filesystem_skill,
            name="Закончились inode",
            slug="test-inode-exhaustion",
            assessment_goal=(
                "Сотрудник умеет отличить нехватку "
                "inode от нехватки места."
            ),
        )

        self.assertTrue(self.linux_topic.is_active)
        self.assertTrue(self.filesystem_skill.is_active)
        self.assertTrue(family.is_active)

    def test_skill_slug_is_unique_inside_topic(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Skill.objects.create(
                    topic=self.linux_topic,
                    name="Другая файловая система",
                    slug="test-filesystems",
                )

    def test_same_skill_slug_is_allowed_in_different_topics(self):
        web_topic = Topic.objects.create(
            name="Тестовая тема Web",
            slug="test-web",
            order=2,
        )

        web_skill = Skill.objects.create(
            topic=web_topic,
            name="Файловые системы сайта",
            slug="test-filesystems",
        )

        self.assertEqual(
            web_skill.slug,
            self.filesystem_skill.slug,
        )

        self.assertNotEqual(
            web_skill.topic,
            self.filesystem_skill.topic,
        )

    def test_family_slug_is_unique_inside_skill(self):
        QuestionFamily.objects.create(
            skill=self.filesystem_skill,
            name="Расхождение df и du",
            slug="test-df-du-difference",
            assessment_goal="Первый вариант семейства.",
        )

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                QuestionFamily.objects.create(
                    skill=self.filesystem_skill,
                    name="Дубликат",
                    slug="test-df-du-difference",
                    assessment_goal="Дублирующее семейство.",
                )

    def test_topic_uses_configured_order(self):
        web_topic = Topic.objects.create(
            name="Тестовая тема Web",
            slug="test-web",
            order=2,
        )

        networks_topic = Topic.objects.create(
            name="Тестовая тема Сети",
            slug="test-networks",
            order=3,
        )

        topic_slugs = list(
            Topic.objects.filter(
                slug__in={
                    self.linux_topic.slug,
                    web_topic.slug,
                    networks_topic.slug,
                },
            ).values_list(
                "slug",
                flat=True,
            )
        )

        self.assertEqual(
            topic_slugs,
            [
                "test-linux-vds",
                "test-web",
                "test-networks",
            ],
        )
