from django import template
from django.middleware.csrf import get_token
from django.urls import reverse

register = template.Library()


@register.inclusion_tag("achievements/_notifications.html", takes_context=True)
def achievement_notification_host(context):
    request = context.get("request")
    if not request or not request.user.is_authenticated or getattr(request, "_achievement_host_included", False):
        return {}
    request._achievement_host_included = True
    return {"notification_config": {
        "userId": request.user.pk,
        "feedUrl": reverse("achievement_api:notifications"),
        "claimUrl": reverse("achievement_api:notification_claim", args=[0]).replace("/0/", "/{event_id}/"),
        "ackUrl": reverse("achievement_api:notification_ack", args=[0]).replace("/0/", "/{event_id}/"),
        "trophyRoomUrl": reverse("achievements"),
        "csrfToken": get_token(request),
    }}
