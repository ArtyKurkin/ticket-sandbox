from django.urls import path

from . import views

app_name = "sandbox"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path(
        "attempts/<int:attempt_id>/", views.task_detail, name="task_detail"
    ),
    path(
        "attempts/<int:attempt_id>/start/", views.start_task, name="start_task"
    ),
    path(
        "attempts/<int:attempt_id>/restart/", views.restart_task, name="restart_task"
    ),
    path(
        "attempts/<int:attempt_id>/rerun/",
        views.rerun_task,
        name="rerun_task",
    ),
    path(
        "attempts/<int:attempt_id>/check/", views.check_task, name="check_task"
    ),
    path(
        "attempts/<int:attempt_id>/mentor-feedback/",
        views.save_mentor_feedback,
        name="save_mentor_feedback",
    ),
    path(
        "terminal-auth/<int:attempt_id>/<int:port>/",
        views.terminal_auth,
        name="terminal_auth",
    ),
    path(
        "terminal-auth/",
        views.terminal_auth,
        name="terminal_auth_from_original_uri",
    ),
]
