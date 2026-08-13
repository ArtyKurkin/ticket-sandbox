from django.test import TestCase

from assessment.models import (
    BlueprintSkillQuota,
    ExamBlueprint,
    Skill,
)


class SeededL1TaxonomyTests(TestCase):

    def test_control_panels_replaces_cron(
        self,
    ):
        cron = Skill.objects.get(
            topic__slug="linux-vds",
            slug="cron-runtime-context",
        )

        panels = Skill.objects.get(
            topic__slug="linux-vds",
            slug="control-panels",
        )

        self.assertFalse(
            cron.is_active
        )

        self.assertTrue(
            panels.is_active
        )

        blueprint = (
            ExamBlueprint.objects.get(
                slug=(
                    "l1-technical-assessment"
                ),
            )
        )

        self.assertFalse(
            BlueprintSkillQuota.objects.filter(
                blueprint=blueprint,
                skill=cron,
            ).exists()
        )

        self.assertTrue(
            BlueprintSkillQuota.objects.filter(
                blueprint=blueprint,
                skill=panels,
                question_count=1,
            ).exists()
        )
