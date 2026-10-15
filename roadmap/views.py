import json
from functools import wraps
from django.db import OperationalError
from django.http import JsonResponse
from traineediary.models import TraineeJourney
from .services.confirmations import ConfirmationConflict, change_training_confirmation
from .services.projection import build_roadmap


def api_access(*, staff=False, method="GET"):
    def decorate(view):
        @wraps(view)
        def wrapped(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return JsonResponse({"error": "authentication_required"}, status=401)
            if staff and not request.user.is_staff:
                return JsonResponse({"error": "staff_required"}, status=403)
            if request.method != method:
                response = JsonResponse({"error": "method_not_allowed"}, status=405)
                response["Allow"] = method
                return response
            response = view(request, *args, **kwargs)
            response["Cache-Control"] = "private, no-store"
            return response
        return wrapped
    return decorate


def _journeys():
    return TraineeJourney.objects.select_related("user", "current_stage")


@api_access()
def me(request):
    return JsonResponse(build_roadmap(_journeys().filter(user=request.user).first(), viewer=request.user))


@api_access(staff=True)
def trainee(request, journey_id):
    journey = _journeys().filter(pk=journey_id).first()
    if journey is None:
        return JsonResponse({"error": "journey_not_found"}, status=404)
    return JsonResponse(build_roadmap(journey, viewer=request.user))


@api_access(staff=True, method="POST")
def training_action(request, journey_id, confirmed):
    try:
        if request.content_type != "application/json":
            raise ValueError("Ожидается application/json.")
        data = json.loads(request.body or b"{}")
        if not isinstance(data, dict) or set(data) - {"comment"}:
            raise ValueError("Разрешено только поле comment.")
        comment = data.get("comment", "")
        if not isinstance(comment, str) or len(comment) > 10000:
            raise ValueError("Комментарий должен быть строкой до 10000 символов.")
    except (ValueError, UnicodeDecodeError) as exc:
        return JsonResponse({"error": "invalid_request", "detail": str(exc)}, status=400)
    try:
        event, changed = change_training_confirmation(
            journey_id=journey_id, actor=request.user, confirmed=confirmed, comment=comment.strip(),
        )
    except TraineeJourney.DoesNotExist:
        return JsonResponse({"error": "journey_not_found"}, status=404)
    except ConfirmationConflict as exc:
        return JsonResponse({"error": "confirmation_conflict", "detail": str(exc)}, status=409)
    except OperationalError as exc:
        # SQLite cannot lock rows; return a retryable conflict rather than duplicating.
        cause = exc.__cause__
        if "locked" not in str(exc).lower() and getattr(cause, "sqlstate", None) not in {"40001", "40P01"}:
            raise
        return JsonResponse({"error": "concurrent_update", "detail": "Повторите запрос."}, status=409)
    return JsonResponse({"stage": "training", "confirmed": confirmed, "changed": changed, "event_id": event.pk if event else None})
