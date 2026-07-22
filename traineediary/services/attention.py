from dataclasses import dataclass
from decimal import Decimal

from traineediary.models import (
    EntryType,
    StageGroup,
)


SPEED_TARGET = Decimal("6.0")
QUALITY_TARGET = 80

ATTENTION_DAYS_LEFT_BY_ENTRY_TYPE = {
    EntryType.NEW_HIRE: 14,
    EntryType.INTERNAL_TRANSFER: 7,
}


@dataclass(frozen=True)
class AttentionReason:
    code: str
    label: str
    description: str
    severity: str


@dataclass(frozen=True)
class TraineeAttentionSummary:
    reasons: tuple[AttentionReason, ...]

    @property
    def requires_attention(self):
        return bool(self.reasons)

    @property
    def highest_severity(self):
        if any(
            reason.severity == "danger"
            for reason in self.reasons
        ):
            return "danger"

        if self.reasons:
            return "warning"

        return "none"


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


def _get_attention_days_left(journey):
    return ATTENTION_DAYS_LEFT_BY_ENTRY_TYPE.get(
        journey.entry_type,
        14,
    )


def build_attention_summary(journey):
    """
    Определяет ситуации, в которых наставнику
    действительно нужно обратить внимание
    на сотрудника.

    Плановые 6 т/ч и 80% не применяются
    как обязательная норма с первой недели.

    Качество учитывается только на этапе
    WITH_REVIEW. После перехода на следующие
    этапы оно остаётся исключительно историей.
    """
    if (
        journey.current_stage.group
        == StageGroup.DONE
    ):
        return TraineeAttentionSummary(
            reasons=(),
        )

    reasons = []

    if journey.manual_risk_override == "high":
        reasons.append(
            AttentionReason(
                code="manual_high_risk",
                label="Высокий риск",
                description=(
                    "Наставник вручную отметил "
                    "высокий риск."
                ),
                severity="danger",
            ),
        )

    overdue_days = max(
        journey.days_on_stage
        - journey.current_stage.max_days,
        0,
    )

    if overdue_days > 0:
        reasons.append(
            AttentionReason(
                code="stage_overdue",
                label="Превышен срок этапа",
                description=(
                    f"Максимальный срок этапа "
                    f"превышен на {overdue_days} дн."
                ),
                severity="danger",
            ),
        )

    current_group = (
        journey.current_stage.group
    )

    # Качество проверяем только перед выходом
    # с этапа обязательной проверки ответов.
    if (
        current_group == StageGroup.WITH_REVIEW
        and journey.days_on_stage
        >= journey.current_stage.max_days
    ):
        latest_quality_metric = (
            _get_latest_metric(
                journey=journey,
                field_name="quality_percent",
            )
        )

        if latest_quality_metric is None:
            reasons.append(
                AttentionReason(
                    code="quality_missing",
                    label="Нет данных по качеству",
                    description=(
                        "Достигнут максимальный срок "
                        "этапа с проверками, но качество "
                        "ещё не заполнено."
                    ),
                    severity="warning",
                ),
            )

        elif (
            latest_quality_metric.quality_percent
            < QUALITY_TARGET
        ):
            reasons.append(
                AttentionReason(
                    code="quality_below_target",
                    label="Качество пока ниже плана",
                    description=(
                        f"Неделя "
                        f"{latest_quality_metric.week_number}: "
                        f"{latest_quality_metric.quality_percent}% "
                        f"при плане {QUALITY_TARGET}%."
                    ),
                    severity="warning",
                ),
            )

    days_left = (
        journey.days_left_until_probation_end
    )

    attention_days_left = (
        _get_attention_days_left(journey)
    )

    probation_is_near_end = (
        days_left <= attention_days_left
    )

    # Если до конца ИС осталось мало времени,
    # сотрудник должен быть уже на финальном
    # этапе самостоятельной работы.
    if (
        probation_is_near_end
        and current_group
        not in {
            StageGroup.NO_REVIEW,
            StageGroup.DONE,
        }
    ):
        reasons.append(
            AttentionReason(
                code="behind_probation_route",
                label="Отставание по маршруту",
                description=(
                    f"До конца испытательного срока "
                    f"осталось {days_left} дн., "
                    f"а сотрудник ещё не дошёл "
                    f"до этапа «Без проверок»."
                ),
                severity="warning",
            ),
        )

    # Скорость становится критерием готовности
    # только на финальном этапе и ближе к концу ИС.
    if (
        probation_is_near_end
        and current_group == StageGroup.NO_REVIEW
    ):
        latest_speed_metric = (
            _get_latest_metric(
                journey=journey,
                field_name="speed_hours",
            )
        )

        if latest_speed_metric is None:
            reasons.append(
                AttentionReason(
                    code="final_speed_missing",
                    label="Нет данных по скорости",
                    description=(
                        "До конца испытательного срока "
                        "осталось мало времени, но "
                        "скорость ещё не заполнена."
                    ),
                    severity="warning",
                ),
            )

        elif (
            latest_speed_metric.speed_hours
            < SPEED_TARGET
        ):
            reasons.append(
                AttentionReason(
                    code="final_speed_below_target",
                    label="Скорость ниже плана",
                    description=(
                        f"Неделя "
                        f"{latest_speed_metric.week_number}: "
                        f"{latest_speed_metric.speed_hours} т/ч "
                        f"при плане {SPEED_TARGET} т/ч."
                    ),
                    severity="warning",
                ),
            )

    return TraineeAttentionSummary(
        reasons=tuple(reasons),
    )
