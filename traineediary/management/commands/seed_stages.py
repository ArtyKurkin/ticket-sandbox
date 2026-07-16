from django.core.management.base import BaseCommand

from traineediary.models import StageGroup, TraineeStage


# (name, slug, order, min_days, max_days, weight, color, group, new_hire, internal)
STAGES = [
    ("Первый день", "first-day", 1, 1, 1, 3, "#9CA3AF", StageGroup.TEACHBASE, True, False),
    ("VDS", "vds", 2, 5, 7, 15, "#3B82F6", StageGroup.TEACHBASE, True, False),
    ("Управляемые сервисы", "managed-services", 3, 2, 3, 8, "#8B5CF6", StageGroup.TEACHBASE, True, False),
    ("Клиентский сервис", "client-service", 4, 1, 2, 5, "#06B6D4", StageGroup.TEACHBASE, True, False),
    ("Перед выходом в тикеты", "before-tickets", 5, 1, 1, 4, "#F59E0B", StageGroup.TEACHBASE, True, False),
    ("Задания в ticket-sandbox", "sandbox-candidate", 6, 1, 2, 5, "#14B8A6", StageGroup.SANDBOX_CANDIDATE, True, False),
    ("В тикетах с проверками", "with-review", 7, 15, 20, 35, "#FACC15", StageGroup.WITH_REVIEW, True, True),
    ("Кнопка по желанию", "optional-review", 8, 5, 10, 10, "#84CC16", StageGroup.OPTIONAL_REVIEW, True, True),
    ("Без проверок", "no-review", 9, 10, 10, 15, "#22C55E", StageGroup.NO_REVIEW, True, True),
    ("Выход с ИС", "done", 10, 0, 0, 0, "#15803D", StageGroup.DONE, True, True),
]


class Command(BaseCommand):
    help = "Наполняет справочник этапов обучения (TraineeStage) стартовым набором данных."

    def handle(self, *args, **options):
        created_count = 0
        updated_count = 0

        for name, slug, order, min_days, max_days, weight, color, group, new_hire, internal in STAGES:
            _, created = TraineeStage.objects.update_or_create(
                slug=slug,
                defaults=dict(
                    name=name,
                    order=order,
                    min_days=min_days,
                    max_days=max_days,
                    progress_weight_percent=weight,
                    color=color,
                    group=group,
                    applies_to_new_hire=new_hire,
                    applies_to_internal_transfer=internal,
                ),
            )
            if created:
                created_count += 1
            else:
                updated_count += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Готово: создано {created_count}, обновлено {updated_count}, "
                f"всего этапов {TraineeStage.objects.count()}.",
            ),
        )
