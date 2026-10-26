from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.views.decorators.http import require_GET, require_POST

from sandbox.models import TaskAttempt
from sandbox.services.observation_config import enabled_for
from sandbox.services.http_observations import request_observation


def summary(run):
    if run is None:
        return None
    return {"run_id": str(run.run_id), "status": run.status, "http": run.http,
            "reason": run.reason, "task_verdict": run.task_verdict, "academic_pass": False,
            "bind": "unverified", "process": "unverified", "network_isolation": "unverified"}


@login_required
@require_POST
def start_http_observation(request, attempt_id):
    attempt = get_object_or_404(TaskAttempt.objects.select_related("task__queue"), pk=attempt_id, user=request.user)
    if not enabled_for(attempt):
        raise Http404
    if (request.GET or request.content_type not in ("multipart/form-data", "application/x-www-form-urlencoded")
            or request.FILES or set(request.POST) - {"csrfmiddlewaretoken", "operation_id"}):
        return JsonResponse({"error": "observation_accepts_no_parameters"}, status=400)
    try:
        request_observation(attempt_id=attempt.pk, user_id=request.user.pk)
    except (ValidationError, ValueError, OSError):
        messages.error(request, "HTTP-наблюдение недоступно: проверь готовность тестового окружения.")
    else:
        messages.info(request, "HTTP-наблюдение запущено. Оно не засчитывает техническую часть; обнови страницу для результата.")
    return redirect("sandbox:task_detail", attempt_id=attempt_id)


@login_required
@require_GET
def http_observation_status(request, attempt_id):
    queryset = TaskAttempt.objects.select_related("task__queue")
    if not request.user.is_staff:
        queryset = queryset.filter(user=request.user)
    attempt = get_object_or_404(queryset, pk=attempt_id)
    if not enabled_for(attempt):
        raise Http404
    return JsonResponse({"attempt_id": attempt.pk, "observation": summary(attempt.http_observations.first()), "academic_pass": False})
