"""Формы приложения «Дневник стажёра»."""

from .completion import CompleteProbationForm
from .legacy import (
    EditTraineeForm,
    NewTraineeForm,
    StartAdaptationForm,
)
from .weekly_metrics import WeeklyMetricForm


__all__ = [
    "CompleteProbationForm",
    "EditTraineeForm",
    "NewTraineeForm",
    "StartAdaptationForm",
    "WeeklyMetricForm",
]