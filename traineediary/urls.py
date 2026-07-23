from django.urls import path

from . import views

app_name = "traineediary"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path(
        "metrics/",
        views.weekly_metrics,
        name="weekly_metrics",
    ),
    path(
        "metrics/<int:journey_id>/weeks/<int:week_number>/save/",
        views.save_weekly_metric,
        name="save_weekly_metric",
    ),
    path("trainees/", views.trainees_kanban, name="trainees_kanban"),
    path("trainees/board-fragment/", views.kanban_board_fragment, name="kanban_board_fragment"),
    path("trainees/new/", views.create_trainee, name="create_trainee"),
    path(
        "trainees/pre-adaptation/",
        views.pre_adaptation_users,
        name="pre_adaptation_users",
    ),
    path(
        (
            "trainees/pre-adaptation/"
            "<int:user_id>/start/"
        ),
        views.start_adaptation,
        name="start_adaptation",
    ),
    path(
        "trainees/<int:journey_id>/",
        views.trainee_detail,
        name="trainee_detail",
    ),
    path(
        "trainees/<int:journey_id>/edit/",
        views.edit_trainee,
        name="edit_trainee",
    ),
    path("trainees/<int:journey_id>/move/", views.move_trainee_stage, name="move_trainee_stage"),
]
