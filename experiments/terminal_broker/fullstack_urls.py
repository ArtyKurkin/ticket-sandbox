import hmac
import json
from pathlib import Path
from django.conf import settings
from django.db import connection
from django.http import HttpResponse, JsonResponse
from django.urls import path
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from config.urls import urlpatterns as production_urls


@csrf_exempt
@require_POST
def control(request):
    if not settings.TB2_FULLSTACK_TEST or not hmac.compare_digest(
            request.headers.get('Authorization', ''), 'Bearer ' + settings.TB2_CONTROL_TOKEN):
        return HttpResponse(status=403)
    from sandbox.models import TaskAttempt
    from sandbox.ledger_models import SandboxEnvironmentEvent
    from config.celery import app
    obj = json.loads(request.body)
    if obj['action'] == 'cleanup':
        from experiments.terminal_broker.fullstack_tasks import cleanup_environment
        for attempt in TaskAttempt.objects.all():
            cleanup_environment.delay(attempt.pk)
    elif obj['action'] == 'security':
        from experiments.terminal_broker.fullstack_tasks import inspect_boundaries
        inspect_boundaries.delay(1, obj.get('escaped_pid'))
    elif obj['action'] != 'state':
        return HttpResponse(status=400)
    attempts = []
    for attempt in TaskAttempt.objects.order_by('pk'):
        attempts.append({'id': attempt.pk, 'status': attempt.status,
            'environment_status': attempt.environment_status, 'container_id': attempt.container_id,
            'container_name': attempt.container_name, 'terminal_name': attempt.terminal_container_name,
            'generation': str(attempt.environment_generation), 'url': attempt.terminal_url,
            'restart_count': attempt.restart_count,
            'error': attempt.last_check_output if attempt.environment_status == 'error' else '',
            'events': list(SandboxEnvironmentEvent.objects.filter(attempt_id=attempt.pk)
                          .values('kind', 'phase', 'outcome', 'reason'))})
    security_file = Path('/lab') / ('security-' + settings.TB2_MODE + '.json')
    security = json.loads(security_file.read_text()) if security_file.is_file() else None
    return JsonResponse({'database': connection.vendor, 'eager': app.conf.task_always_eager, 'security': security,
                         'queue': app.conf.task_default_queue, 'attempts': attempts})


urlpatterns = [path('__tb2_test__/', control)] + production_urls
