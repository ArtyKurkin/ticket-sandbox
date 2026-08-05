from django.contrib import admin
from django.test import SimpleTestCase

from assessment.admin import (
    QuestionFamilyInline,
    SkillInline,
)
from assessment.models import (
    QuestionFamily,
    Skill,
    Topic,
)


class AssessmentTaxonomyAdminTests(SimpleTestCase):
    def test_taxonomy_models_are_registered(self):
        self.assertIn(
            Topic,
            admin.site._registry,
        )
        self.assertIn(
            Skill,
            admin.site._registry,
        )
        self.assertIn(
            QuestionFamily,
            admin.site._registry,
        )

    def test_topic_admin_contains_skill_inline(self):
        topic_admin = admin.site._registry[Topic]

        self.assertIn(
            SkillInline,
            topic_admin.inlines,
        )

    def test_skill_admin_contains_family_inline(self):
        skill_admin = admin.site._registry[Skill]

        self.assertIn(
            QuestionFamilyInline,
            skill_admin.inlines,
        )

    def test_slugs_are_prepopulated_from_names(self):
        topic_admin = admin.site._registry[Topic]
        skill_admin = admin.site._registry[Skill]
        family_admin = admin.site._registry[
            QuestionFamily
        ]

        self.assertEqual(
            topic_admin.prepopulated_fields,
            {
                "slug": (
                    "name",
                ),
            },
        )

        self.assertEqual(
            skill_admin.prepopulated_fields,
            {
                "slug": (
                    "name",
                ),
            },
        )

        self.assertEqual(
            family_admin.prepopulated_fields,
            {
                "slug": (
                    "name",
                ),
            },
        )
