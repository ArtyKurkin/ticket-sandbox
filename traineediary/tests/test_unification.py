"""Synthetic replica of the audited shape, never a copy of personal data."""
from copy import deepcopy
from datetime import date, timedelta
from importlib import import_module
from io import StringIO
import json
import re
import tempfile
from unittest.mock import patch

from django.apps import apps
from django.contrib.auth.models import User
from django.core.management import call_command
from django.db import connection
from django.test import TransactionTestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from deploy import audit_traineediary_unification as audit
from roadmap.services.projection import build_roadmap
from traineediary.models import StageHistory, StageSchemeTransfer, StageSchemeTransferBatch, TraineeJourney, TraineeStage, WeeklyMetric
from traineediary.services.unification import TransferError, fingerprints, load_baseline, migrate_schemes, read_source


def populate(alias="default", user_model=User):
    contract = import_module("traineediary.migrations.0007_classify_stage_catalog")
    for slug, fields in contract.CONFIRMED_LEGACY_CATALOG.items():
        TraineeStage.objects.using(alias).update_or_create(slug=slug, defaults={
            **fields, "catalog_scope": "legacy" if slug in contract.LEGACY_SLUGS else "shared",
        })
    TraineeStage.objects.using(alias).update_or_create(slug="training-program", defaults={
        **contract.TRAINING_PROGRAM, "catalog_scope": "unified",
    })
    stages = {s.slug: s.pk for s in TraineeStage.objects.using(alias).all()}
    staff = user_model.objects.using(alias).create(username="transfer-test-staff", is_staff=True)
    success = ("first-day", "vds", "before-tickets", "sandbox-candidate", "with-review", "optional-review", "no-review", "done")
    paths = [(success, "success", "new_hire")] * 5
    paths += [(("with-review", "done"), "terminated", "internal_transfer")] * 6
    paths += [(("first-day", "vds"), "", "new_hire"),
              (("first-day", "sandbox-candidate", "with-review"), "", "new_hire"),
              (("vds", "managed-services", "client-service", "before-tickets", "sandbox-candidate", "with-review", "optional-review"), "", "new_hire")]
    start = date(2026, 10, 1)
    for i, (path, outcome, entry) in enumerate(paths):
        user = user_model.objects.using(alias).create(username=f"transfer-test-{i}")
        end = start + timedelta(days=len(path) - 1)
        journey = TraineeJourney(user_id=user.pk, stage_scheme="legacy", entry_type=entry,
                                 probation_start_date=start, current_stage_id=stages[path[-1]], stage_started_at=end,
                                 comment="Original mentor note", manual_risk_override="low",
                                 fixed_quality_percent=87, quality_fixed_at=start,
                                 completion_status=outcome, completed_at=end if outcome else None,
                                 completion_comment="Original outcome note" if outcome else "",
                                 completed_by_id=staff.pk if outcome else None)
        TraineeJourney.objects.using(alias).bulk_create([journey])
        StageHistory.objects.using(alias).bulk_create([
            StageHistory(journey_id=journey.pk, stage_id=stages[slug],
                         started_at=start + timedelta(days=n),
                         ended_at=start + timedelta(days=n + 1) if n < len(path) - 1 else None,
                         changed_by_id=staff.pk, note=f"Original transition {n}")
            for n, slug in enumerate(path)
        ])
        WeeklyMetric.objects.using(alias).bulk_create([
            WeeklyMetric(journey_id=journey.pk, week_number=n + 1, week_start_date=start + timedelta(weeks=n),
                         speed_hours="4.5", quality_percent=87,
                         mentor_comment="Original weekly note", next_week_goal="Original goal")
            for n in range(3 if i < 9 else 2)
        ])
    data = read_source(alias)
    report = audit.build_report(data, date(2026, 11, 3), {"read_only": True})
    assert report["integrity"]["ready_for_mapping_review"], report["integrity"]
    assert len(data["history"]) == 64 and len(data["metrics"]) == 37
    return {**report, "preservation_baseline": fingerprints(data)}


