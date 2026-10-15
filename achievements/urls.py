from django.urls import path
from . import views
from . import notification_views

app_name = "achievement_api"
urlpatterns = [
    path("me/notifications/", notification_views.notifications, name="notifications"),
    path("me/notifications/<int:event_id>/claim/", notification_views.claim_notification, name="notification_claim"),
    path("me/notifications/<int:event_id>/ack/", notification_views.ack_notification, name="notification_ack"),
    path("me/", views.me, name="me"),
    path("me/<uuid:public_id>/", views.detail, name="detail"),
    path("users/<int:user_id>/", views.user_collection, name="user"),
    path("users/<int:user_id>/<uuid:public_id>/", views.user_detail, name="user_detail"),
    path("users/<int:user_id>/<uuid:public_id>/grant/", views.manual_grant, name="grant"),
    path("users/<int:user_id>/<uuid:public_id>/revoke/", views.manual_revoke, name="revoke"),
]
