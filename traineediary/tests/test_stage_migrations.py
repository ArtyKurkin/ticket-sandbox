"""Exercise real migrations against a separate in-memory connection, never a real DB."""

from copy import deepcopy
from importlib import import_module
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import MagicMock

from django.db import connections
from django.db.backends.sqlite3.base import DatabaseWrapper
from django.db.migrations.executor import MigrationExecutor
from django.db.migrations.exceptions import IrreversibleError


# Independent regression fixture from the administrator's read-only SQL result.
LIVE_OVERRIDES = {
    "before-tickets": {"order": 5},
    "client-service": {"max_days": 3},
    "managed-services": {"max_days": 4},
    "no-review": {"max_days": 14},
    "optional-review": {"min_days": 10, "max_days": 14},
    "sandbox-candidate": {"order": 6, "max_days": 3},
    "with-review": {"min_days": 28, "max_days": 35},
}


class StageMigrationTests(TestCase):
    alias = "stage_migration_audit"
    before = [("traineediary", "0005_traineejourney_completed_at_and_more")]
    after = [("traineediary", "0007_classify_stage_catalog")]

    def setUp(self):
        settings = deepcopy(connections["default"].settings_dict)
        settings.update(
            ENGINE="django.db.backends.sqlite3", NAME=":memory:", OPTIONS={}
        )
        self.connection = DatabaseWrapper(settings, alias=self.alias)
        connections[self.alias] = self.connection
        self.executor = MigrationExecutor(self.connection)
        self.executor.migrate(self.before)
        self.apps = self.executor.loader.project_state(self.before).apps
        self.contract = import_module(
            "traineediary.migrations.0007_classify_stage_catalog"
        )
        self.Stage = self.apps.get_model("traineediary", "TraineeStage")
        self.Journey = self.apps.get_model("traineediary", "TraineeJourney")
        self.History = self.apps.get_model("traineediary", "StageHistory")
        self.Metric = self.apps.get_model("traineediary", "WeeklyMetric")
        self.User = self.apps.get_model("auth", "User")
        for slug, fields in self.contract.LEGACY_CATALOG.items():
            self.Stage.objects.using(self.alias).create(slug=slug, **fields)

    def tearDown(self):
        self.connection.close()
        del connections[self.alias]

    def journey(self, slug, index):
        user = self.User.objects.using(self.alias).create(username=f"migration-{index}")
        staff = self.User.objects.using(self.alias).get_or_create(
            username="migration-staff", defaults={"is_staff": True}
        )[0]
        stage = self.Stage.objects.using(self.alias).get(slug=slug)
        journey = self.Journey.objects.using(self.alias).create(
            user=user,
            entry_type="new_hire",
            current_stage=stage,
            probation_start_date="2026-01-01",
            stage_started_at="2026-01-03",
            comment="Keep comment",
        )
        self.History.objects.using(self.alias).create(
            journey=journey,
            stage=stage,
            started_at="2026-01-03",
            changed_by=staff,
            note="Keep history",
        )
        self.Metric.objects.using(self.alias).create(
            journey=journey,
            week_number=1,
            quality_percent=87,
            speed_hours="4.5",
            mentor_comment="Keep metric",
            next_week_goal="Keep goal",
        )
        return journey

    def migrate(self):
        executor = MigrationExecutor(self.connection)
        executor.migrate(self.after)
        return executor.loader.project_state(self.after).apps

    def apply_live_profile(self):
        for slug, fields in LIVE_OVERRIDES.items():
            self.Stage.objects.using(self.alias).filter(slug=slug).update(**fields)

    def test_migration_preserves_all_historical_fields_and_foreign_keys(self):
        self.assert_historical_data_preserved()

    def test_confirmed_profile_preserves_all_historical_fields_and_foreign_keys(self):
        self.apply_live_profile()
        from traineediary.services.stage_catalog import check_stage_catalog

        self.assertEqual(check_stage_catalog(database=self.alias, classified=False), [])
        self.assert_historical_data_preserved()

    def assert_historical_data_preserved(self):
        for index, slug in enumerate(
            (
                "first-day",
                "before-tickets",
                "sandbox-candidate",
                "with-review",
                "no-review",
                "done",
            )
        ):
            journey = self.journey(slug, index)
            if slug == "done":
                self.Journey.objects.using(self.alias).filter(pk=journey.pk).update(
                    completion_status="success",
                    completed_at="2026-01-03",
                    completion_comment="Keep result",
                )
        original = {
            name: list(model.objects.using(self.alias).order_by("pk").values())
            for name, model in (
                ("TraineeStage", self.Stage),
                ("TraineeJourney", self.Journey),
                ("StageHistory", self.History),
                ("WeeklyMetric", self.Metric),
            )
        }
        apps = self.migrate()
        for name, rows in original.items():
            model = apps.get_model("traineediary", name)
            migrated = list(
                model.objects.using(self.alias)
                .filter(pk__in=[row["id"] for row in rows])
                .order_by("pk")
                .values()
            )
            for actual in migrated:
                if name == "TraineeJourney":
                    self.assertEqual(actual.pop("stage_scheme"), "legacy")
                elif name == "TraineeStage":
                    scope = actual.pop("catalog_scope")
                    self.assertEqual(
                        scope,
                        (
                            "legacy"
                            if actual["slug"] in self.contract.LEGACY_SLUGS
                            else "shared"
                        ),
                    )
            self.assertEqual(rows, migrated)
        new_stage = (
            apps.get_model("traineediary", "TraineeStage")
            .objects.using(self.alias)
            .get(slug="training-program")
        )
        self.assertNotIn(new_stage.pk, [row["id"] for row in original["TraineeStage"]])
        self.assertEqual(
            (new_stage.min_days, new_stage.max_days, new_stage.progress_weight_percent),
            (10, 14, 35),
        )
        self.assertEqual(new_stage.catalog_scope, "unified")
        self.assertEqual(
            self.contract.catalog_issues(
                apps.get_model("traineediary", "TraineeStage"),
                apps.get_model("traineediary", "TraineeJourney"),
                apps.get_model("traineediary", "StageHistory"),
                self.alias,
                classified=True,
            ),
            [],
        )

    def test_all_partial_combinations_of_confirmed_changes_are_rejected(self):
        changes = [(slug, field, value) for slug, fields in LIVE_OVERRIDES.items()
                   for field, value in fields.items()]
        self.assertEqual(len(changes), 10)
        Stage, Journey, History = MagicMock(), MagicMock(), MagicMock()
        Journey.objects.using.return_value.exists.return_value = False
        History.objects.using.return_value.exists.return_value = False
        for mask in range(1, (1 << len(changes)) - 1):
            stages = {slug: SimpleNamespace(pk=i, slug=slug, **fields)
                      for i, (slug, fields) in enumerate(self.contract.LEGACY_CATALOG.items(), 1)}
            for bit, (slug, field, value) in enumerate(changes):
                if mask & (1 << bit):
                    setattr(stages[slug], field, value)
            Stage.objects.using.return_value.all.return_value = list(stages.values())
            with self.subTest(mask=mask):
                self.assertTrue(self.contract.catalog_issues(Stage, Journey, History, self.alias))

    def test_confirmed_profile_still_rejects_unsupported_changes(self):
        self.apply_live_profile()
        changes = {
            "name": "Unsupported name", "group": "teachbase",
            "progress_weight_percent": 99, "applies_to_new_hire": False,
            "applies_to_internal_transfer": False, "order": 70,
            "min_days": 29, "max_days": 36,
        }
        for field, value in changes.items():
            with self.subTest(field=field):
                original = getattr(self.Stage.objects.using(self.alias).get(slug="with-review"), field)
                self.Stage.objects.using(self.alias).filter(slug="with-review").update(**{field: value})
                issues = self.contract.catalog_issues(self.Stage, self.Journey, self.History, self.alias)
                self.assertTrue(any(field + "=" in issue for issue in issues))
                self.Stage.objects.using(self.alias).filter(slug="with-review").update(**{field: original})

    def test_confirmed_profile_rejects_unknown_and_missing_stages(self):
        self.apply_live_profile()
        self.journey("with-review", 0)
        extra = self.Stage.objects.using(self.alias).create(
            slug="custom-teachbase", name="Custom", order=50, group="teachbase"
        )
        with self.assertRaisesRegex(RuntimeError, "неизвестный этап"):
            self.migrate()
        extra.delete(using=self.alias)
        self.Stage.objects.using(self.alias).filter(slug="first-day").delete()
        with self.assertRaisesRegex(RuntimeError, "Отсутствует исторический этап first-day"):
            self.migrate()

    def test_confirmed_profile_preserves_accepted_labels_and_activity(self):
        self.apply_live_profile()
        self.Stage.objects.using(self.alias).filter(slug="sandbox-candidate").update(
            name="Задания в Ticket Sandbox", color="#123456", is_active=False
        )
        self.Stage.objects.using(self.alias).filter(slug="optional-review").update(
            name="Проверки по желанию"
        )
        self.assert_historical_data_preserved()

    def test_program_in_use_is_still_rejected_with_confirmed_profile(self):
        self.apply_live_profile()
        self.Stage.objects.using(self.alias).create(
            slug="training-program", **self.contract.TRAINING_PROGRAM
        )
        self.journey("training-program", 0)
        with self.assertRaisesRegex(RuntimeError, "training-program уже используется"):
            self.migrate()

    def test_unknown_catalog_aborts_without_changing_data(self):
        journey = self.journey("vds", 0)
        self.Stage.objects.using(self.alias).create(
            slug="custom-teachbase", name="Custom", order=50, group="teachbase"
        )
        with self.assertRaisesRegex(RuntimeError, "неизвестный этап"):
            self.migrate()
        self.assertFalse(
            self.Stage.objects.using(self.alias)
            .filter(slug="training-program")
            .exists()
        )
        journey.refresh_from_db(using=self.alias)
        self.assertEqual(journey.current_stage.slug, "vds")
        self.assertEqual(self.History.objects.using(self.alias).count(), 1)

    def test_conflicting_program_aborts(self):
        self.Stage.objects.using(self.alias).create(
            slug="training-program", name="Wrong", order=1, group="teachbase"
        )
        with self.assertRaisesRegex(RuntimeError, "training-program"):
            self.migrate()
        self.assertEqual(
            self.Stage.objects.using(self.alias).get(slug="training-program").name,
            "Wrong",
        )

    def test_readonly_preflight_works_before_schema_migrations(self):
        from traineediary.services.stage_catalog import check_stage_catalog

        self.assertEqual(check_stage_catalog(database=self.alias, classified=False), [])
        self.Stage.objects.using(self.alias).filter(slug="vds").update(max_days=99)
        self.assertTrue(
            any(
                "max_days" in issue
                for issue in check_stage_catalog(database=self.alias, classified=False)
            )
        )

    def test_migration_refuses_changed_parameters_and_missing_historical_catalog(self):
        self.journey("vds", 0)
        self.Stage.objects.using(self.alias).filter(slug="first-day").delete()
        self.Stage.objects.using(self.alias).filter(slug="vds").update(
            progress_weight_percent=99
        )
        with self.assertRaisesRegex(RuntimeError, "progress_weight_percent"):
            self.migrate()
        self.assertFalse(
            self.Stage.objects.using(self.alias)
            .filter(slug="training-program")
            .exists()
        )

    def test_data_migration_is_irreversible_to_protect_new_scheme_identity(self):
        self.migrate()
        executor = MigrationExecutor(self.connection)
        with self.assertRaises(IrreversibleError):
            executor.migrate(self.before)
