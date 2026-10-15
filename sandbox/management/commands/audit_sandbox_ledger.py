import json
from django.core.management.base import BaseCommand
from sandbox.services.ledger_evidence import program_evidence, attempt_evidence


class Command(BaseCommand):
    help = "SELECT-only ledger evidence; no raw answers and no awarding."

    def add_arguments(self, parser):
        group = parser.add_mutually_exclusive_group(required=True)
        group.add_argument("--user-id", type=int)
        group.add_argument("--attempt-id", type=int)

    def handle(self, *args, **options):
        evidence = (
            program_evidence(options["user_id"])
            if options["user_id"]
            else attempt_evidence(options["attempt_id"])
        )
        self.stdout.write(json.dumps(evidence, ensure_ascii=False, sort_keys=True))
