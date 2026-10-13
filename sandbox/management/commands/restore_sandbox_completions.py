import json
from dataclasses import asdict

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from sandbox.models import SandboxProgramCompletion, TaskAttempt
from sandbox.services.completions import (
    PROGRAM_KEY,
    analyze_program_completion,
    restore_program_completion,
)


class Command(BaseCommand):
    help = "Analyze CURRENT L1 composition; write only with explicit --apply, user IDs and fingerprint."

    def add_arguments(self, parser):
        parser.add_argument("--user-id", type=int, action="append", dest="user_ids")
        parser.add_argument("--apply", action="store_true")
        parser.add_argument("--expected-fingerprint")
        parser.add_argument("--json", action="store_true")

    def handle(self, *args, **options):
        if options["apply"] and (
            not options["user_ids"] or not options["expected_fingerprint"]
        ):
            raise CommandError(
                "--apply требует явных --user-id и --expected-fingerprint из предварительного анализа."
            )
        if options["user_ids"]:
            user_ids = sorted(set(options["user_ids"]))
            found = set(
                get_user_model()
                .objects.filter(pk__in=user_ids)
                .values_list("pk", flat=True)
            )
            if found != set(user_ids):
                raise CommandError("Указаны неизвестные пользователи.")
        else:
            user_ids = list(
                TaskAttempt.objects.filter(
                    attempt_number=1,
                    task__queue__slug=PROGRAM_KEY,
                )
                .order_by("user_id")
                .values_list("user_id", flat=True)
                .distinct()
            )
        results = []
        if options["apply"]:
            try:
                with transaction.atomic():
                    for user_id in user_ids:
                        record, created = restore_program_completion(
                            user_id=user_id,
                            expected_fingerprint=options["expected_fingerprint"],
                        )
                        results.append(
                            {
                                "user_id": user_id,
                                "completion_id": record.pk,
                                "created": created,
                            }
                        )
            except ValidationError as error:
                raise CommandError("\n".join(error.messages)) from error
        else:
            for user_id in user_ids:
                existing = SandboxProgramCompletion.objects.filter(
                    user_id=user_id, program_key=PROGRAM_KEY
                ).first()
                candidate = analyze_program_completion(user_id)
                result = asdict(candidate)
                result["completed_at"] = (
                    candidate.completed_at.isoformat()
                    if candidate.completed_at
                    else None
                )
                result["completion_id"] = existing.pk if existing else None
                result["mode"] = "dry_run_current_composition"
                results.append(result)
        if options["json"]:
            self.stdout.write(json.dumps(results, ensure_ascii=False))
        else:
            self.stdout.write(
                "APPLY: selected users only"
                if options["apply"]
                else "DRY RUN: no data changed; current composition only"
            )
            for result in results:
                self.stdout.write(json.dumps(result, ensure_ascii=False))
