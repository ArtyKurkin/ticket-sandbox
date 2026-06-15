from sandbox.models import TaskAttempt


def enrich_attempts_display_state(attempts):
    """
    Добавляет к текущим попыткам поля для отображения в dashboard.

    Важно:
    - текущая попытка показывает, что стажер делает сейчас;
    - исторический статус показывает, было ли задание уже технически выполнено
      или принято наставником раньше.
    """

    attempts = list(attempts)

    if not attempts:
        return attempts

    user = attempts[0].user
    task_ids = [attempt.task_id for attempt in attempts]

    history_attempts = (
        TaskAttempt.objects
        .filter(
            user=user,
            task_id__in=task_ids,
        )
        .select_related("task")
        .order_by("-attempt_number", "-id")
    )

    technical_by_task_id = {}
    approved_by_task_id = {}

    for history_attempt in history_attempts:
        if (
            history_attempt.technical_passed_at
            and history_attempt.task_id not in technical_by_task_id
        ):
            technical_by_task_id[history_attempt.task_id] = history_attempt

        if (
            history_attempt.mentor_decision == TaskAttempt.MentorDecision.APPROVED
            and history_attempt.task_id not in approved_by_task_id
        ):
            approved_by_task_id[history_attempt.task_id] = history_attempt

    for attempt in attempts:
        technical_attempt = technical_by_task_id.get(attempt.task_id)
        approved_attempt = approved_by_task_id.get(attempt.task_id)

        attempt.was_technically_completed = technical_attempt is not None
        attempt.technical_completed_at = (
            technical_attempt.technical_passed_at
            if technical_attempt
            else None
        )

        attempt.was_mentor_approved = approved_attempt is not None
        attempt.mentor_approved_at = (
            approved_attempt.mentor_reviewed_at
            if approved_attempt
            else None
        )

        apply_learning_status(attempt)
        apply_technical_status(attempt)
        apply_manual_review_status(attempt)
        apply_current_attempt_label(attempt)

    return attempts


def apply_learning_status(attempt):
    if not attempt.is_available:
        attempt.learning_status_label = "Заблокировано"
        attempt.learning_status_class = "status-muted"
        return

    if attempt.was_mentor_approved:
        attempt.learning_status_label = "Пройдено"
        attempt.learning_status_class = "status-success"
        return

    if attempt.was_technically_completed:
        attempt.learning_status_label = "Технически выполнено"
        attempt.learning_status_class = "status-success"
        return

    if attempt.status == TaskAttempt.Status.IN_PROGRESS:
        attempt.learning_status_label = "В работе"
        attempt.learning_status_class = "status-primary"
        return

    if attempt.status == TaskAttempt.Status.ON_REVIEW:
        attempt.learning_status_label = "На проверке"
        attempt.learning_status_class = "status-primary"
        return

    if attempt.status == TaskAttempt.Status.FAILED:
        attempt.learning_status_label = "Доработать"
        attempt.learning_status_class = "status-danger"
        return

    attempt.learning_status_label = "Новый"
    attempt.learning_status_class = "status-primary"


def apply_technical_status(attempt):
    if attempt.was_technically_completed:
        attempt.technical_status_label = "Пройдена"
        attempt.technical_status_class = "status-success"
        attempt.technical_icon = "circle-check-big"
        attempt.technical_icon_class = "progress-icon-success"
        attempt.technical_tooltip = "Техническая часть засчитана"
        return

    if attempt.status == TaskAttempt.Status.FAILED:
        attempt.technical_status_label = "Не пройдена"
        attempt.technical_status_class = "status-danger"
        attempt.technical_icon = "triangle-alert"
        attempt.technical_icon_class = "progress-icon-danger"
        attempt.technical_tooltip = "Техническая проверка не пройдена"
        return

    if attempt.status == TaskAttempt.Status.ON_REVIEW:
        attempt.technical_status_label = "Проверяется"
        attempt.technical_status_class = "status-primary"
        attempt.technical_icon = "loader-circle"
        attempt.technical_icon_class = "progress-icon-primary"
        attempt.technical_tooltip = "Техническая проверка в процессе"
        return

    attempt.technical_status_label = "Не проверялась"
    attempt.technical_status_class = "status-muted"
    attempt.technical_icon = "circle"
    attempt.technical_icon_class = "progress-icon-muted"
    attempt.technical_tooltip = "Техническая часть еще не засчитана"


def apply_manual_review_status(attempt):
    if not attempt.task.requires_manual_review:
        attempt.manual_review_label = "Не требуется"
        attempt.manual_review_class = "status-muted"
        attempt.manual_icon = "minus-circle"
        attempt.manual_icon_class = "progress-icon-muted"
        attempt.manual_tooltip = "Ручная проверка для этого задания не требуется"
        return

    if attempt.was_mentor_approved:
        attempt.manual_review_label = "Принято"
        attempt.manual_review_class = "status-success"
        attempt.manual_icon = "circle-check-big"
        attempt.manual_icon_class = "progress-icon-success"
        attempt.manual_tooltip = "Ответ принят наставником"
        return

    if attempt.mentor_decision == TaskAttempt.MentorDecision.NEEDS_REVISION:
        attempt.manual_review_label = "Доработать"
        attempt.manual_review_class = "status-danger"
        attempt.manual_icon = "triangle-alert"
        attempt.manual_icon_class = "progress-icon-danger"
        attempt.manual_tooltip = "Наставник отправил ответ на доработку"
        return

    if (
        attempt.status == TaskAttempt.Status.ON_REVIEW
        and attempt.technical_passed_at
    ):
        attempt.manual_review_label = "На проверке"
        attempt.manual_review_class = "status-primary"
        attempt.manual_icon = "loader-circle"
        attempt.manual_icon_class = "progress-icon-primary"
        attempt.manual_tooltip = "Ответ ожидает ручной проверки наставником"
        return

    attempt.manual_review_label = "Не проверено"
    attempt.manual_review_class = "status-muted"
    attempt.manual_icon = "circle"
    attempt.manual_icon_class = "progress-icon-muted"
    attempt.manual_tooltip = "Ручная проверка еще не выполнялась"


def apply_current_attempt_label(attempt):
    if getattr(attempt, "attempt_number", 1) <= 1:
        attempt.current_attempt_label = ""
        return

    attempt.current_attempt_label = (
        f"Попытка #{attempt.attempt_number}: "
        f"{attempt.get_status_display()}"
    )
