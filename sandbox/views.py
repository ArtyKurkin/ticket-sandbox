import logging

from django.contrib.auth.decorators import login_required
from django.shortcuts import render, get_object_or_404, redirect
from django.utils import timezone
from django.urls import reverse
from django.contrib import messages
from django.views.decorators.http import require_GET, require_POST
from django.db import transaction
from django.http import HttpResponse, JsonResponse
from .models import TaskAttempt
from .services.trainee_dashboard import build_trainee_dashboard_context
from .services.mentor_dashboard import build_mentor_dashboard_context
from .services.attempts import get_next_attempt_number
from .services.notifications import (
    notify_manual_review_required,
    notify_user_completed_all_tasks,
)
from .services.terminal_gateway import (
    log_terminal_auth_denied,
    parse_terminal_uri,
)
from .services.checks import start_attempt_check_in_background
from .services.environments import (
    start_environment_in_background,
    start_environment_restart_in_background,
    try_mark_environment_restarting,
    try_mark_environment_starting,
)


terminal_logger = logging.getLogger("sandbox.terminal")


def block_historical_attempt_action(request, attempt):
    if attempt.is_current:
        return None

    messages.error(
        request,
        "Это историческая попытка, действия недоступны."
    )

    return redirect(
        "sandbox:task_detail",
        attempt_id=attempt.id,
    )


@login_required
def dashboard(request):
    if request.user.is_staff:
        return render(
            request,
            "sandbox/mentor_dashboard.html",
            build_mentor_dashboard_context(request),
        )

    return render(
        request,
        "sandbox/trainee_dashboard.html",
        build_trainee_dashboard_context(request.user),
    )


@login_required
def task_detail(request, attempt_id):
    attempts_queryset = (
        TaskAttempt.objects
        .select_related("task", "task__queue", "user")
        .prefetch_related("check_runs")
    )

    if request.user.is_staff:
        attempt = get_object_or_404(
            attempts_queryset,
            id=attempt_id,
        )
        is_mentor_view = True
    else:
        attempt = get_object_or_404(
            attempts_queryset,
            id=attempt_id,
            user=request.user,
        )
        is_mentor_view = False

        if not is_mentor_view and attempt.has_unread_mentor_feedback:
            attempt.mentor_feedback_seen_at = timezone.now()
            attempt.save(update_fields=["mentor_feedback_seen_at"])

        if not attempt.is_available:
            return redirect("sandbox:dashboard")

    manual_review_required = attempt.task.requires_manual_review
    technical_part_passed = attempt.is_technically_completed

    answer_flow_enabled = manual_review_required

    answer_is_locked = (
        answer_flow_enabled
        and attempt.status in ["on_review", "passed"]
    )

    answer_can_be_edited = (
        answer_flow_enabled
        and attempt.is_current
        and technical_part_passed
        and not answer_is_locked
    )

    answer_is_hidden_before_technical_pass = (
        answer_flow_enabled
        and attempt.is_current
        and not technical_part_passed
        and not answer_is_locked
    )

    answer_is_collapsed = (
        answer_flow_enabled
        and attempt.is_extra_attempt
        and attempt.status == "passed"
    )

    answer_section_is_hidden = (
        not answer_flow_enabled
        and attempt.is_current
    )

    return render(
        request,
        "sandbox/task_detail.html",
        {
            "attempt": attempt,
            "check_runs": attempt.check_runs.all(),
            "is_mentor_view": is_mentor_view,
            "mentor_decision_options": TaskAttempt.MentorDecision.choices,
            "manual_review_required": manual_review_required,
            "technical_part_passed": technical_part_passed,
            "answer_flow_enabled": answer_flow_enabled,
            "answer_can_be_edited": answer_can_be_edited,
            "answer_is_locked": answer_is_locked,
            "answer_is_collapsed": answer_is_collapsed,
            "answer_is_hidden_before_technical_pass": answer_is_hidden_before_technical_pass,
            "answer_section_is_hidden": answer_section_is_hidden,
        }
    )


