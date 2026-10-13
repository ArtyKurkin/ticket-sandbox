"""The new migration creates a table, never grants completion to legacy users."""

from copy import deepcopy
from unittest import TestCase

from django.db import connections
from django.db.backends.sqlite3.base import DatabaseWrapper
from django.db.migrations.executor import MigrationExecutor


class CompletionMigrationTests(TestCase):
    def test_migration_does_not_backfill_even_proven_historical_completion(self):
        alias = "completion_migration_audit"
        config = deepcopy(connections["default"].settings_dict)
        config.update(ENGINE="django.db.backends.sqlite3", NAME=":memory:", OPTIONS={})
        connection = DatabaseWrapper(config, alias=alias)
        connections[alias] = connection
        try:
            before = [
                (
                    "sandbox",
                    "0030_aireview_mentor_decision_aireview_mentor_reviewed_at_and_more",
                )
            ]
            after = [("sandbox", "0031_sandbox_program_completion")]
            executor = MigrationExecutor(connection)
            executor.migrate(before)
            apps = executor.loader.project_state(before).apps
            user = (
                apps.get_model("auth", "User")
                .objects.using(alias)
                .create(username="historical-migration")
            )
            queue = (
                apps.get_model("sandbox", "Queue")
                .objects.using(alias)
                .get_or_create(
                    slug="l1",
                    defaults={"name": "Historical L1", "is_active": True},
                )[0]
            )
            task = (
                apps.get_model("sandbox", "Task")
                .objects.using(alias)
                .create(queue=queue, slug="migration-proof", title="Proof", order=99)
            )
            attempt = (
                apps.get_model("sandbox", "TaskAttempt")
                .objects.using(alias)
                .create(
                    user=user,
                    task=task,
                    status="passed",
                    technical_passed_at="2026-01-01T00:00:00Z",
                )
            )
            runs = apps.get_model("sandbox", "CheckRun")
            runs.objects.using(alias).create(
                attempt=attempt, result="passed", exit_code=0
            )
            attempts_before = list(
                apps.get_model("sandbox", "TaskAttempt").objects.using(alias).values()
            )
            runs_before = list(runs.objects.using(alias).values())
            executor = MigrationExecutor(connection)
            executor.migrate(after)
            apps = executor.loader.project_state(after).apps
            self.assertEqual(
                apps.get_model("sandbox", "SandboxProgramCompletion")
                .objects.using(alias)
                .count(),
                0,
            )
            self.assertEqual(
                attempts_before,
                list(
                    apps.get_model("sandbox", "TaskAttempt")
                    .objects.using(alias)
                    .values()
                ),
            )
            self.assertEqual(
                runs_before,
                list(
                    apps.get_model("sandbox", "CheckRun").objects.using(alias).values()
                ),
            )
        finally:
            connection.close()
            del connections[alias]