class UnificationTests(TransactionTestCase):
    def setUp(self):
        self.baseline = populate()
        self.before = read_source("default")

    def apply(self):
        return migrate_schemes(self.baseline, execute=True)

    def test_dry_run_is_readonly_and_matches_the_audited_shape(self):
        with CaptureQueriesContext(connection) as queries:
            result = migrate_schemes(self.baseline)
        self.assertEqual(result["changed_fields"], {"stage_scheme": 14, "current_stage_id": 1})
        self.assertTrue(result["baseline_match"])
        self.assertFalse(result["changed"])
        self.assertFalse(StageSchemeTransfer.objects.exists())
        self.assertFalse(any(q["sql"].lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE")) for q in queries))
        self.assertEqual(read_source("default"), self.before)

    def test_apply_preserves_every_original_field_except_two_explicit_fields(self):
        result = self.apply()
        after = read_source("default")
        self.assertEqual(result["checks"]["progress_unchanged"], 14)
        self.assertEqual(result["checks"]["roadmap_evidence_unchanged"], 14)
        for key in ("stages", "history", "metrics", "roadmap", "user_links"):
            self.assertEqual(after[key], self.before[key])
        for old, new in zip(self.before["journeys"], after["journeys"]):
            self.assertEqual(new["stage_scheme"], "unified")
            for field, value in old.items():
                if field not in ("stage_scheme", "current_stage_id"):
                    self.assertEqual(new[field], value, field)
        self.assertEqual(TraineeJourney.objects.count(), 14)
        self.assertEqual(StageSchemeTransfer.objects.count(), 14)
        self.assertEqual(StageSchemeTransferBatch.objects.count(), 1)

    def test_vds_moves_to_training_without_confirming_theory_or_raising_progress(self):
        journey = TraineeJourney.objects.get(current_stage__slug="vds")
        before = journey.progress_percent
        self.apply()
        journey.refresh_from_db()
        self.assertEqual(journey.current_stage.slug, "training-program")
        self.assertEqual(journey.progress_percent, before)
        roadmap = build_roadmap(journey)
        training = next(s for s in roadmap["stages"] if s["id"] == "training")
        self.assertEqual(training["state"], "in_progress")
        self.assertFalse(journey.roadmap_confirmation_events.exists())
        self.assertNotIn("ambiguous_stage_history", [x["code"] for x in roadmap["data_quality"]])

    def test_success_terminated_and_internal_exemptions_survive(self):
        self.apply()
        self.assertEqual(TraineeJourney.objects.filter(completion_status="success").count(), 5)
        self.assertEqual(TraineeJourney.objects.filter(completion_status="terminated").count(), 6)
        for journey in TraineeJourney.objects.filter(current_stage__slug="done"):
            self.assertEqual(journey.progress_percent, 100)
        internal = TraineeJourney.objects.filter(entry_type="internal_transfer").first()
        stages = build_roadmap(internal)["stages"]
        self.assertEqual([s["display_status"] for s in stages[:2]], ["not_required", "not_required"])

    def test_repeat_application_and_verify_are_idempotent(self):
        self.apply()
        after = read_source("default")
        ledger = list(StageSchemeTransfer.objects.values())
        batch = list(StageSchemeTransferBatch.objects.values())
        for execute in (False, True):
            result = migrate_schemes(self.baseline, execute=execute)
            self.assertEqual(result["status"], "already_applied")
            self.assertFalse(result["changed"])
        self.assertTrue(migrate_schemes(self.baseline, action="verify")["verified"])
        self.assertEqual(after, read_source("default"))
        self.assertEqual(ledger, list(StageSchemeTransfer.objects.values()))
        self.assertEqual(batch, list(StageSchemeTransferBatch.objects.values()))

    def test_stale_baseline_refuses_all_changes(self):
        WeeklyMetric.objects.filter(pk=WeeklyMetric.objects.first().pk).update(mentor_comment="Later legitimate edit")
        current = read_source("default")
        with self.assertRaisesRegex(TransferError, "source_snapshot_differs"):
            self.apply()
        self.assertEqual(current, read_source("default"))
        self.assertFalse(StageSchemeTransfer.objects.exists())

    def test_failure_after_updates_rolls_back_everything(self):
        with patch("traineediary.services.unification.verify_runtime", side_effect=TransferError("injected_failure")):
            with self.assertRaisesRegex(TransferError, "injected_failure"):
                self.apply()
        self.assertEqual(read_source("default"), self.before)
        self.assertFalse(StageSchemeTransfer.objects.exists())
        self.assertFalse(StageSchemeTransferBatch.objects.exists())

    def test_rollback_and_repeated_rollback_restore_exact_source(self):
        self.apply()
        result = migrate_schemes(self.baseline, action="rollback")
        self.assertEqual(result["status"], "rollback_ready")
        self.assertEqual(TraineeJourney.objects.filter(stage_scheme="unified").count(), 14)
        result = migrate_schemes(self.baseline, action="rollback", execute=True)
        self.assertEqual(result["status"], "rolled_back")
        self.assertEqual(read_source("default"), self.before)
        self.assertEqual(migrate_schemes(self.baseline, action="rollback", execute=True)["status"], "already_rolled_back")
        self.assertEqual(StageSchemeTransfer.objects.count(), 14)

    def test_rollback_and_rerun_refuse_after_new_diary_writes(self):
        self.apply()
        WeeklyMetric.objects.filter(pk=WeeklyMetric.objects.first().pk).update(next_week_goal="New goal")
        current = read_source("default")
        for action in ("apply", "verify", "rollback"):
            with self.assertRaisesRegex(TransferError, "post_snapshot_changed"):
                migrate_schemes(self.baseline, action=action, execute=action != "verify")
        self.assertEqual(read_source("default"), current)

    def test_original_board_is_readonly_and_default_has_one_unified_board(self):
        self.apply()
        staff = User.objects.get(username="transfer-test-staff")
        self.client.force_login(staff)
        url = reverse("traineediary:trainees_kanban")
        response = self.client.get(url)
        self.assertEqual([b["scheme"] for b in response.context["boards"]], ["unified"])
        original = self.client.get(url + "?view=original")
        self.assertEqual(original.status_code, 200)
        self.assertContains(original, "VDS")
        self.assertNotContains(original, "data-move-url")
        self.assertNotContains(original, "js/kanban.js")
        self.assertEqual(len(original.context["transfers"]), 14)

    def test_real_transition_ends_compatibility_progress_and_keeps_history(self):
        self.apply()
        journey = TraineeJourney.objects.get(scheme_transfer__source_stage__slug="vds")
        original_history = journey.scheme_transfer.source_open_history
        journey.move_to_stage(TraineeStage.objects.get(slug="sandbox-candidate"))
        journey.refresh_from_db()
        original_history.refresh_from_db()
        self.assertEqual(original_history.stage.slug, "vds")
        self.assertIsNotNone(original_history.ended_at)
        self.assertFalse(journey.scheme_transfer.continues_source_stage(journey))
        self.assertEqual(StageHistory.objects.count(), 65)

    def test_dryrun_command_outputs_json_and_requires_execute_for_writes(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json") as file:
            json.dump(self.baseline, file)
            file.flush()
            output = StringIO()
            call_command("unify_stage_schemes", baseline=file.name, stdout=output)
        self.assertEqual(json.loads(output.getvalue())["status"], "dry_run")
        self.assertFalse(StageSchemeTransfer.objects.exists())

    def test_corrupt_provenance_is_refused_without_touching_source_data(self):
        self.apply()
        after = read_source("default")
        transfer = StageSchemeTransfer.objects.first()
        changed = dict(transfer.progress_basis, current_weight=100)
        StageSchemeTransfer.objects.filter(pk=transfer.pk).update(progress_basis=changed)
        with self.assertRaisesRegex(TransferError, "transfer_provenance_corrupt"):
            migrate_schemes(self.baseline, execute=True)
        self.assertEqual(after, read_source("default"))

    def test_committed_operator_baseline_validates_and_differs_from_synthetic_data(self):
        baseline = load_baseline("deploy/traineediary_unification_baseline_2026-11-03.json")
        self.assertEqual(baseline["counts"]["legacy_journeys"], 14)
        with self.assertRaisesRegex(TransferError, "source_snapshot_differs"):
            migrate_schemes(baseline, execute=True)
        self.assertFalse(StageSchemeTransfer.objects.exists())

    def test_missing_or_invalid_hash_is_refused(self):
        invalid = deepcopy(self.baseline)
        invalid["preservation_baseline"]["tables"]["history"]["sha256"] = "invalid"
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json") as file:
            json.dump(invalid, file)
            file.flush()
            with self.assertRaisesRegex(TransferError, "invalid_baseline"):
                load_baseline(file.name)

    def test_missing_provenance_is_not_reported_as_successful_repeat(self):
        self.apply()
        StageSchemeTransfer.objects.first().delete()
        with self.assertRaisesRegex(TransferError, "transfer_provenance_incomplete"):
            migrate_schemes(self.baseline)

    def test_roadmap_work_completions_unchanged_for_every_journey(self):
        before = {j.pk: {s["id"] for s in build_roadmap(j)["stages"] if s["state"] == "completed"}
                  for j in TraineeJourney.objects.all()}
        self.apply()
        after = {j.pk: {s["id"] for s in build_roadmap(j)["stages"] if s["state"] == "completed"}
                 for j in TraineeJourney.objects.all()}
        self.assertEqual(before, after)

    def test_award_eligibility_is_unchanged_and_no_grants_are_created(self):
        from achievements.models import AchievementDefinition, AchievementEvent, UserAchievement
        from achievements.services.catalog import seed_catalog
        from achievements.services.evaluators import evaluate
        seed_catalog()
        definitions = list(AchievementDefinition.objects.filter(evaluator_key__in=[
            "training_program", "review_quality", "independent_speed", "probation_new_hire", "independent_engineer",
        ]))
        def reports():
            return {(j.pk, definition.pk): evaluate(user_id=j.user_id, definition=definition).report()
                    for j in TraineeJourney.objects.all() for definition in definitions}
        before = reports()
        self.apply()
        self.assertEqual(before, reports())
        self.assertEqual(AchievementEvent.objects.count(), 0)
        self.assertEqual(UserAchievement.objects.count(), 0)

    def test_partial_catalog_changes_or_ambiguous_history_block_a_matching_baseline(self):
        closed = StageHistory.objects.filter(ended_at__isnull=False).first()
        StageHistory.objects.filter(pk=closed.pk).update(ended_at=None)
        current = read_source("default")
        baseline = deepcopy(self.baseline)
        baseline["preservation_baseline"] = fingerprints(current)
        with self.assertRaisesRegex(TransferError, "audit_has_blockers"):
            migrate_schemes(baseline, execute=True)
        self.assertFalse(StageSchemeTransfer.objects.exists())

    def test_no_award_or_sandbox_writes_or_roadmap_confirmation_writes(self):
        models = [m for m in apps.get_models() if m._meta.app_label in ("achievements", "sandbox", "roadmap")]
        counts = {m._meta.label: m.objects.count() for m in models}
        with CaptureQueriesContext(connection) as queries:
            self.apply()
        self.assertEqual(counts, {m._meta.label: m.objects.count() for m in models})
        for query in queries:
            sql = query["sql"].lstrip().upper()
            if sql.startswith(("INSERT", "UPDATE", "DELETE")):
                target = re.match(r'(?:INSERT INTO|UPDATE|DELETE FROM) "([^"]+)"', sql)
                self.assertIsNotNone(target)
                self.assertTrue(target[1].startswith("TRAINEEDIARY_"))