@login_required
@require_POST
def start_task(request, attempt_id):
    attempt = get_object_or_404(
        TaskAttempt.objects.select_related("task", "task__queue"),
        id=attempt_id,
        user=request.user,
    )

    historical_attempt_response = block_historical_attempt_action(
        request,
        attempt,
    )

    if historical_attempt_response is not None:
        return historical_attempt_response

    if attempt.technical_locked:
        messages.info(
            request,
            (
                "Техническая часть этого тикета уже выполнена. "
                "Обычный запуск окружения заблокирован, чтобы случайно не сбросить прогресс."
            )
        )

        return redirect(
            "sandbox:task_detail",
            attempt_id=attempt.id
        )

    if attempt.environment_status in [
        TaskAttempt.EnvironmentStatus.STARTING,
        TaskAttempt.EnvironmentStatus.RESTARTING,
    ]:
        messages.info(
            request,
            "Окружение задания уже запускается или перезапускается."
        )

        return redirect(
            "sandbox:task_detail",
            attempt_id=attempt.id
        )

    if attempt.container_name:
        messages.info(
            request,
            "Окружение задания уже запущено."
        )

        return redirect(
            "sandbox:task_detail",
            attempt_id=attempt.id
        )

    if not attempt.is_available:
        return redirect("sandbox:dashboard")

    if not try_mark_environment_starting(attempt):
        messages.info(
            request,
            "Окружение задания уже запускается или перезапускается."
        )

        return redirect(
            "sandbox:task_detail",
            attempt_id=attempt.id
        )

    start_environment_in_background(attempt.id)

    messages.info(
        request,
        "Окружение запускается. Страница обновится после готовности."
    )

    return redirect("sandbox:task_detail", attempt_id=attempt.id)


@login_required
@require_POST
def restart_task(request, attempt_id):
    attempt = get_object_or_404(
        TaskAttempt.objects.select_related("task", "task__queue"),
        id=attempt_id,
        user=request.user,
    )

    historical_attempt_response = block_historical_attempt_action(
        request,
        attempt,
    )

    if historical_attempt_response is not None:
        return historical_attempt_response

    if attempt.technical_locked:
        messages.info(
            request,
            (
                "Техническая часть этого тикета уже выполнена. "
                "Обычный перезапуск заблокирован, чтобы случайно не сбросить прогресс."
            )
        )

        return redirect(
            "sandbox:task_detail",
            attempt_id=attempt.id
        )

    if attempt.environment_status in [
        TaskAttempt.EnvironmentStatus.STARTING,
        TaskAttempt.EnvironmentStatus.RESTARTING,
    ]:
        messages.info(
            request,
            "Окружение задания уже запускается или перезапускается."
        )

        return redirect(
            "sandbox:task_detail",
            attempt_id=attempt.id
        )

    if attempt.check_status == TaskAttempt.CheckStatus.RUNNING:
        messages.info(
            request,
            "Автопроверка уже выполняется. Дождись результата перед перезапуском окружения."
        )

        return redirect(
            "sandbox:task_detail",
            attempt_id=attempt.id
        )

    if not attempt.is_available:
        messages.error(request, "Этот тикет пока недоступен.")
        return redirect("sandbox:dashboard")

    if not try_mark_environment_restarting(attempt):
        messages.info(
            request,
            "Окружение задания уже запускается или перезапускается."
        )

        return redirect(
            "sandbox:task_detail",
            attempt_id=attempt.id
        )

    start_environment_restart_in_background(attempt.id)

    messages.info(
        request,
        "Окружение перезапускается. Страница обновится после готовности."
    )

    return redirect("sandbox:task_detail", attempt_id=attempt.id)


@login_required
@require_POST
@transaction.atomic
def rerun_task(request, attempt_id):
    attempt = get_object_or_404(
        TaskAttempt.objects.select_related("task", "task__queue"),
        id=attempt_id,
        user=request.user,
    )

    if not attempt.is_current:
        messages.info(
            request,
            "Это не текущая попытка. Вернись в очередь и открой актуальное задание."
        )
        return redirect("sandbox:dashboard")

    if not attempt.technical_locked:
        messages.info(
            request,
            (
                "Задание еще не закрыто технически. "
                "Если нужно начать окружение заново, используй обычный перезапуск."
            )
        )
        return redirect(
            "sandbox:task_detail",
            attempt_id=attempt.id,
        )

    if not attempt.is_available:
        messages.error(request, "Этот тикет пока недоступен.")
        return redirect("sandbox:dashboard")

    next_attempt_number = get_next_attempt_number(
        user=request.user,
        task=attempt.task,
    )

    TaskAttempt.objects.filter(
        user=request.user,
        task=attempt.task,
        is_current=True,
    ).update(is_current=False)

    new_attempt = TaskAttempt.objects.create(
        user=request.user,
        task=attempt.task,
        attempt_number=next_attempt_number,
        is_current=True,
        status=TaskAttempt.Status.NEW,
        last_check_output=(
            "Создана дополнительная тренировочная попытка. "
            "Она не влияет на зачет по заданию и не отправляется наставнику на ручную проверку."
        ),
    )

    messages.success(
        request,
        (
            "Создана дополнительная попытка для тренировки. "
            "Предыдущий зачетный результат сохранен."
        )
    )

    return redirect(
        "sandbox:task_detail",
        attempt_id=new_attempt.id,
    )


