"""Synthetic audit tests; optional PostgreSQL runs on a private local Unix socket.

No existing application database, Docker, backup or live service is contacted.
"""
from copy import deepcopy
from datetime import date, datetime, timezone
from decimal import Decimal
from io import StringIO
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from deploy import audit_traineediary_unification as audit


TODAY = date(2026, 11, 3)
PRIVATE_TEXT = "PRIVATE synthetic comment: never print this"


def fixture():
    stages = []
    for pk, (slug, spec) in enumerate(audit.CONFIRMED_CATALOG.items(), 1):
        stages.append({"id": pk, "slug": slug, "name": slug,
                       "color": "#123456", "is_active": True,
                       **dict(zip(audit.CATALOG_FIELDS, spec))})
    return {"stages": stages, "journeys": [], "history": [], "metrics": [], "roadmap": [],
            "user_links": [{"id": 100, "is_staff": True}],
            "migrations": [{"app": "traineediary", "name": "0007_classify_stage_catalog"},
                           {"app": "roadmap", "name": "0001_initial"}]}


def add_journey(data, slugs=("vds",), *, scheme="legacy", entry="new_hire", outcome=""):
    jid = len(data["journeys"]) + 1
    stage_ids = {s["slug"]: s["id"] for s in data["stages"]}
    data["user_links"].append({"id": jid, "is_staff": False})
    journey = {
        "id": jid, "user_id": jid, "entry_type": entry, "stage_scheme": scheme,
        "probation_start_date": date(2026, 10, 1), "stage_started_at": date(2026, 10, len(slugs)),
        "current_stage_id": stage_ids[slugs[-1]], "comment": PRIVATE_TEXT,
        "manual_risk_override": "", "fixed_quality_percent": 87,
        "quality_fixed_at": date(2026, 10, 1), "completion_status": outcome,
        "completed_at": date(2026, 10, len(slugs)) if outcome else None,
        "completion_comment": PRIVATE_TEXT if outcome else "", "completed_by_id": 100 if outcome else None,
    }
    data["journeys"].append(journey)
    for index, slug in enumerate(slugs, 1):
        data["history"].append({"id": len(data["history"]) + 1, "journey_id": jid,
                                "stage_id": stage_ids[slug], "started_at": date(2026, 10, index),
                                "ended_at": date(2026, 10, index + 1) if index < len(slugs) else None,
                                "changed_by_id": 100, "note": PRIVATE_TEXT})
    data["metrics"].append({"id": jid, "journey_id": jid, "week_number": 1,
                            "week_start_date": date(2026, 10, 1), "speed_hours": Decimal("4.5"),
                            "quality_percent": 87, "mentor_comment": PRIVATE_TEXT, "next_week_goal": PRIVATE_TEXT})
    return journey


