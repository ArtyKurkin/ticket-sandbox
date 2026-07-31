from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP

from django.contrib.auth.decorators import (
    login_required,
)
from django.core.exceptions import (
    PermissionDenied,
)
from django.db.models import Prefetch
from django.shortcuts import (
    get_object_or_404,
    render,
)
from django.utils import timezone

from ..constants import (
    WEEKLY_QUALITY_TARGET,
    WEEKLY_SPEED_TARGET,
)
from ..models import (
    EntryType,
    StageGroup,
    StageHistory,
    TraineeJourney,
    TraineeStage,
    WeeklyMetric,
)
from ..services.assessment import (
    build_trainee_assessment,
)
from ..services.sandbox_progress import (
    build_sandbox_queue_progress,
)


def _build_gantt_rows(
    journey,
    history_entries,
    today,
):
    """
    Готовит этапы для шкалы
    «план против факта».

    Для каждого применимого этапа
    рассчитываются:

    - плановые min/max дни;
    - фактическое количество дней;
    - состояние этапа;
    - превышение максимального срока.
    """
    applicable_field = (
        "applies_to_internal_transfer"
        if (
            journey.entry_type
            == EntryType.INTERNAL_TRANSFER
        )
        else "applies_to_new_hire"
    )

    stages = (
        TraineeStage.objects
        .filter(
            is_active=True,
            **{
                applicable_field: True,
            },
        )
        .exclude(
            group=StageGroup.DONE,
        )
        .order_by(
            "order",
        )
    )

    history_by_stage = {}

    for history_entry in history_entries:
        history_by_stage.setdefault(
            history_entry.stage_id,
            [],
        ).append(
            history_entry,
        )

    gantt_rows = []

    for stage in stages:
        stage_history = (
            history_by_stage.get(
                stage.id,
                [],
            )
        )

        has_started = bool(
            stage_history,
        )

        actual_days = 0
        fact_started_at = None
        fact_ended_at = None

        if has_started:
            fact_started_at = min(
                entry.started_at
                for entry in stage_history
            )

            has_open_entry = any(
                entry.ended_at is None
                for entry in stage_history
            )

            if not has_open_entry:
                fact_ended_at = max(
                    entry.ended_at
                    for entry in stage_history
                    if (
                        entry.ended_at
                        is not None
                    )
                )

            for entry in stage_history:
                effective_end_date = (
                    entry.ended_at
                    or today
                )

                actual_days += max(
                    (
                        effective_end_date
                        - entry.started_at
                    ).days,
                    0,
                )

        max_days = max(
            stage.max_days,
            1,
        )

        actual_width_percent = (
            min(
                round(
                    actual_days
                    / max_days
                    * 100,
                ),
                100,
            )
            if has_started
            else 0
        )

        min_marker_percent = min(
            round(
                stage.min_days
                / max_days
                * 100,
            ),
            100,
        )

        is_current = (
            journey.current_stage_id
            == stage.id
        )

        is_overdue = (
            has_started
            and actual_days
            > stage.max_days
        )

        gantt_rows.append({
            "stage": stage,
            "has_started": (
                has_started
            ),
            "is_current": (
                is_current
            ),
            "is_completed": (
                has_started
                and not is_current
                and all(
                    entry.ended_at
                    is not None
                    for entry
                    in stage_history
                )
            ),
            "actual_days": (
                actual_days
            ),
            "actual_width_percent": (
                actual_width_percent
            ),
            "min_marker_percent": (
                min_marker_percent
            ),
            "is_overdue": (
                is_overdue
            ),
            "overdue_days": max(
                actual_days
                - stage.max_days,
                0,
            ),
            "fact_started_at": (
                fact_started_at
            ),
            "fact_ended_at": (
                fact_ended_at
            ),
        })

    return gantt_rows


def _build_weekly_metric_chart(
    metrics,
    value_field,
    target,
    minimum_scale_max,
):
    """
    Готовит координаты для SVG-графика
    недельной метрики.

    Координаты возвращаются в диапазоне
    0–100, поэтому график остаётся
    адаптивным без JavaScript.
    """
    values = []

    for metric in metrics:
        value = getattr(
            metric,
            value_field,
        )

        if value is None:
            continue

        values.append({
            "week_number": (
                metric.week_number
            ),
            "value": float(
                value,
            ),
        })

    if not values:
        return {
            "points": [],
            "polyline": "",
            "target_y": None,
            "scale_max": (
                minimum_scale_max
            ),
        }

    first_week = min(
        item["week_number"]
        for item in values
    )

    last_week = max(
        item["week_number"]
        for item in values
    )

    week_span = (
        last_week - first_week
    )

    scale_max = max(
        float(
            minimum_scale_max,
        ),
        float(
            target,
        ),
        max(
            item["value"]
            for item in values
        ),
    )

    points = []

    for item in values:
        if week_span == 0:
            x = 50
        else:
            x = (
                (
                    item["week_number"]
                    - first_week
                )
                / week_span
                * 100
            )

        y = (
            100
            - min(
                item["value"]
                / scale_max,
                1,
            )
            * 100
        )

        points.append({
            **item,
            "x": round(
                x,
                2,
            ),
            "y": round(
                y,
                2,
            ),
        })

    target_y = (
        100
        - min(
            float(target)
            / scale_max,
            1,
        )
        * 100
    )

    polyline = " ".join(
        (
            f'{point["x"]},'
            f'{point["y"]}'
        )
        for point in points
    )

    return {
        "points": points,
        "polyline": polyline,
        "target_y": round(
            target_y,
            2,
        ),
        "scale_max": scale_max,
    }


