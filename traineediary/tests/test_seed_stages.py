from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from traineediary.models import (
    StageGroup,
    TraineeStage,
)


class SeedStagesCommandTests(TestCase):
    def test_seed_stages_creates_current_stage_order(
        self,
    ):
        stdout = StringIO()

        call_command(
            "seed_stages",
            stdout=stdout,
        )

        stage_slugs = list(
            TraineeStage.objects
            .order_by("order")
            .values_list(
                "slug",
                flat=True,
            )
        )

        self.assertEqual(
            stage_slugs,
            [
                "first-day",
                "vds",
                "managed-services",
                "client-service",
                "sandbox-candidate",
                "before-tickets",
                "with-review",
                "optional-review",
                "no-review",
                "done",
            ],
        )

        sandbox_stage = (
            TraineeStage.objects.get(
                slug="sandbox-candidate",
            )
        )
        before_tickets_stage = (
            TraineeStage.objects.get(
                slug="before-tickets",
            )
        )

        self.assertEqual(
            sandbox_stage.order,
            5,
        )
        self.assertEqual(
            sandbox_stage.group,
            StageGroup.SANDBOX_L1,
        )
        self.assertEqual(
            before_tickets_stage.order,
            6,
        )

        self.assertIn(
            "создано 10",
            stdout.getvalue(),
        )

    def test_seed_stages_updates_existing_data_without_duplicates(
        self,
    ):
        TraineeStage.objects.create(
            name="Старое название",
            slug="sandbox-candidate",
            order=99,
            min_days=10,
            max_days=20,
            progress_weight_percent=1,
            color="#000000",
            group=StageGroup.TEACHBASE,
            applies_to_new_hire=False,
            applies_to_internal_transfer=True,
        )

        call_command(
            "seed_stages",
            stdout=StringIO(),
        )
        call_command(
            "seed_stages",
            stdout=StringIO(),
        )

        self.assertEqual(
            TraineeStage.objects.count(),
            10,
        )

        sandbox_stage = (
            TraineeStage.objects.get(
                slug="sandbox-candidate",
            )
        )

        self.assertEqual(
            sandbox_stage.name,
            "Задания в ticket-sandbox",
        )
        self.assertEqual(
            sandbox_stage.order,
            5,
        )
        self.assertEqual(
            sandbox_stage.min_days,
            1,
        )
        self.assertEqual(
            sandbox_stage.max_days,
            2,
        )
        self.assertEqual(
            sandbox_stage.progress_weight_percent,
            5,
        )
        self.assertEqual(
            sandbox_stage.color,
            "#14B8A6",
        )
        self.assertEqual(
            sandbox_stage.group,
            StageGroup.SANDBOX_L1,
        )
        self.assertTrue(
            sandbox_stage.applies_to_new_hire,
        )
        self.assertFalse(
            sandbox_stage.applies_to_internal_transfer,
        )