@login_required
@require_POST
def check_task(request, attempt_id):
    attempt = get_object_or_404(
        TaskAttempt.objects.select_related("task", "task__queue"),
        id=attempt_id,
        user=request.user,
    )

    historical_attempt_response = block_historical_attempt_action(
        request,
        attempt,
    )

    if historical_attempt_response is not None:
        return historical_attempt_response

    if not attempt.is_available:
        messages.error(request, "Этот тикет пока недоступен.")
        return redirect("sandbox:dashboard")

    if attempt.status == TaskAttempt.Status.PASSED:
        messages.info(request, "Этот тикет уже пройден.")
        return redirect("sandbox:task_detail", attempt_id=attempt.id)

    if attempt.status == TaskAttempt.Status.ON_REVIEW:
        messages.info(
            request,
            "Ответ уже зафиксирован и находится на проверке у наставника."
        )
        return redirect("sandbox:task_detail", attempt_id=attempt.id)

    if attempt.check_status == TaskAttempt.CheckStatus.RUNNING:
        messages.info(
            request,
            "Автопроверка уже выполняется. Дождись результата."
        )
        return redirect("sandbox:task_detail", attempt_id=attempt.id)

    if attempt.technical_passed_at:
        if not attempt.task.requires_manual_review:
            messages.info(
                request,
                "Техническая часть уже принята. Для этого задания ручная проверка не требуется."
            )
            return redirect("sandbox:task_detail", attempt_id=attempt.id)

        client_answer = request.POST.get("client_answer", "").strip()
        trainee_report = request.POST.get("trainee_report", "").strip()

        if not client_answer:
            messages.error(
                request,
                "Перед отправкой на проверку нужно написать ответ клиенту."
            )
            return redirect("sandbox:task_detail", attempt_id=attempt.id)

        if not trainee_report:
            messages.error(
                request,
                "Перед отправкой на проверку нужно добавить внутренний комментарий с диагностикой."
            )
            return redirect("sandbox:task_detail", attempt_id=attempt.id)

        attempt.client_answer = client_answer
        attempt.trainee_report = trainee_report
        attempt.status = TaskAttempt.Status.ON_REVIEW
        attempt.mentor_decision = TaskAttempt.MentorDecision.NOT_REVIEWED
        attempt.mentor_reviewed_by = None
        attempt.mentor_reviewed_at = None
        attempt.mentor_feedback_seen_at = timezone.now()

        attempt.save(
            update_fields=[
                "client_answer",
                "trainee_report",
                "status",
                "mentor_decision",
                "mentor_reviewed_by",
                "mentor_reviewed_at",
                "mentor_feedback_seen_at",
            ]
        )

        transaction.on_commit(
            lambda: notify_manual_review_required(attempt)
        )

        messages.success(
            request,
            "Ответ отправлен наставнику на ручную проверку."
        )

        return redirect("sandbox:task_detail", attempt_id=attempt.id)

    if attempt.environment_status in [
        TaskAttempt.EnvironmentStatus.STARTING,
        TaskAttempt.EnvironmentStatus.RESTARTING,
    ]:
        messages.info(
            request,
            "Окружение задания ещё запускается или перезапускается. Дождись готовности."
        )
        return redirect("sandbox:task_detail", attempt_id=attempt.id)

    if attempt.environment_status == TaskAttempt.EnvironmentStatus.ERROR:
        messages.error(
            request,
            "Окружение задания завершилось с ошибкой. Перезапусти окружение перед автопроверкой."
        )
        return redirect("sandbox:task_detail", attempt_id=attempt.id)

    if not attempt.container_name:
        messages.error(
            request,
            "Сначала начни работу с тикетом, чтобы запустить окружение."
        )
        return redirect("sandbox:task_detail", attempt_id=attempt.id)

    check_thread = start_attempt_check_in_background(
        attempt=attempt,
        user_id=request.user.id,
    )

    if check_thread is None:
        messages.info(
            request,
            "Автопроверка уже выполняется. Дождись результата."
        )
    else:
        messages.info(
            request,
            "Автопроверка запущена. Результат появится на странице после завершения."
        )

    return redirect("sandbox:task_detail", attempt_id=attempt.id)


