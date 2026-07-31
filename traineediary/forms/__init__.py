"""
Формы приложения «Дневник стажёра».

Формы временно переносятся из legacy.py
в тематические модули.
"""

from .legacy import (
    EditTraineeForm,
    NewTraineeForm,
    StartAdaptationForm,
    WeeklyMetricForm,
)
from .completion import CompleteProbationForm


__all__ = [
    "CompleteProbationForm",
    "EditTraineeForm",
    "NewTraineeForm",
    "StartAdaptationForm",
    "WeeklyMetricForm",
]