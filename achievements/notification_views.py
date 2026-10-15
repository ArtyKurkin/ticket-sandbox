import json

from django.http import JsonResponse

from achievements.models import AchievementNotification
from achievements.services.notifications import acknowledge, claim, feed, NotificationConflict, token
from achievements.views import api


@api()
def notifications(request):
    return JsonResponse(feed(request.user.pk))


def change(request, event_id, handler):
    try:
        if request.content_type != "application/json":
            raise ValueError("invalid_body")
        body = json.loads(request.body)
        if not isinstance(body, dict) or set(body) != {"claim_token"}:
            raise ValueError("invalid_body")
        result = handler(request.user.pk, event_id, token(body["claim_token"]))
    except (ValueError, UnicodeDecodeError):
        return JsonResponse({"error": "invalid_request"}, status=400)
    except AchievementNotification.DoesNotExist:
        return JsonResponse({"error": "notification_not_found"}, status=404)
    except NotificationConflict as error:
        return JsonResponse({"error": str(error)}, status=409)
    return JsonResponse(result)


@api(method="POST")
def claim_notification(request, event_id):
    return change(request, event_id, claim)


@api(method="POST")
def ack_notification(request, event_id):
    return change(request, event_id, acknowledge)