@login_required
@require_GET
def check_task_status(request, attempt_id):
    attempts_queryset = (
        TaskAttempt.objects
        .select_related("task", "task__queue", "user")
    )

    if request.user.is_staff:
        attempt = get_object_or_404(
            attempts_queryset,
            id=attempt_id,
        )
    else:
        attempt = get_object_or_404(
            attempts_queryset,
            id=attempt_id,
            user=request.user,
        )

        if not attempt.is_available:
            return JsonResponse(
                {
                    "error": "attempt_not_available",
                },
                status=403,
            )

    return JsonResponse(
        {
            "attempt_id": attempt.id,
            "attempt_status": attempt.status,
            "attempt_status_label": attempt.get_status_display(),
            "check_status": attempt.check_status,
            "check_status_label": attempt.get_check_status_display(),
            "check_started_at": (
                attempt.check_started_at.isoformat()
                if attempt.check_started_at
                else None
            ),
            "check_finished_at": (
                attempt.check_finished_at.isoformat()
                if attempt.check_finished_at
                else None
            ),
            "technical_passed": attempt.is_technically_completed,
            "last_check_output": attempt.last_check_output,
            "is_running": attempt.check_status == TaskAttempt.CheckStatus.RUNNING,
            "is_finished": attempt.check_status in [
                TaskAttempt.CheckStatus.PASSED,
                TaskAttempt.CheckStatus.FAILED,
                TaskAttempt.CheckStatus.ERROR,
            ],
            "redirect_url": reverse(
                "sandbox:task_detail",
                args=[attempt.id],
            ),
        }
    )


@login_required
@require_GET
def environment_status(request, attempt_id):
    lookup_kwargs = {
        "id": attempt_id,
    }

    if not request.user.is_staff:
        lookup_kwargs["user"] = request.user

    attempt = get_object_or_404(
        TaskAttempt.objects.select_related("task", "task__queue", "user"),
        **lookup_kwargs,
    )

    is_running = attempt.environment_status in [
        TaskAttempt.EnvironmentStatus.STARTING,
        TaskAttempt.EnvironmentStatus.RESTARTING,
    ]

    is_finished = attempt.environment_status in [
        TaskAttempt.EnvironmentStatus.READY,
        TaskAttempt.EnvironmentStatus.ERROR,
    ]

    return JsonResponse(
        {
            "attempt_id": attempt.id,
            "attempt_status": attempt.status,
            "environment_status": attempt.environment_status,
            "environment_status_label": attempt.get_environment_status_display(),
            "environment_ready": (
                attempt.environment_status == TaskAttempt.EnvironmentStatus.READY
            ),
            "last_check_output": attempt.last_check_output,
            "is_running": is_running,
            "is_finished": is_finished,
            "redirect_url": reverse(
                "sandbox:task_detail",
                args=[attempt.id],
            ),
        }
    )


