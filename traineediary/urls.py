from django.urls import path

from . import views

app_name = "traineediary"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("trainees/", views.trainees_kanban, name="trainees_kanban"),
    path("trainees/board-fragment/", views.kanban_board_fragment, name="kanban_board_fragment"),
    path("trainees/new/", views.create_trainee, name="create_trainee"),
    path("trainees/<int:journey_id>/move/", views.move_trainee_stage, name="move_trainee_stage"),
]
