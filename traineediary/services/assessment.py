from dataclasses import dataclass

from traineediary.models import (
    EntryType,
    RiskLevel,
    StageGroup,
    TraineeStage,
)

from .attention import (
    ATTENTION_DAYS_LEFT_BY_ENTRY_TYPE,
    QUALITY_TARGET,
    SPEED_TARGET,
    TraineeAttentionSummary,
    build_attention_summary,
)
from .sandbox_progress import (
    SandboxQueueProgress,
    build_sandbox_queue_progress,
)


ALMOST_READY_STAGE_DAYS = 3


@dataclass(frozen=True)
class ReadinessReason:
    code: str
    label: str
    description: str


@dataclass(frozen=True)
class TraineeReadinessSummary:
    state: str
    label: str
    reasons: tuple[ReadinessReason, ...]
    next_stage: TraineeStage | None

    @property
    def is_ready(self):
        return self.state == "ready"

    @property
    def is_almost_ready(self):
        return self.state == "almost_ready"

    @property
    def is_completed(self):
        return self.state == "completed"


@dataclass(frozen=True)
class TraineeAssessment:
    risk_level: str | None
    attention: TraineeAttentionSummary
    readiness: TraineeReadinessSummary

    @property
    def requires_attention(self):
        return self.attention.requires_attention


def _get_next_applicable_stage(
    journey,
):
    applicable_field = (
        "applies_to_internal_transfer"
        if (
            journey.entry_type
            == EntryType.INTERNAL_TRANSFER
        )
        else "applies_to_new_hire"
    )

    return (
        TraineeStage.objects
        .filter(
            is_active=True,
            order__gt=(
                journey.current_stage.order
            ),
            **{
                applicable_field: True,
            },
        )
        .order_by(
            "order",
            "id",
        )
        .first()
    )


def _get_latest_metric(
    journey,
    field_name,
):
    return (
        journey.weekly_metrics
        .filter(
            **{
                f"{field_name}__isnull": False,
            },
        )
        .order_by(
            "-week_number",
            "-id",
        )
        .first()
    )


def _build_risk_level(
    journey,
    attention,
):
    if (
        journey.current_stage.group
        == StageGroup.DONE
    ):
        return None

    if journey.manual_risk_override:
        return journey.manual_risk_override

    if attention.highest_severity == "danger":
        return RiskLevel.HIGH

    if attention.requires_attention:
        return RiskLevel.MEDIUM

    return RiskLevel.LOW


def _not_ready(
    *,
    reasons,
    next_stage,
):
    return TraineeReadinessSummary(
        state="not_ready",
        label="Пока не готов",
        reasons=tuple(reasons),
        next_stage=next_stage,
    )


def _almost_ready(
    *,
    reasons,
    next_stage,
):
    return TraineeReadinessSummary(
        state="almost_ready",
        label="Почти готов",
        reasons=tuple(reasons),
        next_stage=next_stage,
    )


def _ready(
    *,
    next_stage,
):
    return TraineeReadinessSummary(
        state="ready",
        label="Готов к переходу",
        reasons=(),
        next_stage=next_stage,
    )


