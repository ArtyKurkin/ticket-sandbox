"""Versioned, server-owned rule schemas. Catalog data never executes code."""
from django.core.exceptions import ValidationError
from django.db import transaction

ART_KEYS = {"generic", "training", "sandbox", "quality", "speed", "probation", "milestone", "independent"}
RARITIES = ("bronze", "silver", "gold", "platinum")


def family(code, title, category, tiers, *, kind="tiered", applicability="both", secret=False):
    return dict(code=code, title=title, description=title, category=category, secret=secret,
                kind=kind, applicability=applicability, evaluator_key=code, rule_version=1,
                art_key=category if category in ART_KEYS else "generic", tiers=tiers)


CATALOG = [
    family("training_program", "Программа обучения", "training", [
        ("bronze", "Подтверждённое завершение программы", {"automatic": True}),
        ("silver", "≤11 учебных рабочих дней и >90%", {"automatic": False, "max_study_days": 11, "score_gt": 90}),
        ("gold", "≤6 учебных рабочих дней и >95%", {"automatic": False, "max_study_days": 6, "score_gt": 95}),
        ("platinum", "≤6 учебных рабочих дней и ровно 100%", {"automatic": False, "max_study_days": 6, "score_eq": 100}),
    ], applicability="new_hire"),
    family("sandbox_program", "Ticket Sandbox", "sandbox", [
        ("bronze", "Обязательная программа технически завершена", {"automatic": True}),
        ("silver", "Техническое завершение, ≤2 успешных перезапусков", {"automatic": False, "max_resets": 2}),
        ("gold", "Все ответы приняты, ≤2 перезапусков и ≤2 возвратов", {"automatic": False, "max_resets": 2, "max_revisions": 2, "answers_approved": True}),
        ("platinum", "Первая проверка и первая отправка успешны, без перезапусков", {"automatic": False, "max_resets": 0, "first_check": True, "first_submission": True}),
    ], applicability="new_hire"),
    family("review_quality", "Качество тикетов", "quality", [
        ("bronze", "≥80% за достоверную неделю WITH_REVIEW", {"automatic": True, "minimum": "80", "strict": False}),
        ("silver", "≥90% за достоверную неделю WITH_REVIEW", {"automatic": True, "minimum": "90", "strict": False}),
        ("gold", ">95% за достоверную неделю WITH_REVIEW", {"automatic": True, "minimum": "95", "strict": True}),
    ]),
    family("independent_speed", "Скорость обработки тикетов", "speed", [
        ("bronze", "≥5 т/ч на NO_REVIEW", {"automatic": True, "minimum": "5", "strict": False}),
        ("silver", "≥7 т/ч на NO_REVIEW", {"automatic": True, "minimum": "7", "strict": False}),
        ("gold", "≥9 т/ч на NO_REVIEW", {"automatic": True, "minimum": "9", "strict": False}),
        ("platinum", ">10 т/ч на NO_REVIEW", {"automatic": True, "minimum": "10", "strict": True}),
    ]),
    family("probation_new_hire", "Завершение испытательного срока", "probation", [
        ("bronze", "Успешный выход позднее 60-го дня", {"automatic": True, "min_day": 61}),
        ("silver", "Успешный выход на 46–60-й день", {"automatic": True, "min_day": 46, "max_day": 60}),
        ("gold", "Успешный выход на 31–45-й день", {"automatic": True, "min_day": 31, "max_day": 45}),
        ("platinum", "Успешный выход не позднее 30-го дня", {"automatic": True, "min_day": 1, "max_day": 30}),
    ], applicability="new_hire"),
    family("sandbox_first_success", "Первый запуск", "sandbox", [("bronze", "Первое технически успешное зачётное задание", {"automatic": True, "task_count": 1})], kind="fixed", applicability="new_hire"),
    family("sandbox_five_successes", "Пять из пяти", "sandbox", [("silver", "Пять различных технически успешных зачётных заданий", {"automatic": True, "task_count": 5})], kind="fixed", applicability="new_hire"),
    family("sandbox_first_five_clean_answers", "Без замечаний", "sandbox", [("gold", "Первые пять разных ответов приняты с первой отправки", {"automatic": False})], kind="fixed", applicability="new_hire"),
    family("review_quality_streak", "Стабильность — признак мастерства", "quality", [("gold", "Три полные последовательные недели WITH_REVIEW с ≥90%", {"automatic": False})], kind="fixed"),
    family("independent_engineer", "Самостоятельный инженер", "independent", [("silver", "Подтверждённый переход OPTIONAL_REVIEW → NO_REVIEW", {"automatic": True})], kind="fixed"),
    family("clean_week", "Чистая неделя", "quality", [("platinum", "100% за полную рабочую неделю WITH_REVIEW с подтверждённым покрытием", {"automatic": False})], kind="fixed", secret=True),
]
SCHEMAS = {row["evaluator_key"]: row for row in CATALOG}


def validate_definition(definition):
    schema = SCHEMAS.get(definition.evaluator_key)
    if schema is None or definition.rule_version != schema["rule_version"]:
        raise ValidationError("Неизвестный evaluator или неподдерживаемая версия правила.")
    if definition.kind != schema["kind"] or definition.applicability != schema["applicability"]:
        raise ValidationError("Тип и применимость не соответствуют схеме evaluator.")
    if definition.art_key not in ART_KEYS:
        raise ValidationError("Недопустимый ключ оформления.")


def validate_tier(tier):
    validate_definition(tier.definition)
    schema = SCHEMAS[tier.definition.evaluator_key]
    match = next((t for t in schema["tiers"] if t[0] == tier.code), None)
    if (match is None or tier.parameters != match[2] or tier.rarity != match[0]
            or tier.rank != RARITIES.index(match[0]) + 1 or tier.rule_version != tier.definition.rule_version):
        raise ValidationError("Уровень не соответствует проверенной серверной схеме.")


@transaction.atomic
def seed_catalog(apps=None):
    """Only definitions/tiers: no user backfill. Also usable after a test flush."""
    if apps is None:
        from achievements.models import AchievementDefinition, AchievementTier
    else:
        AchievementDefinition = apps.get_model("achievements", "AchievementDefinition")
        AchievementTier = apps.get_model("achievements", "AchievementTier")
    for row in CATALOG:
        metadata = {k: v for k, v in row.items() if k != "tiers"}
        definition, _ = AchievementDefinition.objects.get_or_create(code=row["code"], defaults=metadata)
        for code, criterion, parameters in row["tiers"]:
            AchievementTier.objects.get_or_create(definition=definition, code=code, defaults={
                "rank": RARITIES.index(code) + 1, "rarity": code, "criterion": criterion,
                "parameters": parameters, "rule_version": row["rule_version"],
            })
