from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase
from sandbox.services.ledger_evidence import attempt_evidence


class LedgerMigrationTests(TransactionTestCase):

    def test_existing_attempts_unchanged_no_coverage_backfill(self):
        previous = ("sandbox", "0031_sandbox_program_completion")
        current = MigrationExecutor(connection).loader.graph.leaf_nodes()
        try:
            executor = MigrationExecutor(connection)
            executor.migrate([previous])
            apps = executor.loader.project_state([previous]).apps
            User = apps.get_model("auth", "User")
            Queue = apps.get_model("sandbox", "Queue")
            Task = apps.get_model("sandbox", "Task")
            Attempt = apps.get_model("sandbox", "TaskAttempt")
            user = User.objects.create(username="ledger-before")
            queue = Queue.objects.get_or_create(
                slug="legacy-test", defaults={"name": "Legacy"}
            )[0]
            task = Task.objects.create(
                queue=queue, slug="legacy-task", title="Legacy", order=1
            )
            attempt = Attempt.objects.create(
                user=user, task=task, attempts_count=3, restart_count=2
            )
            before = Attempt.objects.filter(pk=attempt.pk).values().get()
            MigrationExecutor(connection).migrate(current)
            from sandbox.models import TaskAttempt
            from sandbox.ledger_models import (
                SandboxAttemptCoverage,
                TechnicalCheckExecution,
                SandboxProgramManifest,
            )

            self.assertEqual(
                TaskAttempt.objects.filter(pk=attempt.pk).values(*before).get(), before
            )
            self.assertEqual(TaskAttempt.objects.get(pk=attempt.pk).http_observation_runtime, {})
            self.assertFalse(
                SandboxAttemptCoverage.objects.filter(attempt_id=attempt.pk).exists()
            )
            self.assertFalse(TechnicalCheckExecution.objects.exists())
            self.assertFalse(SandboxProgramManifest.objects.exists())
            self.assertEqual(
                attempt_evidence(attempt.pk)["coverage"]["status"], "unknown"
            )
        finally:
            executor = MigrationExecutor(connection)
            executor.migrate(executor.loader.graph.leaf_nodes())