class AuditTests(unittest.TestCase):
    def setUp(self):
        self.data = fixture()

    def report(self):
        return audit.build_report(self.data, TODAY, {"read_only": True})

    def test_empty_audit_does_not_invent_eleven_completed_employees(self):
        self.assertEqual(self.report()["counts"]["legacy_done"], 0)
        self.assertFalse(self.report()["integrity"]["migration_authorized"])

    def test_every_legacy_stage_has_an_exact_mapping(self):
        for slug in sorted(audit.MAPPING):
            add_journey(self.data, (slug,), outcome="success" if slug == "done" else "")
        rows = self.report()["proposed_mapping"]
        self.assertEqual(len(rows), 10)
        self.assertEqual({r["from"]: r["to"] for r in rows}, audit.MAPPING)
        self.assertTrue(self.report()["integrity"]["ready_for_mapping_review"])

    def test_eleven_completed_are_counted_without_creating_adaptations(self):
        for _ in range(11):
            add_journey(self.data, ("done",), outcome="success")
        report = self.report()
        self.assertEqual(report["counts"]["legacy_done"], 11)
        self.assertEqual(report["proposed_preservation_policy"]["new_journeys"], 0)
        self.assertEqual(report["naive_progress_recalculation"]["equal"], 11)

    def test_terminated_and_done_without_evidence_are_distinct(self):
        add_journey(self.data, ("done",), outcome="terminated")
        add_journey(self.data, ("done",))
        report = self.report()
        self.assertEqual({r["outcome"] for r in report["probation_evidence"]}, {"terminated", "insufficient_data"})
        self.assertEqual(report["integrity"]["warning_journey_counts"]["done_without_proven_probation_outcome"], 1)

    def test_internal_transfer_never_requires_theory(self):
        add_journey(self.data, ("with-review", "optional-review"), entry="internal_transfer")
        report = self.report()
        self.assertTrue(report["integrity"]["ready_for_mapping_review"])
        self.assertEqual(report["proposed_mapping"][0]["to"], "optional-review")
        self.assertEqual(report["theory"], {})

    def test_internal_transfer_in_theory_is_blocked(self):
        add_journey(self.data, ("vds",), entry="internal_transfer")
        report = self.report()
        self.assertFalse(report["integrity"]["ready_for_mapping_review"])
        self.assertEqual(report["integrity"]["blocked_legacy_journeys"], 1)

    def test_partial_theory_does_not_grant_training_confirmation(self):
        add_journey(self.data, ("first-day", "vds"))
        report = self.report()
        self.assertEqual(report["theory"]["subset_of_theory_stages_visited"], 1)
        self.assertEqual(report["roadmap"]["latest_training_confirmation"], [])
        self.assertEqual(report["proposed_preservation_policy"]["roadmap_confirmations_created"], 0)

    def test_default_catalog_theory_after_sandbox_requires_review(self):
        for stage in self.data["stages"]:
            stage.update(dict(zip(audit.CATALOG_FIELDS, audit.DEFAULT_CATALOG[stage["slug"]])))
        add_journey(self.data, ("sandbox-candidate", "before-tickets"))
        report = self.report()
        self.assertEqual(report["catalog_profile"], "default")
        self.assertEqual(report["integrity"]["warning_journey_counts"]["theory_after_sandbox_requires_review"], 1)

    def test_naive_unified_recalculation_detects_progress_loss(self):
        j = add_journey(self.data, ("first-day", "vds", "managed-services", "client-service", "before-tickets"))
        j["stage_started_at"] = TODAY
        self.data["history"][-1]["started_at"] = TODAY
        self.data["history"][-2]["ended_at"] = TODAY
        report = self.report()
        self.assertEqual(report["naive_progress_recalculation"]["lower"], 1)

    def test_histories_metrics_dates_comments_and_links_are_not_mutated(self):
        add_journey(self.data, ("first-day", "vds"))
        before = deepcopy(self.data)
        report = self.report()
        self.assertEqual(self.data, before)
        self.assertEqual(report["preservation_baseline"]["nonempty_text_counts"]["metric_mentor_comments"], 1)
        self.assertFalse(report["preservation_baseline"]["post_migration_preservation_verified"])
        self.assertEqual(report, self.report())

    def test_fingerprints_detect_each_preserved_field_change(self):
        add_journey(self.data)
        baseline = self.report()["preservation_baseline"]["snapshot_sha256"]
        for table, field, changed in (
            ("journeys", "comment", "changed"), ("journeys", "completed_by_id", 999),
            ("journeys", "stage_started_at", date(2026, 10, 2)),
            ("history", "note", "changed"), ("history", "changed_by_id", 999),
            ("metrics", "speed_hours", Decimal("5.5")), ("metrics", "mentor_comment", "changed"),
            ("metrics", "week_start_date", date(2026, 10, 2)),
        ):
            with self.subTest(table=table, field=field):
                original = self.data[table][0][field]
                self.data[table][0][field] = changed
                self.assertNotEqual(baseline, self.report()["preservation_baseline"]["snapshot_sha256"])
                self.data[table][0][field] = original

    def test_reports_have_no_identifiers_texts_individual_dates_or_unknown_values(self):
        add_journey(self.data)
        self.data["stages"][0]["name"] = PRIVATE_TEXT
        self.data["stages"][0]["slug"] = PRIVATE_TEXT
        self.data["journeys"][0]["entry_type"] = PRIVATE_TEXT
        report = json.dumps(self.report())
        for forbidden in (PRIVATE_TEXT, '"journey_id"', '"user_id"', '"actor_id"', '"2026-10-01"'):
            self.assertNotIn(forbidden, report)

    def test_broken_history_and_missing_links_are_blockers(self):
        add_journey(self.data, ("first-day", "vds"))
        self.data["history"][0]["ended_at"] = None
        self.data["history"][1]["changed_by_id"] = 999
        self.data["metrics"][0]["quality_percent"] = 101
        report = self.report()
        codes = report["integrity"]["issue_journey_counts"]
        for expected in ("ambiguous_open_history", "history_gap_or_overlap", "missing_history_author_link", "invalid_weekly_metric"):
            self.assertIn(expected, codes)
        self.assertFalse(report["integrity"]["ready_for_mapping_review"])

    def test_orphan_roadmap_event_is_reported_without_printing_text(self):
        self.data["roadmap"].append({"id": 1, "journey_id": 999, "actor_id": 100,
                                    "stage_code": "training", "action": "confirmed",
                                    "created_at": datetime(2026, 10, 1, tzinfo=timezone.utc), "comment": PRIVATE_TEXT})
        report = self.report()
        self.assertEqual(report["integrity"]["global_blockers"]["orphan_roadmap"], 1)
        self.assertNotIn(PRIVATE_TEXT, json.dumps(report))

    def test_completed_work_progress_and_latest_training_confirmation_are_retained(self):
        j = add_journey(self.data, ("with-review", "optional-review", "no-review", "done"), outcome="success")
        for i, action in enumerate(("confirmed", "revoked", "confirmed"), 1):
            self.data["roadmap"].append({"id": i, "journey_id": j["id"], "actor_id": 100,
                                        "stage_code": "training", "action": action,
                                        "created_at": datetime(2026, 10, 1, tzinfo=timezone.utc), "comment": PRIVATE_TEXT})
        report = self.report()
        self.assertEqual({r["stage"] for r in report["roadmap"]["proven_work_stage_completions"]},
                         {"with-review", "optional-review", "no-review"})
        self.assertEqual(report["roadmap"]["latest_training_confirmation"][0]["action"], "confirmed")

    def test_a_return_invalidates_an_earlier_roadmap_completion(self):
        add_journey(self.data, ("with-review", "optional-review", "with-review"))
        self.assertEqual(self.report()["roadmap"]["proven_work_stage_completions"], [])

    def test_existing_unified_journeys_are_counted_but_not_remapped(self):
        add_journey(self.data, ("training-program",), scheme="unified")
        report = self.report()
        self.assertEqual(report["counts"]["unified_journeys"], 1)
        self.assertEqual(report["proposed_mapping"], [])

    def test_catalog_hybrids_are_not_silently_accepted(self):
        self.data["stages"][0]["max_days"] = 999
        self.assertEqual(self.report()["integrity"]["global_blockers"]["unsupported_stage_catalog"], 1)

    def test_unknown_or_missing_schema_is_blocked(self):
        self.data["migrations"] = []
        self.assertFalse(self.report()["required_schema_recorded"])
        self.assertFalse(self.report()["integrity"]["ready_for_mapping_review"])

    def test_errors_are_json_and_never_disclose_connection_or_sql(self):
        with patch.object(audit, "run", side_effect=RuntimeError(PRIVATE_TEXT)), patch("sys.stdout", new_callable=StringIO) as output:
            self.assertEqual(audit.main(), 1)
        result = json.loads(output.getvalue())
        self.assertEqual(result["error"], "audit_failed")
        self.assertNotIn(PRIVATE_TEXT, output.getvalue())

    def test_queries_are_explicit_selects_with_no_sandbox_or_credentials(self):
        for query in audit.QUERIES.values():
            self.assertTrue(query.startswith("SELECT "))
            self.assertNotIn("sandbox_", query)
            for forbidden in ("password", "email", "username", "token"):
                self.assertNotIn(forbidden, query)


