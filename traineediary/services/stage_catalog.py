"""Read-only preflight shared with the frozen migration it validates."""

from importlib import import_module

from django.db import DEFAULT_DB_ALIAS

from ..models import StageHistory, TraineeJourney, TraineeStage

# This validator checks migration 0007's frozen contract, not an evolving seed spec.
contract = import_module("traineediary.migrations.0007_classify_stage_catalog")


def check_stage_catalog(*, database=DEFAULT_DB_ALIAS, classified=True):
    Stage, Journey, History = TraineeStage, TraineeJourney, StageHistory
    if not classified:
        from django.db import connections
        from django.db.migrations.loader import MigrationLoader

        apps = (
            MigrationLoader(connections[database])
            .project_state(
                [
                    ("traineediary", "0005_traineejourney_completed_at_and_more"),
                ]
            )
            .apps
        )
        Stage = apps.get_model("traineediary", "TraineeStage")
        Journey = apps.get_model("traineediary", "TraineeJourney")
        History = apps.get_model("traineediary", "StageHistory")
    return contract.catalog_issues(
        Stage,
        Journey,
        History,
        database,
        classified=classified,
    )
