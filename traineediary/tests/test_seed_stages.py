from io import StringIO

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from traineediary.models import EntryType, StageScheme, StageScope, TraineeStage
from traineediary.services.stage_catalog import contract
from traineediary.services.stages import selectable_stages


class SeedStagesCommandTests(TestCase):
    def test_seed_creates_six_unified_stages_and_is_idempotent(self):
        call_command("seed_stages", stdout=StringIO())
        before = list(TraineeStage.objects.order_by("pk").values())
        call_command("seed_stages", stdout=StringIO())
        self.assertEqual(before, list(TraineeStage.objects.order_by("pk").values()))
        stages = selectable_stages(StageScheme.UNIFIED, EntryType.NEW_HIRE)
        self.assertEqual(
            list(stages.values_list("slug", flat=True)),
            [
                "training-program",
                "sandbox-candidate",
                "with-review",
                "optional-review",
                "no-review",
                "done",
            ],
        )
        self.assertEqual(sum(s.progress_weight_percent for s in stages), 100)
        self.assertEqual(TraineeStage.objects.count(), 6)

    def test_seed_preserves_legacy_records_and_shared_names_and_colors(self):
        for slug, fields in contract.LEGACY_CATALOG.items():
            TraineeStage.objects.create(
                slug=slug,
                **fields,
                color="#000000",
                catalog_scope=(
                    StageScope.LEGACY
                    if slug in contract.LEGACY_SLUGS
                    else StageScope.SHARED
                ),
            )
        before = list(TraineeStage.objects.order_by("pk").values())
        call_command("seed_stages", stdout=StringIO())
        self.assertEqual(before, list(TraineeStage.objects.order_by("pk").values()))
        self.assertEqual(TraineeStage.objects.count(), 11)

    def test_seed_refuses_nonstandard_parameters_without_any_changes(self):
        TraineeStage.objects.create(
            slug="sandbox-candidate", name="Custom", order=99, group="teachbase"
        )
        before = list(TraineeStage.objects.values())
        with self.assertRaisesMessage(CommandError, "Seed остановлен"):
            call_command("seed_stages", stdout=StringIO())
        self.assertEqual(before, list(TraineeStage.objects.values()))

    def test_seed_refuses_unknown_stages(self):
        TraineeStage.objects.create(
            slug="custom-course", name="Custom", order=99, group="teachbase"
        )
        with self.assertRaisesMessage(CommandError, "неизвестный этап"):
            call_command("seed_stages", stdout=StringIO())
        self.assertFalse(TraineeStage.objects.filter(slug="with-review").exists())

    def test_seed_does_not_reactivate_stages(self):
        call_command("seed_stages", stdout=StringIO())
        TraineeStage.objects.filter(slug="training-program").update(is_active=False)
        call_command("seed_stages", stdout=StringIO())
        self.assertFalse(TraineeStage.objects.get(slug="training-program").is_active)

    def test_historical_fixture_resolves_slugs_without_overwriting_program_pk(self):
        program = TraineeStage.objects.get(slug="training-program")
        call_command("seed_stages", stdout=StringIO())
        shared_pk = TraineeStage.objects.get(slug="with-review").pk
        call_command("loaddata", "trainee_stages", stdout=StringIO())
        program.refresh_from_db()
        self.assertEqual(program.slug, "training-program")
        self.assertEqual(program.catalog_scope, StageScope.UNIFIED)
        self.assertEqual(TraineeStage.objects.get(slug="with-review").pk, shared_pk)
        self.assertEqual(TraineeStage.objects.count(), 11)
