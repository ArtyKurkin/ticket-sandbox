from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from traineediary.models import StageScope, TraineeStage
from traineediary.services.stage_catalog import check_stage_catalog, contract


# Existing parameters are validated and never overwritten, including names/colors/activity.
STAGES = {
    "training-program": {
        **contract.TRAINING_PROGRAM,
        "color": "#3B82F6",
        "catalog_scope": StageScope.UNIFIED,
    },
    **{
        slug: {
            **contract.LEGACY_CATALOG[slug],
            "catalog_scope": StageScope.SHARED,
            "color": color,
        }
        for slug, color in (
            ("sandbox-candidate", "#14B8A6"),
            ("with-review", "#FACC15"),
            ("optional-review", "#84CC16"),
            ("no-review", "#22C55E"),
            ("done", "#15803D"),
        )
    },
}
STAGES["sandbox-candidate"]["name"] = "Задания в Ticket Sandbox"
STAGES["optional-review"]["name"] = "Проверки по желанию"


class Command(BaseCommand):
    help = "Создаёт недостающие этапы единой программы без перезаписи исторических параметров."

    @transaction.atomic
    def handle(self, *args, **options):
        issues = check_stage_catalog()
        if issues:
            raise CommandError(
                "Seed остановлен до изменения данных:\n" + "\n".join(issues)
            )
        created_count = 0
        for slug, defaults in STAGES.items():
            _, created = TraineeStage.objects.get_or_create(
                slug=slug, defaults=defaults
            )
            created_count += int(created)
        self.stdout.write(
            self.style.SUCCESS(
                f"Готово: создано {created_count}, существующие этапы сохранены, "
                f"всего этапов {TraineeStage.objects.count()}.",
            )
        )
