"""Opt-in migration proof on a private PostgreSQL 16 cluster, Unix socket only."""
from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor
import os
from pathlib import Path
import subprocess
import tempfile
from threading import Barrier
import unittest
from unittest.mock import patch

from django.db import connections, DatabaseError
from django.core.management import call_command
from io import StringIO
from django.db.backends.postgresql.base import DatabaseWrapper
from django.db.migrations.executor import MigrationExecutor
from django.db.migrations.exceptions import IrreversibleError

from traineediary.models import StageSchemeTransfer, StageSchemeTransferBatch, TraineeJourney, WeeklyMetric
from traineediary.services.unification import TransferError, migrate_schemes, read_source
from .test_unification import populate


def start_at_0007(test):
    test.initial_migration = "0007_classify_stage_catalog"
    return test


@unittest.skipUnless(os.environ.get("TP_UNIFICATION_POSTGRES_BIN"), "private PostgreSQL opt-in required")
class PostgresUnificationTests(unittest.TestCase):
    alias = "unification_private_postgres"

    @classmethod
    def setUpClass(cls):
        cls.bin = Path(os.environ["TP_UNIFICATION_POSTGRES_BIN"])
        cls.temp = tempfile.TemporaryDirectory(prefix="tp-unify-test-", dir="/tmp")
        cls.addClassCleanup(cls.temp.cleanup)
        root = Path(cls.temp.name)
        root.chmod(0o700)
        cls.data, cls.socket = root / "data", root / "socket"
        cls.socket.mkdir(mode=0o700)
        cls.env = {k: v for k, v in os.environ.items() if not k.startswith("PG")}
        cls.command([str(cls.bin / "initdb"), "-D", str(cls.data), "-U", "unification_test_admin", "-A", "trust", "--no-locale", "--encoding=UTF8"])
        cls.command([str(cls.bin / "pg_ctl"), "-D", str(cls.data), "-l", str(root / "postgres.log"),
                     "-o", f"-h '' -k {cls.socket}", "-w", "start"])
        cls.addClassCleanup(lambda: cls.command([str(cls.bin / "pg_ctl"), "-D", str(cls.data), "-m", "fast", "-w", "stop"]))

    @classmethod
    def command(cls, argv):
        result = subprocess.run(argv, env=cls.env, capture_output=True, timeout=30)
        if result.returncode:
            raise RuntimeError("Private PostgreSQL setup failed")

    def setUp(self):
        settings = deepcopy(connections["default"].settings_dict)
        settings.update(ENGINE="django.db.backends.postgresql", NAME="postgres", USER="unification_test_admin",
                        PASSWORD="", HOST=str(self.socket), PORT="5432", OPTIONS={})
        self.connection = DatabaseWrapper(settings, alias=self.alias)
        connections[self.alias] = self.connection
        self.addCleanup(self.close)
        with self.connection.cursor() as cursor:
            cursor.execute("DROP SCHEMA public CASCADE")
            cursor.execute("CREATE SCHEMA public")
        executor = MigrationExecutor(self.connection)
        version = getattr(getattr(self, self._testMethodName), "initial_migration", "0008_stageschemetransfer")
        self.targets = [("traineediary", version), ("roadmap", "0001_initial")]
        self.targets += executor.loader.graph.leaf_nodes("auth")
        executor.migrate(self.targets)
        historical = executor.loader.project_state(self.targets).apps
        self.baseline = populate(self.alias, historical.get_model("auth", "User"))
        self.before = read_source(self.alias)

    def close(self):
        self.connection.close()
        del connections[self.alias]

    def run_transfer(self, **kwargs):
        return migrate_schemes(self.baseline, alias=self.alias, **kwargs)

    def test_schema_and_data_migration_repeat_and_exact_history_preservation(self):
        # No Sandbox/achievements tables exist: querying or modifying them fails.
        self.assertFalse(any(n.startswith("sandbox_") for n in self.connection.introspection.table_names()))
        result = self.run_transfer(execute=True)
        self.assertEqual(result["changed_fields"], {"stage_scheme": 14, "current_stage_id": 1})
        self.assertEqual(result["checks"]["progress_unchanged"], 14)
        after = read_source(self.alias)
        for name in ("stages", "history", "metrics", "roadmap"):
            self.assertEqual(self.before[name], after[name])
        self.assertEqual(len(after["history"]), 64)
        self.assertEqual(len(after["metrics"]), 37)
        self.assertEqual(self.run_transfer(execute=True)["status"], "already_applied")
        executor = MigrationExecutor(self.connection)
        executor.migrate(self.targets)
        self.assertEqual(after, read_source(self.alias))
        self.assertEqual(StageSchemeTransfer.objects.using(self.alias).count(), 14)

    def test_postgres_dryrun_really_rejects_writes(self):
        original = read_source
        def injected(alias):
            with self.connection.cursor() as cursor:
                cursor.execute("UPDATE traineediary_traineejourney SET stage_scheme='unified'")
            return original(alias)
        with patch("traineediary.services.unification.read_source", side_effect=injected):
            with self.assertRaises(DatabaseError) as raised:
                self.run_transfer()
        self.assertEqual(raised.exception.__cause__.sqlstate, "25006")
        self.assertEqual(read_source(self.alias), self.before)

    def test_all_changes_rollback_on_postcheck_failure(self):
        with patch("traineediary.services.unification.verify_runtime", side_effect=TransferError("injected_failure")):
            with self.assertRaises(TransferError):
                self.run_transfer(execute=True)
        self.assertEqual(read_source(self.alias), self.before)
        self.assertFalse(StageSchemeTransferBatch.objects.using(self.alias).exists())

    def test_stale_baseline_is_refused_on_postgres(self):
        metric = WeeklyMetric.objects.using(self.alias).first()
        WeeklyMetric.objects.using(self.alias).filter(pk=metric.pk).update(mentor_comment="New comment")
        with self.assertRaisesRegex(TransferError, "source_snapshot_differs"):
            self.run_transfer(execute=True)
        self.assertEqual(TraineeJourney.objects.using(self.alias).filter(stage_scheme="legacy").count(), 14)

    def test_guarded_rollback_and_its_repeat_restore_the_exact_source(self):
        self.run_transfer(execute=True)
        self.assertTrue(self.run_transfer(action="verify")["verified"])
        self.assertEqual(self.run_transfer(action="rollback", execute=True)["status"], "rolled_back")
        self.assertEqual(self.before, read_source(self.alias))
        self.assertEqual(self.run_transfer(action="rollback", execute=True)["status"], "already_rolled_back")

    def test_two_concurrent_runs_produce_one_verified_batch(self):
        barrier = Barrier(2)
        settings = deepcopy(self.connection.settings_dict)
        def run_once():
            wrapper = DatabaseWrapper(settings, alias=self.alias)
            connections[self.alias] = wrapper
            try:
                barrier.wait(timeout=5)
                return self.run_transfer(execute=True)["status"]
            finally:
                wrapper.close()
                del connections[self.alias]
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(run_once) for _ in range(2)]
            statuses = [future.result(timeout=15) for future in futures]
        self.assertEqual(sorted(statuses), ["already_applied", "applied"])
        self.assertEqual(StageSchemeTransferBatch.objects.using(self.alias).count(), 1)
        self.assertEqual(StageSchemeTransfer.objects.using(self.alias).count(), 14)

    def test_schema_reverse_is_blocked_to_preserve_provenance(self):
        self.run_transfer(execute=True)
        targets = [(app, "0007_classify_stage_catalog" if app == "traineediary" else name)
                   for app, name in self.targets]
        with self.assertRaises(IrreversibleError):
            MigrationExecutor(self.connection).migrate(targets)
        self.assertEqual(StageSchemeTransfer.objects.using(self.alias).count(), 14)

    @start_at_0007
    def test_plain_manage_migrate_applies_0008_without_transferring_existing_legacy_data(self):
        self.assertNotIn("traineediary_stageschemetransfer", self.connection.introspection.table_names())
        # Old single-database migrations use the default alias. Bind both names
        # to this disposable PG connection while preparing the deployed schema;
        # never let historical migrations fall through to another database.
        original_default = connections["default"]
        connections["default"] = self.connection
        try:
            executor = MigrationExecutor(self.connection)
            deployed = [node for node in executor.loader.graph.leaf_nodes() if node[0] != "traineediary"]
            deployed.append(("traineediary", "0007_classify_stage_catalog"))
            executor.migrate(deployed)
            executor = MigrationExecutor(self.connection)
            pending = executor.migration_plan(executor.loader.graph.leaf_nodes())
            self.assertEqual([(m.app_label, m.name, backwards) for m, backwards in pending],
                             [("traineediary", "0008_stageschemetransfer", False)])
            with patch("traineediary.services.unification.migrate_schemes", side_effect=AssertionError("Unexpected data transfer")):
                call_command("migrate", database=self.alias, interactive=False, verbosity=0, stdout=StringIO())
        finally:
            connections["default"] = original_default
        after = read_source(self.alias)
        for name in self.before:
            if name != "migrations":
                self.assertEqual(self.before[name], after[name])
        self.assertEqual(TraineeJourney.objects.using(self.alias).filter(stage_scheme="legacy").count(), 14)
        self.assertFalse(StageSchemeTransfer.objects.using(self.alias).exists())
        self.assertFalse(StageSchemeTransferBatch.objects.using(self.alias).exists())
        self.assertIn(("traineediary", "0008_stageschemetransfer"),
                      MigrationExecutor(self.connection).loader.applied_migrations)