def _build_sandbox_readiness(
    journey,
    sandbox_progress,
    next_stage,
):
    if not sandbox_progress.queue_exists:
        return _not_ready(
            reasons=[
                ReadinessReason(
                    code="sandbox_queue_missing",
                    label="Очередь L1 не найдена",
                    description=(
                        "Невозможно проверить "
                        "выполнение заданий L1."
                    ),
                ),
            ],
            next_stage=next_stage,
        )

    if sandbox_progress.total_count == 0:
        return _not_ready(
            reasons=[
                ReadinessReason(
                    code="sandbox_tasks_missing",
                    label="В L1 нет заданий",
                    description=(
                        "В очереди L1 нет активных "
                        "заданий для проверки."
                    ),
                ),
            ],
            next_stage=next_stage,
        )

    if sandbox_progress.is_ready:
        return _ready(
            next_stage=next_stage,
        )

    all_tasks_completed_or_on_review = (
        (
            sandbox_progress.passed_count
            + sandbox_progress.on_review_count
        )
        == sandbox_progress.total_count
    )

    if (
        all_tasks_completed_or_on_review
        and sandbox_progress.on_review_count > 0
    ):
        return _almost_ready(
            reasons=[
                ReadinessReason(
                    code="sandbox_tasks_on_review",
                    label="Задания ждут проверки",
                    description=(
                        f"На проверке: "
                        f"{sandbox_progress.on_review_count}."
                    ),
                ),
            ],
            next_stage=next_stage,
        )

    return _not_ready(
        reasons=[
            ReadinessReason(
                code="sandbox_tasks_remaining",
                label="L1 ещё не завершён",
                description=(
                    f"Осталось зачесть заданий: "
                    f"{sandbox_progress.remaining_count}."
                ),
            ),
        ],
        next_stage=next_stage,
    )


def _build_with_review_readiness(
    journey,
    next_stage,
):
    reasons = []

    days_until_minimum = max(
        journey.current_stage.min_days
        - journey.days_on_stage,
        0,
    )

    if days_until_minimum > 0:
        reasons.append(
            ReadinessReason(
                code="minimum_stage_days",
                label="Не пройден минимальный срок",
                description=(
                    f"До минимального срока этапа "
                    f"осталось {days_until_minimum} дн."
                ),
            ),
        )

    latest_quality_metric = (
        _get_latest_metric(
            journey=journey,
            field_name="quality_percent",
        )
    )

    if latest_quality_metric is None:
        reasons.append(
            ReadinessReason(
                code="quality_missing",
                label="Нет данных по качеству",
                description=(
                    "Для перехода нужно заполнить "
                    "качество за последнюю неделю."
                ),
            ),
        )

    elif (
        latest_quality_metric.quality_percent
        < QUALITY_TARGET
    ):
        reasons.append(
            ReadinessReason(
                code="quality_below_target",
                label="Качество ниже плана",
                description=(
                    f"Сейчас "
                    f"{latest_quality_metric.quality_percent}%, "
                    f"план — {QUALITY_TARGET}%."
                ),
            ),
        )

    if not reasons:
        return _ready(
            next_stage=next_stage,
        )

    only_minimum_time_remains = (
        len(reasons) == 1
        and reasons[0].code
        == "minimum_stage_days"
        and days_until_minimum
        <= ALMOST_READY_STAGE_DAYS
    )

    if only_minimum_time_remains:
        return _almost_ready(
            reasons=reasons,
            next_stage=next_stage,
        )

    return _not_ready(
        reasons=reasons,
        next_stage=next_stage,
    )


def _build_time_based_readiness(
    journey,
    next_stage,
):
    days_until_minimum = max(
        journey.current_stage.min_days
        - journey.days_on_stage,
        0,
    )

    if days_until_minimum == 0:
        return _ready(
            next_stage=next_stage,
        )

    reasons = [
        ReadinessReason(
            code="minimum_stage_days",
            label="Не пройден минимальный срок",
            description=(
                f"До минимального срока этапа "
                f"осталось {days_until_minimum} дн."
            ),
        ),
    ]

    if (
        days_until_minimum
        <= ALMOST_READY_STAGE_DAYS
    ):
        return _almost_ready(
            reasons=reasons,
            next_stage=next_stage,
        )

    return _not_ready(
        reasons=reasons,
        next_stage=next_stage,
    )