@login_required
def trainee_detail(
    request,
    journey_id,
):
    if not request.user.is_staff:
        raise PermissionDenied

    history_queryset = (
        StageHistory.objects
        .select_related(
            "stage",
            "changed_by",
        )
        .order_by(
            "-started_at",
            "-id",
        )
    )

    weekly_metrics_queryset = (
        WeeklyMetric.objects
        .order_by(
            "week_number",
        )
    )

    journey = get_object_or_404(
        TraineeJourney.objects
        .select_related(
            "user",
            "current_stage",
        )
        .prefetch_related(
            Prefetch(
                "stage_history",
                queryset=(
                    history_queryset
                ),
            ),
            Prefetch(
                "weekly_metrics",
                queryset=(
                    weekly_metrics_queryset
                ),
            ),
        ),
        id=journey_id,
    )

    sandbox_l1_progress = (
        build_sandbox_queue_progress(
            user=journey.user,
            queue_slug="l1",
        )
    )

    assessment = (
        build_trainee_assessment(
            journey,
            sandbox_progress=(
                sandbox_l1_progress
            ),
        )
    )

    today = timezone.localdate()

    history_entries = list(
        journey.stage_history.all(),
    )

    weekly_metrics_entries = list(
        journey.weekly_metrics.all(),
    )

    weekly_feedback_rows = [
        metric
        for metric in reversed(
            weekly_metrics_entries,
        )
        if (
            metric.mentor_comment
            or metric.next_week_goal
        )
    ]

    speed_values = [
        metric.speed_hours
        for metric
        in weekly_metrics_entries
        if (
            metric.speed_hours
            is not None
        )
    ]

    quality_values = [
        metric.quality_percent
        for metric
        in weekly_metrics_entries
        if (
            metric.quality_percent
            is not None
        )
    ]

    average_speed = None

    if speed_values:
        average_speed = (
            sum(
                speed_values,
                Decimal("0"),
            )
            / Decimal(
                len(speed_values),
            )
        ).quantize(
            Decimal("0.1"),
            rounding=ROUND_HALF_UP,
        )

    average_quality = None

    if quality_values:
        average_quality = int(
            (
                sum(
                    Decimal(value)
                    for value
                    in quality_values
                )
                / Decimal(
                    len(quality_values),
                )
            ).quantize(
                Decimal("1"),
                rounding=ROUND_HALF_UP,
            )
        )

    latest_weekly_metric = (
        weekly_metrics_entries[-1]
        if weekly_metrics_entries
        else None
    )

    weekly_metrics_summary = {
        "count": len(
            weekly_metrics_entries,
        ),
        "average_speed": (
            average_speed
        ),
        "average_quality": (
            average_quality
        ),
        "latest": (
            latest_weekly_metric
        ),
    }

    speed_chart = (
        _build_weekly_metric_chart(
            metrics=(
                weekly_metrics_entries
            ),
            value_field="speed_hours",
            target=(
                WEEKLY_SPEED_TARGET
            ),
            minimum_scale_max=(
                Decimal("8.0")
            ),
        )
    )

    quality_chart = (
        _build_weekly_metric_chart(
            metrics=(
                weekly_metrics_entries
            ),
            value_field=(
                "quality_percent"
            ),
            target=(
                WEEKLY_QUALITY_TARGET
            ),
            minimum_scale_max=100,
        )
    )

    gantt_rows = _build_gantt_rows(
        journey=journey,
        history_entries=history_entries,
        today=today,
    )

    history_rows = []

    for history_entry in history_entries:
        effective_end_date = (
            history_entry.ended_at
            or today
        )

        history_rows.append({
            "entry": history_entry,
            "is_current": (
                history_entry.ended_at
                is None
            ),
            "duration_days": max(
                (
                    effective_end_date
                    - history_entry.started_at
                ).days,
                0,
            ),
        })

    probation_end_date = (
        journey.probation_start_date
        + timedelta(
            days=(
                journey
                .probation_days_total
            ),
        )
    )

    context = {
        "journey": journey,
        "assessment": assessment,
        "history_rows": (
            history_rows
        ),
        "gantt_rows": (
            gantt_rows
        ),
        "probation_end_date": (
            probation_end_date
        ),
        "progress_percent": (
            journey.progress_percent
        ),
        "weekly_metrics_summary": (
            weekly_metrics_summary
        ),
        "weekly_feedback_rows": (
            weekly_feedback_rows
        ),
        "speed_chart": (
            speed_chart
        ),
        "quality_chart": (
            quality_chart
        ),
        "weekly_speed_target": (
            WEEKLY_SPEED_TARGET
        ),
        "weekly_quality_target": (
            WEEKLY_QUALITY_TARGET
        ),
        "sandbox_l1_progress": (
            sandbox_l1_progress
        ),
    }

    return render(
        request,
        (
            "traineediary/"
            "trainee_detail.html"
        ),
        context,
    )
