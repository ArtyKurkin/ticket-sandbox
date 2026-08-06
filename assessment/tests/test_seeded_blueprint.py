from django.test import TestCase

from assessment.constants import SupportLevel
from assessment.models import (
    ExamBlueprint,
)


class SeededL1BlueprintTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.blueprint = ExamBlueprint.objects.get(
            slug="l1-technical-assessment",
        )

    def test_l1_blueprint_exists(self):
        self.assertEqual(
            self.blueprint.name,
            "Техническая оценка L1",
        )
        self.assertEqual(
            self.blueprint.level,
            SupportLevel.L1,
        )

    def test_blueprint_is_inactive_until_bank_is_ready(
        self,
    ):
        self.assertFalse(
            self.blueprint.is_active,
        )

    def test_blueprint_uses_expected_settings(self):
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

    def test_blueprint_contains_twenty_six_questions(
        self,
    ):
        self.assertEqual(
            self.blueprint.question_count,
            26,
        )
        self.assertEqual(
            self.blueprint.skill_quotas.count(),
            26,
        )

    def test_each_skill_requires_one_question(self):
        self.assertFalse(
            self.blueprint.skill_quotas.exclude(
                question_count=1,
            ).exists()
        )

    def test_blueprint_has_expected_topic_distribution(
        self,
    ):
        topic_counts = {
            topic_slug: (
                self.blueprint.skill_quotas.filter(
                    skill__topic__slug=topic_slug,
                ).count()
            )
            for topic_slug in (
                "linux-vds",
                "web",
                "networks",
                "internal-regulations",
            )
        }

        self.assertEqual(
            topic_counts,
            {
                "linux-vds": 10,
                "web": 8,
                "networks": 8,
                "internal-regulations": 0,
            },
        )

    def test_blueprint_contains_key_skills(self):
        skill_slugs = set(
            self.blueprint.skill_quotas.values_list(
                "skill__slug",
                flat=True,
            )
        )

        self.assertTrue(
            {
                "df-du-open-files",
                "cpu-io-load-average",
                "php-fpm-pool-limits",
                "mtr-intermediate-loss",
                "ipv6-routing-listening",
            }.issubset(skill_slugs)
        )