def _build_no_review_readiness(
    journey,
    next_stage,
):
    reasons = []

    days_until_minimum = max(
        journey.current_stage.min_days
        - journey.days_on_stage,
        0,
    )

    if days_until_minimum > 0:
        reasons.append(
            ReadinessReason(
                code="minimum_stage_days",
                label="Не пройден минимальный срок",
                description=(
                    f"До минимального срока этапа "
                    f"осталось {days_until_minimum} дн."
                ),
            ),
        )

    days_left = (
        journey.days_left_until_probation_end
    )

    if days_left > 0:
        reasons.append(
            ReadinessReason(
                code="probation_not_finished",
                label="Испытательный срок не завершён",
                description=(
                    f"До конца испытательного срока "
                    f"осталось {days_left} дн."
                ),
            ),
        )

    latest_speed_metric = (
        _get_latest_metric(
            journey=journey,
            field_name="speed_hours",
        )
    )

    if latest_speed_metric is None:
        reasons.append(
            ReadinessReason(
                code="speed_missing",
                label="Нет данных по скорости",
                description=(
                    "Для завершения ИС нужно "
                    "заполнить скорость."
                ),
            ),
        )

    elif (
        latest_speed_metric.speed_hours
        < SPEED_TARGET
    ):
        reasons.append(
            ReadinessReason(
                code="speed_below_target",
                label="Скорость ниже плана",
                description=(
                    f"Сейчас "
                    f"{latest_speed_metric.speed_hours} т/ч, "
                    f"план — {SPEED_TARGET} т/ч."
                ),
            ),
        )

    if not reasons:
        return _ready(
            next_stage=next_stage,
        )

    time_reason_codes = {
        "minimum_stage_days",
        "probation_not_finished",
    }

    reason_codes = {
        reason.code
        for reason in reasons
    }

    almost_ready_days = (
        ATTENTION_DAYS_LEFT_BY_ENTRY_TYPE.get(
            journey.entry_type,
            14,
        )
    )

    only_time_remains = (
        reason_codes
        and reason_codes.issubset(
            time_reason_codes,
        )
        and days_until_minimum
        <= ALMOST_READY_STAGE_DAYS
        and days_left
        <= almost_ready_days
    )

    if only_time_remains:
        return _almost_ready(
            reasons=reasons,
            next_stage=next_stage,
        )

    return _not_ready(
        reasons=reasons,
        next_stage=next_stage,
    )


def build_readiness_summary(
    journey,
    *,
    sandbox_progress: (
        SandboxQueueProgress | None
    ) = None,
):
    current_group = (
        journey.current_stage.group
    )

    if current_group == StageGroup.DONE:
        return TraineeReadinessSummary(
            state="completed",
            label="Адаптация завершена",
            reasons=(),
            next_stage=None,
        )

    next_stage = _get_next_applicable_stage(
        journey,
    )

    if next_stage is None:
        return _not_ready(
            reasons=[
                ReadinessReason(
                    code="next_stage_missing",
                    label="Не найден следующий этап",
                    description=(
                        "В маршруте нет следующего "
                        "активного этапа."
                    ),
                ),
            ],
            next_stage=None,
        )

    if (
        current_group
        == StageGroup.SANDBOX_CANDIDATE
    ):
        if sandbox_progress is None:
            sandbox_progress = (
                build_sandbox_queue_progress(
                    user=journey.user,
                )
            )

        return _build_sandbox_readiness(
            journey=journey,
            sandbox_progress=sandbox_progress,
            next_stage=next_stage,
        )

    if current_group == StageGroup.WITH_REVIEW:
        return _build_with_review_readiness(
            journey=journey,
            next_stage=next_stage,
        )

    if current_group == StageGroup.NO_REVIEW:
        return _build_no_review_readiness(
            journey=journey,
            next_stage=next_stage,
        )

    return _build_time_based_readiness(
        journey=journey,
        next_stage=next_stage,
    )


def build_trainee_assessment(
    journey,
    *,
    sandbox_progress: (
        SandboxQueueProgress | None
    ) = None,
):
    attention = build_attention_summary(
        journey,
    )

    readiness = build_readiness_summary(
        journey,
        sandbox_progress=sandbox_progress,
    )

    return TraineeAssessment(
        risk_level=_build_risk_level(
            journey=journey,
            attention=attention,
        ),
        attention=attention,
        readiness=readiness,
    )
