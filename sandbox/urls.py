from django.urls import path

from . import views
from . import observation_views
from . import terminal_broker_views

app_name = "sandbox"

urlpatterns = [
    path("terminal-broker-auth/", terminal_broker_views.authorize, name="terminal_broker_authorize"),
    path("attempts/<int:attempt_id>/http-observation/", observation_views.start_http_observation, name="http_observation"),
    path("attempts/<int:attempt_id>/http-observation-status/", observation_views.http_observation_status, name="http_observation_status"),
    path(
        "sandbox/ai-review-stats/",
        views.ai_review_stats,
        name="ai_review_stats",
    ),
    path(
        "sandbox/",
        views.dashboard,
        name="dashboard",
    ),
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
        "attempts/<int:attempt_id>/check-status/",
        views.check_task_status,
        name="check_task_status",
    ),
    path(
        "attempts/<int:attempt_id>/environment-status/",
        views.environment_status,
        name="environment_status",
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
        "terminal-auth/<int:attempt_id>/",
        views.terminal_auth,
        name="terminal_auth_docker_network",
    ),
    path(
        "terminal-auth/",
        views.terminal_auth,
        name="terminal_auth_from_original_uri",
    ),
]
