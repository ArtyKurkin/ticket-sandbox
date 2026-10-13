from django.core.management.base import BaseCommand, CommandError

from traineediary.services.stage_catalog import check_stage_catalog


class Command(BaseCommand):
    help = "Проверяет справочник перед миграцией или seed; не изменяет данные."

    def add_arguments(self, parser):
        parser.add_argument("--database", default="default")
        parser.add_argument("--before-migration", action="store_true")

    def handle(self, *args, **options):
        issues = check_stage_catalog(
            database=options["database"],
            classified=not options["before_migration"],
        )
        if issues:
            raise CommandError("\n".join(issues))
        self.stdout.write(self.style.SUCCESS("Справочник этапов согласован."))
