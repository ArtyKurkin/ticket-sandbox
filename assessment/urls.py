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
    path(
        "mentor/questions/",
        views.mentor_question_list,
        name="mentor_question_list",
    ),
    path(
        "mentor/questions/new/",
        views.mentor_question_create,
        name="mentor_question_create",
    ),

    path(
        "mentor/questions/<int:question_id>/edit/",
        views.mentor_question_edit,
        name="mentor_question_edit",
    ),
]
