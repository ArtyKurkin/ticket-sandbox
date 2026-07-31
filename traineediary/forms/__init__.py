"""Формы приложения «Дневник стажёра»."""

from .completion import CompleteProbationForm
from .trainee_management import (
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
