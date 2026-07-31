from django.urls import path

from .views.completion import (
    complete_trainee,
)
from .views.dashboard import dashboard
from .views.kanban import (
    kanban_board_fragment,
    move_trainee_stage,
    trainees_kanban,
)
from .views.trainee_detail import (
    trainee_detail,
)
from .views.trainee_management import (
    create_trainee,
    edit_trainee,
    pre_adaptation_users,
    start_adaptation,
)
from .views.weekly_metrics import (
    save_weekly_metric,
    weekly_metrics,
)


app_name = "traineediary"


urlpatterns = [
    path(
        "",
        dashboard,
        name="dashboard",
    ),
    path(
        "metrics/",
        weekly_metrics,
        name="weekly_metrics",
    ),
    path(
        (
            "metrics/<int:journey_id>/"
            "weeks/<int:week_number>/save/"
        ),
        save_weekly_metric,
        name="save_weekly_metric",
    ),
    path(
        "trainees/",
        trainees_kanban,
        name="trainees_kanban",
    ),
    path(
        "trainees/board-fragment/",
        kanban_board_fragment,
        name="kanban_board_fragment",
    ),
    path(
        "trainees/new/",
        create_trainee,
        name="create_trainee",
    ),
    path(
        "trainees/pre-adaptation/",
        pre_adaptation_users,
        name="pre_adaptation_users",
    ),
    path(
        (
            "trainees/pre-adaptation/"
            "<int:user_id>/start/"
        ),
        start_adaptation,
        name="start_adaptation",
    ),
    path(
        "trainees/<int:journey_id>/",
        trainee_detail,
        name="trainee_detail",
    ),
    path(
        "trainees/<int:journey_id>/edit/",
        edit_trainee,
        name="edit_trainee",
    ),
    path(
        "trainees/<int:journey_id>/move/",
        move_trainee_stage,
        name="move_trainee_stage",
    ),
    path(
        (
            "trainees/<int:journey_id>/"
            "complete/"
        ),
        complete_trainee,
        name="complete_trainee",
    ),
]
