import hmac
import json

from django.conf import settings
from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from sandbox.models import TaskAttempt
from sandbox.services.terminal_broker import lease_credential


@csrf_exempt
@require_POST
def authorize(request):
    """Server-to-server lease check; never grants a browser a shell credential."""
    if not settings.TERMINAL_BROKER_ENABLED or len(request.body) > 2048:
        return HttpResponse(status=403)
    try:
        obj = json.loads(request.body)
        if (type(obj) is not dict or set(obj) != {"container_id", "attempt", "queue", "task", "generation"}
                or type(obj["attempt"]) is not int or obj["attempt"] < 1):
            raise ValueError
        attempt = TaskAttempt.objects.select_related("task", "task__queue", "user").get(pk=obj["attempt"])
        generation = str(attempt.environment_generation)
        expected = "Bearer " + lease_credential(attempt.pk, generation)
        allowed = (
            hmac.compare_digest(request.headers.get("Authorization", ""), expected)
            and obj == {"container_id": attempt.container_id, "attempt": attempt.pk,
                        "queue": attempt.task.queue.slug, "task": attempt.task.slug, "generation": generation}
            and attempt.environment_generation is not None
            and attempt.user.is_active
            and attempt.can_access_terminal and attempt.is_available
        )
        return HttpResponse(status=204 if allowed else 403)
    except (ValueError, TypeError, KeyError, TaskAttempt.DoesNotExist, OverflowError):
        return HttpResponse(status=403)
