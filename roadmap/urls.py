from django.urls import path
from . import views

app_name = "roadmap_api"
urlpatterns = [
    path("me/", views.me, name="me"),
    path("trainees/<int:journey_id>/", views.trainee, name="trainee"),
    path("trainees/<int:journey_id>/stages/training/confirm/", views.training_action, {"confirmed": True}, name="confirm"),
    path("trainees/<int:journey_id>/stages/training/revoke/", views.training_action, {"confirmed": False}, name="revoke"),
]
