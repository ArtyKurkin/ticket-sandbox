from datetime import timedelta

from django.db.models import Count, Prefetch, Q
from django.utils import timezone

from sandbox.models import CheckRun, Queue, TaskAttempt


def build_mentor_dashboard_context(request):
    selected_status = request.GET.get("status", "")
    selected_queue = request.GET.get("queue", "")
    search_query = request.GET.get("q", "").strip()

    attempts = (
        TaskAttempt.objects
        .filter(attempt_number=1)
        .select_related("user", "task", "task__queue")
        .prefetch_related(
            Prefetch(
                "check_runs",
                queryset=CheckRun.objects.order_by("-created_at"),
                to_attr="recent_check_runs",
            )
        )
    )

    if selected_status:
        attempts = attempts.filter(status=selected_status)

    if selected_queue:
        attempts = attempts.filter(task__queue__slug=selected_queue)

    if search_query:
        attempts = attempts.filter(
            Q(user__username__icontains=search_query)
            | Q(user__email__icontains=search_query)
            | Q(task__title__icontains=search_query)
            | Q(task__slug__icontains=search_query)
            | Q(task__queue__name__icontains=search_query)
        )

    dashboard_stats = attempts.aggregate(
        total=Count("id"),
        new=Count(
            "id",
            filter=Q(status=TaskAttempt.Status.NEW),
        ),
        in_progress=Count(
            "id",
            filter=Q(status=TaskAttempt.Status.IN_PROGRESS),
        ),
        on_review=Count(
            "id",
            filter=Q(status=TaskAttempt.Status.ON_REVIEW),
        ),
        failed=Count(
            "id",
            filter=Q(status=TaskAttempt.Status.FAILED),
        ),
        needs_revision=Count(
            "id",
            filter=Q(
                mentor_decision=TaskAttempt.MentorDecision.NEEDS_REVISION,
            ),
        ),
        passed=Count(
            "id",
            filter=Q(status=TaskAttempt.Status.PASSED),
        ),
    )

    pending_review_count = TaskAttempt.objects.filter(
        status=TaskAttempt.Status.ON_REVIEW,
        attempt_number=1,
        is_current=True,
        task__requires_manual_review=True,
    ).count()

    stuck_since = timezone.now() - timedelta(hours=24)

    stuck_attempts_count = (
        TaskAttempt.objects
        .filter(
            attempt_number=1,
            is_current=True,
        )
        .filter(
            Q(
                environment_status=TaskAttempt.EnvironmentStatus.ERROR,
                environment_finished_at__gte=stuck_since,
                last_check_output__icontains="Запуск окружения был прерван",
            )
            | Q(
                check_status=TaskAttempt.CheckStatus.ERROR,
                check_finished_at__gte=stuck_since,
                last_check_output__icontains="Автопроверка была прервана",
            )
        )
        .count()
    )

    attempts = attempts.order_by(
        "user__username",
        "task__queue__order",
        "task__order",
    )

    return {
        "attempts": attempts,
        "status_options": TaskAttempt.Status.choices,
        "queue_options": Queue.objects.filter(is_active=True).order_by("order"),
        "selected_status": selected_status,
        "selected_queue": selected_queue,
        "search_query": search_query,
        "dashboard_stats": dashboard_stats,
        "pending_review_count": pending_review_count,
        "stuck_attempts_count": stuck_attempts_count,
    }
