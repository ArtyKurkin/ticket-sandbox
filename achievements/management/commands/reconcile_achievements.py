import json

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError

from achievements.models import AchievementDefinition
from achievements.services.events import PROVIDERS
from achievements.services.reconciliation import reconcile


class Command(BaseCommand):
    help = "SELECT-only dry-run по явно выбранным пользователям; запись только с --apply."

    def add_arguments(self, parser):
        parser.add_argument("--user-ids", nargs="+", type=int, required=True)
        group = parser.add_mutually_exclusive_group()
        group.add_argument("--families", nargs="+")
        group.add_argument("--source", choices=PROVIDERS)
        parser.add_argument("--rule-version", type=int, default=1)
        parser.add_argument("--apply", action="store_true")

    def handle(self, *args, **options):
        user_ids = sorted(set(options["user_ids"]))
        if set(get_user_model().objects.filter(pk__in=user_ids).values_list("pk", flat=True)) != set(user_ids):
            raise CommandError("Неизвестный пользователь.")
        definitions = AchievementDefinition.objects.all()
        codes = options["families"]
        if options["source"]:
            definitions = definitions.filter(evaluator_key__in=PROVIDERS[options["source"]])
        elif codes:
            definitions = definitions.filter(code__in=codes)
            if set(definitions.values_list("code", flat=True)) != set(codes):
                raise CommandError("Неизвестное семейство.")
        definitions = list(definitions)
        if not definitions or any(d.rule_version != options["rule_version"] for d in definitions):
            raise CommandError("Каталог отсутствует или версия правила изменилась.")
        try:
            evidence_cache = {}
            reports = [reconcile(user_id=user_id, definition=d, apply=options["apply"], expected_rule_version=options["rule_version"], evidence_cache=evidence_cache)
                       for user_id in user_ids for d in definitions]
        except ValidationError as error:
            raise CommandError(str(error)) from error
        self.stdout.write(json.dumps(reports, ensure_ascii=False, indent=2))
