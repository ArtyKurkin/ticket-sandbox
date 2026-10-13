import json
from dataclasses import asdict

from django.core.management.base import BaseCommand

from sandbox.models import TaskAttempt
from sandbox.services.technical_evidence import (
    diagnose_technical_evidence,
    with_technical_evidence,
)


class Command(BaseCommand):
    help = "Read-only report of ambiguous credit results, including inactive historical tasks."

    def add_arguments(self, parser):
        parser.add_argument("--queue", default="l1")
        parser.add_argument("--user-id", type=int)
        parser.add_argument("--json", action="store_true")

    def handle(self, *args, **options):
        attempts = TaskAttempt.objects.filter(
            attempt_number=1, task__queue__slug=options["queue"]
        )
        if options["user_id"] is not None:
            attempts = attempts.filter(user_id=options["user_id"])
        diagnostics = [
            asdict(issue)
            for attempt in with_technical_evidence(
                attempts.order_by("user_id", "task_id")
            )
            for issue in diagnose_technical_evidence(attempt)
        ]
        if options["json"]:
            self.stdout.write(json.dumps(diagnostics, ensure_ascii=False))
        else:
            for issue in diagnostics:
                self.stdout.write(
                    "{code}: attempt={attempt_id} user={user_id} task={task_id}".format(
                        **issue
                    )
                )
            self.stdout.write(
                f"Diagnostic records: {len(diagnostics)}. No data changed."
            )
