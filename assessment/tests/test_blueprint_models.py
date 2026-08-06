from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase

from assessment.constants import SupportLevel
from assessment.models import (
    BlueprintSkillQuota,
    ExamBlueprint,
    Skill,
    Topic,
)


class ExamBlueprintModelTests(TestCase):
    def setUp(self):
        self.linux_topic = Topic.objects.create(
            name="Тестовая тема Linux для шаблона",
            slug="test-blueprint-linux",
            order=100,
        )

        self.web_topic = Topic.objects.create(
            name="Тестовая тема Web для шаблона",
            slug="test-blueprint-web",
            order=110,
        )

        self.linux_skill = Skill.objects.create(
            topic=self.linux_topic,
            name="Тестовый Linux-навык",
            slug="test-blueprint-linux-skill",
            order=10,
        )

        self.web_skill = Skill.objects.create(
            topic=self.web_topic,
            name="Тестовый Web-навык",
            slug="test-blueprint-web-skill",
            order=10,
        )

        self.blueprint = ExamBlueprint.objects.create(
            name="Тестовый шаблон L1",
            slug="test-l1-blueprint",
            level=SupportLevel.L1,
        )

    def test_blueprint_defaults(self):
        self.assertEqual(
            self.blueprint.pass_percentage,
            85,
        )
        self.assertFalse(
            self.blueprint.allow_back_navigation,
        )
        self.assertTrue(
            self.blueprint.shuffle_questions,
        )
        self.assertTrue(
            self.blueprint.shuffle_answer_options,
        )
        self.assertTrue(
            self.blueprint.is_active,
        )

    def test_blueprint_string_contains_name_and_level(self):
        self.assertEqual(
            str(self.blueprint),
            "Тестовый шаблон L1 — L1",
        )

    def test_question_count_is_calculated_from_skill_quotas(
        self,
    ):
        BlueprintSkillQuota.objects.create(
            blueprint=self.blueprint,
            skill=self.linux_skill,
            question_count=10,
            order=10,
        )

        BlueprintSkillQuota.objects.create(
            blueprint=self.blueprint,
            skill=self.web_skill,
            question_count=8,
            order=20,
        )

        self.assertEqual(
            self.blueprint.question_count,
            18,
        )

    def test_skill_can_be_added_only_once(self):
        BlueprintSkillQuota.objects.create(
            blueprint=self.blueprint,
            skill=self.linux_skill,
            question_count=1,
        )

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                BlueprintSkillQuota.objects.create(
                    blueprint=self.blueprint,
                    skill=self.linux_skill,
                    question_count=2,
                )

    def test_question_count_must_be_positive(self):
        quota = BlueprintSkillQuota(
            blueprint=self.blueprint,
            skill=self.linux_skill,
            question_count=0,
        )

        with self.assertRaises(ValidationError):
            quota.full_clean()

    def test_pass_percentage_cannot_exceed_one_hundred(
        self,
    ):
        self.blueprint.pass_percentage = 101

        with self.assertRaises(ValidationError):
            self.blueprint.full_clean()