@unittest.skipUnless(os.environ.get("TP_AUDIT_POSTGRES_BIN"), "private local PostgreSQL opt-in required")
class PostgresAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import psycopg

        cls.bin = Path(os.environ["TP_AUDIT_POSTGRES_BIN"])
        cls.temp = tempfile.TemporaryDirectory(prefix="tp-diary-audit-", dir="/tmp")
        cls.addClassCleanup(cls.temp.cleanup)
        root = Path(cls.temp.name)
        root.chmod(0o700)
        cls.data, cls.socket = root / "data", root / "socket"
        cls.socket.mkdir(mode=0o700)
        cls.env = {k: v for k, v in os.environ.items() if not k.startswith("PG")}
        cls.command([str(cls.bin / "initdb"), "-D", str(cls.data), "-U", "audit_test_admin", "-A", "trust", "--no-locale", "--encoding=UTF8"])
        cls.command([str(cls.bin / "pg_ctl"), "-D", str(cls.data), "-l", str(root / "postgres.log"),
                     "-o", f"-h '' -k {cls.socket}", "-w", "start"])
        cls.addClassCleanup(lambda: cls.command([str(cls.bin / "pg_ctl"), "-D", str(cls.data), "-m", "fast", "-w", "stop"]))
        cls.kwargs = {"host": str(cls.socket), "dbname": "postgres", "user": "audit_test_admin", "autocommit": True}
        cls.conn = psycopg.connect(**cls.kwargs)
        cls.addClassCleanup(cls.conn.close)

    @classmethod
    def command(cls, argv):
        result = subprocess.run(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30, env=cls.env)
        if result.returncode:
            raise RuntimeError("Private synthetic PostgreSQL command failed")

    def setUp(self):
        from psycopg import sql

        self.sample = fixture()
        add_journey(self.sample, ("first-day", "vds"))
        self.tables = {
            "stages": "traineediary_traineestage", "journeys": "traineediary_traineejourney",
            "history": "traineediary_stagehistory", "metrics": "traineediary_weeklymetric",
            "roadmap": "roadmap_trainingconfirmationevent", "user_links": "auth_user", "migrations": "django_migrations",
        }
        # Empty roadmap still needs a real table with the deployed projection.
        self.sample["roadmap"].append({"id": 1, "journey_id": 1, "actor_id": 100, "stage_code": "training", "action": "confirmed",
                                       "created_at": datetime(2026, 10, 1, tzinfo=timezone.utc), "comment": PRIVATE_TEXT})
        def pg_type(field, value):
            if field == "created_at":
                return "timestamptz"
            if field in {"started_at", "ended_at", "completed_at", "quality_fixed_at", "probation_start_date", "stage_started_at", "week_start_date"}:
                return "date"
            if isinstance(value, bool):
                return "boolean"
            if isinstance(value, int) or field.endswith("_id"):
                return "integer"
            if isinstance(value, Decimal):
                return "numeric"
            return "text"
        with self.conn.cursor() as cursor:
            cursor.execute("DROP SCHEMA public CASCADE")
            cursor.execute("CREATE SCHEMA public")
            for key, table in self.tables.items():
                rows = self.sample[key]
                columns = list(rows[0])
                specs = [sql.SQL("{} {}").format(sql.Identifier(c), sql.SQL(pg_type(c, rows[0][c]))) for c in columns]
                cursor.execute(sql.SQL("CREATE TABLE {} ({})").format(sql.Identifier(table), sql.SQL(", ").join(specs)))
                for row in rows:
                    cursor.execute(sql.SQL("INSERT INTO {} ({}) VALUES ({})").format(
                        sql.Identifier(table), sql.SQL(", ").join(map(sql.Identifier, columns)),
                        sql.SQL(", ").join(sql.Placeholder() for _ in columns)), [row[c] for c in columns])

    def connect_readonly(self):
        import psycopg

        return psycopg.connect(**self.kwargs, options="-c default_transaction_read_only=on -c statement_timeout=15000 -c lock_timeout=2000 -c idle_in_transaction_session_timeout=60000")

    def test_real_snapshot_is_readonly_and_all_source_rows_are_unchanged(self):
        from psycopg.rows import dict_row

        with self.connect_readonly() as connection:
            report = audit.read_snapshot(connection)
        self.assertTrue(report["transaction"]["read_only"])
        self.assertEqual(report["transaction"]["isolation"], "repeatable read")
        self.assertEqual(report["counts"]["legacy_journeys"], 1)
        self.assertNotIn(PRIVATE_TEXT, json.dumps(report))
        with self.conn.cursor(row_factory=dict_row) as cursor:
            for key, query in audit.QUERIES.items():
                cursor.execute(query)
                expected = sorted(self.sample[key], key=(
                    (lambda row: (row["app"], row["name"])) if key == "migrations" else (lambda row: row["id"])
                ))
                self.assertEqual(cursor.fetchall(), expected)

    def test_postgres_rejects_a_write_even_with_database_owner_privileges(self):
        import psycopg

        # Fault injection belongs only to this disposable test cluster.
        with self.connect_readonly() as connection:
            with patch.dict(audit.QUERIES, {"fault_injection": "INSERT INTO auth_user (id, is_staff) VALUES (999, false)"}):
                with self.assertRaises(psycopg.errors.ReadOnlySqlTransaction):
                    audit.read_snapshot(connection)
        with self.conn.cursor() as cursor:
            cursor.execute("SELECT count(*) FROM auth_user WHERE id=999")
            self.assertEqual(cursor.fetchone()[0], 0)

    def test_main_reads_web_environment_without_loading_django(self):
        environment = {k: v for k, v in self.env.items() if not k.startswith("DB_")}
        environment |= {"DB_NAME": "postgres", "DB_USER": "audit_test_admin", "DB_PASSWORD": "synthetic-unused", "DB_HOST": str(self.socket)}
        with patch.dict(os.environ, environment, clear=True), patch("sys.stdout", new_callable=StringIO) as output:
            self.assertEqual(audit.main(), 0)
        report = json.loads(output.getvalue())
        self.assertEqual(report["counts"]["legacy_journeys"], 1)
        self.assertFalse(report["integrity"]["migration_authorized"])


if __name__ == "__main__":
    unittest.main()
