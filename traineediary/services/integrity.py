from dataclasses import dataclass

from django.utils import timezone

from ..models import (
    CompletionStatus,
    StageGroup,
    TraineeJourney,
)


@dataclass(
    frozen=True,
    slots=True,
)
class TraineeIntegrityIssue:
    journey_id: int
    username: str
    code: str
    message: str

    def __str__(self):
        return (
            f"[{self.code}] "
            f"journey={self.journey_id} "
            f"user={self.username}: "
            f"{self.message}"
        )


def check_journey_integrity(
    journey: TraineeJourney,
    *,
    today=None,
):
    """
    Проверяет согласованность карточки сотрудника.

    Функция ничего не изменяет в базе
    и возвращает список найденных проблем.
    """
    today = today or timezone.localdate()
    issues = []

    def add_issue(
        code,
        message,
    ):
        issues.append(
            TraineeIntegrityIssue(
                journey_id=journey.id,
                username=journey.user.username,
                code=code,
                message=message,
            ),
        )

    # --- Основные даты и этап ---

    if (
        journey.probation_start_date
        > today
    ):
        add_issue(
            "PROBATION_START_IN_FUTURE",
            (
                "Дата начала испытательного срока "
                "находится в будущем."
            ),
        )

    if (
        journey.stage_started_at
        < journey.probation_start_date
    ):
        add_issue(
            "STAGE_BEFORE_PROBATION",
            (
                "Текущий этап начался раньше "
                "испытательного срока."
            ),
        )

    if journey.stage_started_at > today:
        add_issue(
            "STAGE_START_IN_FUTURE",
            (
                "Дата начала текущего этапа "
                "находится в будущем."
            ),
        )

    if not (
        journey.current_stage
        .applies_to_entry_type(
            journey.entry_type,
        )
    ):
        add_issue(
            "STAGE_NOT_APPLICABLE",
            (
                "Текущий этап не применяется "
                "к выбранному типу входа."
            ),
        )

    # --- История этапов ---

    history_entries = sorted(
        journey.stage_history.all(),
        key=lambda entry: (
            entry.started_at,
            entry.id,
        ),
    )

    if not history_entries:
        add_issue(
            "NO_STAGE_HISTORY",
            (
                "У карточки отсутствует "
                "история этапов."
            ),
        )

    open_entries = [
        entry
        for entry in history_entries
        if entry.ended_at is None
    ]

    if len(open_entries) != 1:
        add_issue(
            "OPEN_HISTORY_COUNT",
            (
                "Ожидалась одна открытая запись "
                "истории, найдено "
                f"{len(open_entries)}."
            ),
        )

    if len(open_entries) == 1:
        open_entry = open_entries[0]

        if (
            open_entry.stage_id
            != journey.current_stage_id
        ):
            add_issue(
                "CURRENT_STAGE_MISMATCH",
                (
                    "Текущий этап карточки "
                    "не совпадает с открытой "
                    "записью истории."
                ),
            )

        if (
            open_entry.started_at
            != journey.stage_started_at
        ):
            add_issue(
                "CURRENT_STAGE_DATE_MISMATCH",
                (
                    "Дата начала текущего этапа "
                    "не совпадает с открытой "
                    "записью истории."
                ),
            )

    if history_entries:
        first_entry = history_entries[0]

        if (
            first_entry.started_at
            != journey.probation_start_date
        ):
            add_issue(
                "FIRST_HISTORY_DATE_MISMATCH",
                (
                    "Первая запись истории "
                    "начинается не с даты "
                    "старта испытательного срока."
                ),
            )

    for entry in history_entries:
        if (
            entry.ended_at is not None
            and entry.ended_at
            < entry.started_at
        ):
            add_issue(
                "INVALID_HISTORY_INTERVAL",
                (
                    f"Запись истории #{entry.id} "
                    "заканчивается раньше, "
                    "чем начинается."
                ),
            )

    for previous_entry, next_entry in zip(
        history_entries,
        history_entries[1:],
    ):
        if previous_entry.ended_at is None:
            add_issue(
                "OPEN_HISTORY_NOT_LAST",
                (
                    f"Запись истории "
                    f"#{previous_entry.id} "
                    "остаётся открытой, хотя "
                    "после неё есть другой этап."
                ),
            )

            continue

        if (
            previous_entry.ended_at
            < next_entry.started_at
        ):
            add_issue(
                "HISTORY_GAP",
                (
                    "Между записями истории "
                    f"#{previous_entry.id} и "
                    f"#{next_entry.id} есть "
                    "пропуск по датам."
                ),
            )

        elif (
            previous_entry.ended_at
            > next_entry.started_at
        ):
            add_issue(
                "HISTORY_OVERLAP",
                (
                    "Записи истории "
                    f"#{previous_entry.id} и "
                    f"#{next_entry.id} "
                    "пересекаются по датам."
                ),
            )

    # --- Завершение испытательного срока ---

    completion_comment = (
        journey.completion_comment
        or ""
    ).strip()

    has_completion_data = any(
        (
            journey.completion_status,
            journey.completed_at,
            completion_comment,
            journey.completed_by_id,
        ),
    )

    is_done = (
        journey.current_stage.group
        == StageGroup.DONE
    )

    if is_done:
        if not journey.completion_status:
            add_issue(
                "DONE_WITHOUT_COMPLETION_STATUS",
                (
                    "Карточка находится на "
                    "финальном этапе, но результат "
                    "испытательного срока не указан."
                ),
            )

        if journey.completed_at is None:
            add_issue(
                "DONE_WITHOUT_COMPLETED_AT",
                (
                    "Карточка находится на "
                    "финальном этапе, но дата "
                    "завершения не указана."
                ),
            )

    elif has_completion_data:
        add_issue(
            "COMPLETION_DATA_OUTSIDE_DONE",
            (
                "Данные завершения заполнены, "
                "хотя сотрудник находится "
                "не на финальном этапе."
            ),
        )

    if (
        journey.completion_status
        and journey.completion_status
        not in CompletionStatus.values
    ):
        add_issue(
            "UNKNOWN_COMPLETION_STATUS",
            (
                "Указан неизвестный результат "
                "испытательного срока."
            ),
        )

    if (
        journey.completion_status
        == CompletionStatus.TERMINATED
        and not completion_comment
    ):
        add_issue(
            "TERMINATED_WITHOUT_COMMENT",
            (
                "Для прекращённого "
                "испытательного срока "
                "не указана причина."
            ),
        )

    if journey.completed_at is not None:
        if (
            journey.completed_at
            < journey.probation_start_date
        ):
            add_issue(
                "COMPLETION_BEFORE_PROBATION",
                (
                    "Дата завершения находится "
                    "раньше даты начала ИС."
                ),
            )

        if journey.completed_at > today:
            add_issue(
                "COMPLETION_IN_FUTURE",
                (
                    "Дата завершения находится "
                    "в будущем."
                ),
            )

        if (
            is_done
            and journey.stage_started_at
            != journey.completed_at
        ):
            add_issue(
                "DONE_STAGE_DATE_MISMATCH",
                (
                    "Дата перехода на финальный "
                    "этап не совпадает с датой "
                    "завершения ИС."
                ),
            )

    return issues
