"""Server-owned availability, independent of individual completion.

Requirement policy v1 is deliberately fixed. Enabling future modules must introduce
an opt-in/pinned policy version for NEW journeys; never alter this requirement set.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class Module:
    code: str
    title: str
    source: str
    availability: str = "enabled"
    description: str = ""


MODULES = (
    Module("training", "Программа обучения", "manual"),
    Module("sandbox", "Ticket Sandbox", "sandbox"),
    Module("escalation", "Карта эскалаций", "escalation", "coming_soon",
           "Интерактивная карта маршрутизации обращений, небольшая теория и тренажёр."),
    Module("ticket_analysis", "Анализ тикетов", "ticket_analysis", "coming_soon",
           "Учебная тикет-система и тренажёр анализа обращений."),
    Module("with_review", "Тикеты с проверками", "traineediary"),
    Module("optional_review", "Проверки по желанию", "traineediary"),
    Module("no_review", "Тикеты без проверок", "traineediary"),
    Module("probation", "Выход с ИС", "traineediary"),
)
REQUIREMENTS_V1 = frozenset({"training", "sandbox", "with_review", "optional_review", "no_review", "probation"})
