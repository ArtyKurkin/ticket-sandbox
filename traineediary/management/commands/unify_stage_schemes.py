import json

from django.core.management.base import BaseCommand, CommandError
from django.db import DatabaseError

from traineediary.services.unification import TransferError, load_baseline, migrate_schemes


class Command(BaseCommand):
    help = "Baseline-locked legacy → unified migration; defaults to a read-only dry-run."
    requires_system_checks = []

    def add_arguments(self, parser):
        parser.add_argument("--baseline", required=True)
        parser.add_argument("--database", default="default")
        parser.add_argument("--execute", action="store_true")
        actions = parser.add_mutually_exclusive_group()
        actions.add_argument("--verify", action="store_true")
        actions.add_argument("--rollback", action="store_true")

    def handle(self, *args, **options):
        try:
            baseline = load_baseline(options["baseline"])
            result = migrate_schemes(
                baseline, alias=options["database"], execute=options["execute"],
                action="verify" if options["verify"] else "rollback" if options["rollback"] else "apply",
            )
        except TransferError as error:
            raise CommandError(str(error)) from None
        except DatabaseError:
            raise CommandError("database_operation_failed_transaction_rolled_back") from None
        self.stdout.write(json.dumps(result, ensure_ascii=False, indent=2))
