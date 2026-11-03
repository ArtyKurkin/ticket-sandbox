"""Final rollout checks on synthetic data with schema 0008 already applied."""
from datetime import date, datetime, timedelta, timezone as dt_timezone
from unittest.mock import patch

from django.apps import apps
from django.contrib.auth.models import User
from django.db import connection, migrations
from django.db.migrations.loader import MigrationLoader
from django.test import TransactionTestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from deploy import audit_traineediary_unification as audit
from traineediary.models import StageHistory, StageSchemeTransfer, StageSchemeTransferBatch, TraineeJourney, TraineeStage
from traineediary.services.unification import TransferError, fingerprints, migrate_schemes, read_source
from .test_unification import populate


TODAY = date(2026, 11, 3)


class UnificationReadinessTests(TransactionTestCase):
    def setUp(self):
        self.baseline = populate()

    def all_rows(self):
        return {model._meta.label: list(model.objects.order_by(model._meta.pk.name).values())
                for model in apps.get_models()}

    def login_staff(self):
        self.client.force_login(User.objects.get(username="transfer-test-staff"))

    def assert_no_sql_writes(self, queries):
        self.assertTrue(queries)
        self.assertTrue(all(q["sql"].lstrip().upper().startswith("SELECT") for q in queries))

    def test_new_web_legacy_kanban_and_fragment_after_0008_are_select_only(self):
        self.assertIn("traineediary_stageschemetransfer", connection.introspection.table_names())
        self.assertFalse(StageSchemeTransfer.objects.exists())
        self.assertFalse(StageSchemeTransferBatch.objects.exists())
        self.login_staff()
        before = self.all_rows()
        with CaptureQueriesContext(connection) as queries:
            page = self.client.get(reverse("traineediary:trainees_kanban"))
            fragment = self.client.get(reverse("traineediary:kanban_board_fragment"))
        self.assertEqual(page.status_code, 200)
        self.assertEqual(fragment.status_code, 200)
        boards = {board["scheme"]: board for board in page.context["boards"]}
        legacy = boards["legacy"]
        self.assertEqual(sum(len(c["cards"]) for c in legacy["columns"]), 3)
        self.assertEqual(sum(len(c["cards"]) for c in legacy["done_columns"]), 11)
        self.assertContains(page, "VDS")
        self.assert_no_sql_writes(queries)
        self.assertEqual(before, self.all_rows())
        self.assertEqual(TraineeJourney.objects.filter(stage_scheme="legacy").count(), 14)

    def test_all_fourteen_legacy_detail_pages_after_0008_are_select_only(self):
        self.login_staff()
        journeys = list(TraineeJourney.objects.select_related("current_stage"))
        before = self.all_rows()
        with CaptureQueriesContext(connection) as queries:
            for journey in journeys:
                response = self.client.get(reverse("traineediary:trainee_detail", args=[journey.pk]))
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, journey.current_stage.name)
                self.assertContains(response, "Original mentor note")
        self.assert_no_sql_writes(queries)
        self.assertEqual(before, self.all_rows())

    def prepare_vds(self):
        journey = TraineeJourney.objects.get(current_stage__slug="vds")
        started = TODAY - timedelta(days=8)
        opened = journey.stage_history.get(ended_at=None)
        journey.stage_history.filter(ended_at=opened.started_at).update(ended_at=started)
        StageHistory.objects.filter(pk=opened.pk).update(started_at=started)
        TraineeJourney.objects.filter(pk=journey.pk).update(stage_started_at=started, manual_risk_override="")
        data = read_source("default")
        self.baseline = audit.build_report(data, TODAY, {"read_only": True})
        self.baseline["preservation_baseline"] = fingerprints(data)
        journey.refresh_from_db()
        return journey, started

    def test_vds_progress_preserved_while_deadline_and_derived_risk_use_new_stage(self):
        with patch("django.utils.timezone.localdate", return_value=TODAY):
            journey, started = self.prepare_vds()
            self.assertEqual(journey.progress_percent, 18)
            self.assertEqual(journey.expected_stage_transition_date, date(2026, 11, 2))
            self.assertEqual(journey.risk_level, "medium")
            self.assertAlmostEqual(journey.stage_overstay_ratio, 8 / 7)
            migrate_schemes(self.baseline, execute=True)
            journey.refresh_from_db()
            self.assertEqual(journey.current_stage.slug, "training-program")
            self.assertEqual(journey.stage_started_at, started)
            self.assertEqual(journey.days_on_stage, 8)
            self.assertEqual(journey.progress_percent, 18)
            self.assertEqual(journey.expected_stage_transition_date, date(2026, 11, 9))
            self.assertAlmostEqual(journey.stage_overstay_ratio, 8 / 14)
            self.assertEqual(journey.risk_level, "low")
            self.assertEqual(journey.stage_history.get(ended_at=None).stage.slug, "vds")
            self.assertFalse(journey.roadmap_confirmation_events.exists())

    def test_vds_source_progress_continues_until_first_real_transition(self):
        with patch("django.utils.timezone.localdate", return_value=TODAY):
            journey, started = self.prepare_vds()
            migrate_schemes(self.baseline, execute=True)
        for today, risk in ((date(2026, 11, 8), "low"), (date(2026, 11, 18), "high")):
            with self.subTest(today=today), patch("django.utils.timezone.localdate", return_value=today):
                journey.refresh_from_db()
                self.assertTrue(journey.scheme_transfer.continues_source_stage(journey))
                self.assertEqual(journey.progress_percent, 18)
                self.assertEqual(journey.risk_level, risk)
                self.assertEqual(journey.stage_started_at, started)
                self.assertEqual(journey.expected_stage_transition_date, date(2026, 11, 9))
        with patch("django.utils.timezone.localdate", return_value=date(2026, 11, 18)):
            journey.move_to_stage(TraineeStage.objects.get(slug="sandbox-candidate"))
            journey.refresh_from_db()
            self.assertFalse(journey.scheme_transfer.continues_source_stage(journey))
            self.assertEqual(journey.progress_percent, 35)
            self.assertEqual(journey.expected_stage_transition_date, date(2026, 11, 21))
            self.assertEqual(journey.risk_level, "low")
            self.assertEqual(journey.stage_history.count(), 3)
            self.assertFalse(journey.roadmap_confirmation_events.exists())

    def test_rollback_after_a_real_transition_refuses_and_preserves_the_new_history(self):
        migrate_schemes(self.baseline, execute=True)
        journey = TraineeJourney.objects.get(scheme_transfer__source_stage__slug="vds")
        journey.move_to_stage(TraineeStage.objects.get(slug="sandbox-candidate"))
        before = self.all_rows()
        for execute in (False, True):
            with self.assertRaisesRegex(TransferError, "post_snapshot_changed"):
                migrate_schemes(self.baseline, action="rollback", execute=execute)
        self.assertEqual(before, self.all_rows())
        self.assertEqual(StageHistory.objects.count(), 65)

    def test_rollback_also_refuses_after_an_unrelated_user_registration(self):
        migrate_schemes(self.baseline, execute=True)
        User.objects.create_user(username="new-user-after-transfer")
        before = self.all_rows()
        with self.assertRaisesRegex(TransferError, "post_snapshot_changed"):
            migrate_schemes(self.baseline, action="rollback", execute=True)
        self.assertEqual(before, self.all_rows())

    def test_elapsed_time_and_last_login_alone_do_not_block_rollback_dryrun(self):
        with patch("django.utils.timezone.localdate", return_value=TODAY):
            migrate_schemes(self.baseline, execute=True)
        User.objects.filter(username="transfer-test-staff").update(
            last_login=datetime(2026, 11, 4, tzinfo=dt_timezone.utc),
        )
        before = self.all_rows()
        with patch("django.utils.timezone.localdate", return_value=date(2026, 11, 18)):
            result = migrate_schemes(self.baseline, action="rollback")
        self.assertEqual(result["status"], "rollback_ready")
        self.assertFalse(result["changed"])
        self.assertEqual(before, self.all_rows())

    def test_migration_graph_has_schema_only_0008_and_no_0009(self):
        loader = MigrationLoader(connection)
        migration = loader.disk_migrations[("traineediary", "0008_stageschemetransfer")]
        self.assertEqual(migration.dependencies, [("traineediary", "0007_classify_stage_catalog")])
        self.assertEqual([type(op) for op in migration.operations], [migrations.CreateModel, migrations.CreateModel, migrations.RunPython])
        self.assertIs(migration.operations[-1].code, migrations.RunPython.noop)
        self.assertIsNone(migration.operations[-1].reverse_code)
        self.assertFalse(any(app == "traineediary" and name.startswith("0009") for app, name in loader.disk_migrations))
        self.assertEqual(loader.graph.leaf_nodes("traineediary"), [("traineediary", "0008_stageschemetransfer")])