@login_required
@require_POST
def save_mentor_feedback(request, attempt_id):
    if not request.user.is_staff:
        messages.error(request, "У тебя нет доступа к этому действию.")
        return redirect("sandbox:dashboard")

    attempt = get_object_or_404(
        TaskAttempt.objects.select_related("task", "user"),
        id=attempt_id,
    )

    if attempt.is_extra_attempt:
        messages.info(
            request,
            (
                "Это дополнительная тренировочная попытка. "
                "Она не отправляется на ручную проверку наставником."
            )
        )
        return redirect("sandbox:task_detail", attempt_id=attempt.id)

    mentor_decision = request.POST.get(
        "mentor_decision",
        TaskAttempt.MentorDecision.NOT_REVIEWED,
    )

    allowed_decisions = [
        choice[0]
        for choice in TaskAttempt.MentorDecision.choices
    ]

    if mentor_decision not in allowed_decisions:
        mentor_decision = TaskAttempt.MentorDecision.NOT_REVIEWED

    attempt.mentor_feedback = request.POST.get("mentor_feedback", "").strip()
    attempt.mentor_decision = mentor_decision
    attempt.mentor_reviewed_by = request.user
    attempt.mentor_reviewed_at = timezone.now()
    attempt.mentor_feedback_seen_at = None

    update_fields = [
        "mentor_feedback",
        "mentor_decision",
        "mentor_reviewed_by",
        "mentor_reviewed_at",
        "mentor_feedback_seen_at",
    ]

    if mentor_decision == TaskAttempt.MentorDecision.APPROVED:
        attempt.status = TaskAttempt.Status.PASSED
        attempt.finished_at = timezone.now()

        update_fields.extend(
            [
                "status",
                "finished_at",
            ]
        )

        messages.success(
            request,
            "Решение сохранено. Тикет отмечен как пройденный."
        )

    elif mentor_decision == TaskAttempt.MentorDecision.NEEDS_REVISION:
        attempt.status = TaskAttempt.Status.FAILED
        attempt.finished_at = None

        update_fields.extend(
            [
                "status",
                "finished_at",
            ]
        )

        messages.success(
            request,
            "Решение сохранено. Ответ отправлен стажеру на доработку."
        )

    else:
        messages.success(request, "Комментарий наставника сохранен.")

    attempt.save(update_fields=update_fields)

    return redirect("sandbox:task_detail", attempt_id=attempt.id)


@require_GET
def terminal_auth(request, attempt_id=None, port=None):
    if attempt_id is None or port is None:
        attempt_id, port = parse_terminal_uri(
            request.META.get("HTTP_X_ORIGINAL_URI", "")
        )

    if attempt_id is None or port is None:
        log_terminal_auth_denied(
            request,
            reason="invalid_original_uri",
        )
        return HttpResponse(status=403)

    if not request.user.is_authenticated:
        log_terminal_auth_denied(
            request,
            reason="anonymous",
            attempt_id=attempt_id,
            port=port,
        )
        return HttpResponse(status=401)

    attempt = (
        TaskAttempt.objects
        .select_related("task", "task__queue")
        .filter(id=attempt_id)
        .first()
    )

    if not attempt:
        log_terminal_auth_denied(
            request,
            reason="attempt_not_found",
            attempt_id=attempt_id,
            port=port,
        )
        return HttpResponse(status=403)

    user_is_owner = attempt.user_id == request.user.id
    user_is_mentor = request.user.is_staff

    if not user_is_owner and not user_is_mentor:
        log_terminal_auth_denied(
            request,
            reason="forbidden_user",
            attempt_id=attempt_id,
            port=port,
            owner_id=attempt.user_id,
            is_staff=request.user.is_staff,
        )
        return HttpResponse(status=403)

    if attempt.terminal_port != port:
        log_terminal_auth_denied(
            request,
            reason="wrong_port",
            attempt_id=attempt_id,
            port=port,
            actual_port=attempt.terminal_port,
        )
        return HttpResponse(status=403)

    if not attempt.terminal_container_name:
        log_terminal_auth_denied(
            request,
            reason="missing_terminal_container",
            attempt_id=attempt_id,
            port=port,
        )
        return HttpResponse(status=403)

    if not attempt.terminal_url:
        log_terminal_auth_denied(
            request,
            reason="empty_terminal_url",
            attempt_id=attempt_id,
            port=port,
        )
        return HttpResponse(status=403)

    if attempt.technical_locked:
        log_terminal_auth_denied(
            request,
            reason="technically_locked",
            attempt_id=attempt_id,
            port=port,
        )
        return HttpResponse(status=403)

    if not attempt.is_available:
        log_terminal_auth_denied(
            request,
            reason="attempt_not_available",
            attempt_id=attempt_id,
            port=port,
        )
        return HttpResponse(status=403)

    if user_is_mentor and not user_is_owner:
        terminal_logger.warning(
            "mentor_terminal_access mentor_user_id=%s trainee_user_id=%s attempt_id=%s task_slug=%s queue_slug=%s port=%s",
            request.user.id,
            attempt.user_id,
            attempt.id,
            attempt.task.slug,
            attempt.task.queue.slug,
            port,
        )

    return HttpResponse(status=204)
