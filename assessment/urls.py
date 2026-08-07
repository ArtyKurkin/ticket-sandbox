from django.urls import path

from . import views


app_name = "assessment"


urlpatterns = [
    path(
        "",
        views.dashboard,
        name="dashboard",
    ),
    path(
        "assignments/<int:assignment_id>/start/",
        views.start_assignment,
        name="start_assignment",
    ),
    path(
        "attempts/<int:attempt_id>/",
        views.attempt_overview,
        name="attempt_overview",
    ),
    path(
        "attempts/<int:attempt_id>/question/",
        views.attempt_question,
        name="attempt_question",
    ),

    path(
        (
            "attempts/<int:attempt_id>/"
            "questions/<int:snapshot_id>/submit/"
        ),
        views.submit_question_answer,
        name="submit_question_answer",
    ),
]
