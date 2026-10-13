"""Frozen catalog preflight. Never imports mutable runtime models or catalog values."""

from django.db import migrations, models

LEGACY_CATALOG = {
    "first-day": {
        "name": "Первый день",
        "order": 1,
        "min_days": 1,
        "max_days": 1,
        "progress_weight_percent": 3,
        "group": "teachbase",
        "applies_to_new_hire": True,
        "applies_to_internal_transfer": False,
    },
    "vds": {
        "name": "VDS",
        "order": 2,
        "min_days": 5,
        "max_days": 7,
        "progress_weight_percent": 15,
        "group": "teachbase",
        "applies_to_new_hire": True,
        "applies_to_internal_transfer": False,
    },
    "managed-services": {
        "name": "Управляемые сервисы",
        "order": 3,
        "min_days": 2,
        "max_days": 3,
        "progress_weight_percent": 8,
        "group": "teachbase",
        "applies_to_new_hire": True,
        "applies_to_internal_transfer": False,
    },
    "client-service": {
        "name": "Клиентский сервис",
        "order": 4,
        "min_days": 1,
        "max_days": 2,
        "progress_weight_percent": 5,
        "group": "teachbase",
        "applies_to_new_hire": True,
        "applies_to_internal_transfer": False,
    },
    "before-tickets": {
        "name": "Перед выходом в тикеты",
        "order": 6,
        "min_days": 1,
        "max_days": 1,
        "progress_weight_percent": 4,
        "group": "teachbase",
        "applies_to_new_hire": True,
        "applies_to_internal_transfer": False,
    },
    "sandbox-candidate": {
        "name": "Задания в ticket-sandbox",
        "order": 5,
        "min_days": 1,
        "max_days": 2,
        "progress_weight_percent": 5,
        "group": "sandbox_candidate",
        "applies_to_new_hire": True,
        "applies_to_internal_transfer": False,
    },
    "with-review": {
        "name": "В тикетах с проверками",
        "order": 7,
        "min_days": 15,
        "max_days": 20,
        "progress_weight_percent": 35,
        "group": "with_review",
        "applies_to_new_hire": True,
        "applies_to_internal_transfer": True,
    },
    "optional-review": {
        "name": "Кнопка по желанию",
        "order": 8,
        "min_days": 5,
        "max_days": 10,
        "progress_weight_percent": 10,
        "group": "optional_review",
        "applies_to_new_hire": True,
        "applies_to_internal_transfer": True,
    },
    "no-review": {
        "name": "Без проверок",
        "order": 9,
        "min_days": 10,
        "max_days": 10,
        "progress_weight_percent": 15,
        "group": "no_review",
        "applies_to_new_hire": True,
        "applies_to_internal_transfer": True,
    },
    "done": {
        "name": "Выход с ИС",
        "order": 10,
        "min_days": 0,
        "max_days": 0,
        "progress_weight_percent": 0,
        "group": "done",
        "applies_to_new_hire": True,
        "applies_to_internal_transfer": True,
    },
}

TRAINING_PROGRAM = {
    "name": "Программа обучения",
    "order": 1,
    "min_days": 10,
    "max_days": 14,
    "progress_weight_percent": 35,
    "group": "teachbase",
    "applies_to_new_hire": True,
    "applies_to_internal_transfer": False,
}

LEGACY_SLUGS = {
    "first-day",
    "vds",
    "managed-services",
    "client-service",
    "before-tickets",
}


def catalog_issues(Stage, Journey, History, alias, *, classified=False):
    issues = []
    stages = list(Stage.objects.using(alias).all())
    by_slug = {stage.slug: stage for stage in stages}
    for stage in stages:
        expected = (
            TRAINING_PROGRAM
            if stage.slug == "training-program"
            else LEGACY_CATALOG.get(stage.slug)
        )
        if expected is None:
            issues.append(
                f"pk={stage.pk} slug={stage.slug}: неизвестный этап; необходимо ручное согласование"
            )
            continue
        # New display labels are accepted without rewriting stored historical names.
        accepted_names = {
            "sandbox-candidate": {
                "Задания в ticket-sandbox",
                "Задания в Ticket Sandbox",
            },
            "optional-review": {"Кнопка по желанию", "Проверки по желанию"},
        }
        for field, value in expected.items():
            actual = getattr(stage, field)
            if field == "name" and actual in accepted_names.get(stage.slug, set()):
                continue
            if actual != value:
                issues.append(
                    f"pk={stage.pk} slug={stage.slug}: {field}={actual!r}, ожидается {value!r}"
                )
        if classified:
            scope = (
                "unified"
                if stage.slug == "training-program"
                else ("legacy" if stage.slug in LEGACY_SLUGS else "shared")
            )
            if stage.catalog_scope != scope:
                issues.append(
                    f"pk={stage.pk} slug={stage.slug}: catalog_scope={stage.catalog_scope!r}, ожидается {scope!r}"
                )
    if Journey.objects.using(alias).exists() or History.objects.using(alias).exists():
        for slug in sorted(set(LEGACY_CATALOG) - set(by_slug)):
            # Only legacy journeys require the historical catalog on a classified DB.
            if (
                not classified
                or Journey.objects.using(alias).filter(stage_scheme="legacy").exists()
            ):
                issues.append(
                    f"Отсутствует исторический этап {slug}; необходимо ручное согласование"
                )
    if not classified and "training-program" in by_slug:
        program = by_slug["training-program"]
        if (
            Journey.objects.using(alias).filter(current_stage_id=program.pk).exists()
            or History.objects.using(alias).filter(stage_id=program.pk).exists()
        ):
            issues.append(
                "training-program уже используется: требуется ручное сопоставление схем"
            )
    return issues


def forwards(apps, schema_editor):
    alias = schema_editor.connection.alias
    Stage = apps.get_model("traineediary", "TraineeStage")
    Journey = apps.get_model("traineediary", "TraineeJourney")
    History = apps.get_model("traineediary", "StageHistory")
    issues = catalog_issues(Stage, Journey, History, alias)
    if issues:
        raise RuntimeError(
            "Миграция этапов остановлена до изменения данных:\n" + "\n".join(issues)
        )
    Journey.objects.using(alias).all().update(stage_scheme="legacy")
    Stage.objects.using(alias).filter(slug__in=LEGACY_SLUGS).update(
        catalog_scope="legacy"
    )
    Stage.objects.using(alias).exclude(slug__in=LEGACY_SLUGS).update(
        catalog_scope="shared"
    )
    program, _ = Stage.objects.using(alias).get_or_create(
        slug="training-program",
        defaults={**TRAINING_PROGRAM, "color": "#3B82F6", "catalog_scope": "unified"},
    )
    Stage.objects.using(alias).filter(pk=program.pk).update(catalog_scope="unified")


class Migration(migrations.Migration):
    dependencies = [("traineediary", "0006_stage_schemes")]
    operations = [
        # Intentionally irreversible: rolling back would remove schema identity from new journeys.
        migrations.RunPython(forwards),
        migrations.AlterField(
            model_name="traineejourney",
            name="stage_scheme",
            field=models.CharField(
                choices=[
                    ("legacy", "Прежняя программа"),
                    ("unified", "Единая программа"),
                ],
                default="unified",
                max_length=16,
                verbose_name="Схема адаптации",
            ),
        ),
    ]
