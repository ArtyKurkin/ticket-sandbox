import json
from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.views.decorators.http import require_POST
from django.db.models import Max, Prefetch, Q

from .models import (
    EntryType,
    StageGroup,
    StageHistory,
    TraineeJourney,
    TraineeStage,
    WeeklyMetric,
)
from .forms import (
    EditTraineeForm,
    NewTraineeForm,
    WeeklyMetricForm,
)
from .services.sandbox_progress import (
    build_sandbox_queue_progress,
    build_sandbox_queue_progress_map,
)
from .services.attention import (
    build_attention_summary,
)


WEEKLY_SPEED_TARGET = Decimal("6.0")
WEEKLY_QUALITY_TARGET = 80

TICKET_METRIC_GROUPS = {
    StageGroup.WITH_REVIEW,
    StageGroup.OPTIONAL_REVIEW,
    StageGroup.NO_REVIEW,
}


def _metric_trend_state(delta):
    if delta > 0:
        return "up"

    if delta < 0:
        return "down"

    return "stable"


def _build_weekly_pulse(journeys):
    """
    Сравнивает две последние недели, в которых заполнена скорость.

    Качество сравнивается только тогда, когда оно заполнено
    в обеих неделях. После фиксации качества общая динамика
    рассчитывается только по скорости.

    Стажёры с просадкой выводятся первыми, затем стажёры
    с положительной динамикой и после них — без изменений.
    """
    pulse_rows = []

    for journey in journeys:
        if (
            journey.current_stage.group
            not in TICKET_METRIC_GROUPS
        ):
            continue

        speed_metrics = sorted(
            (
                metric
                for metric in journey.weekly_metrics.all()
                if metric.speed_hours is not None
            ),
            key=lambda metric: metric.week_number,
        )

        if len(speed_metrics) < 2:
            continue

        previous_metric = speed_metrics[-2]
        latest_metric = speed_metrics[-1]

        speed_delta = (
            latest_metric.speed_hours
            - previous_metric.speed_hours
        ).quantize(
            Decimal("0.1"),
        )

        speed_state = _metric_trend_state(
            speed_delta,
        )

        quality_delta = None
        quality_state = "fixed"

        if (
            previous_metric.quality_percent is not None
            and latest_metric.quality_percent is not None
        ):
            quality_delta = (
                latest_metric.quality_percent
                - previous_metric.quality_percent
            )

            quality_state = _metric_trend_state(
                quality_delta,
            )

        has_decline = (
            speed_state == "down"
            or quality_state == "down"
        )

        has_growth = (
            speed_state == "up"
            or quality_state == "up"
        )

        if has_decline:
            overall_state = "danger"
        elif has_growth:
            overall_state = "success"
        else:
            overall_state = "stable"

        pulse_rows.append({
            "journey": journey,
            "previous": previous_metric,
            "latest": latest_metric,
            "speed_delta": speed_delta,
            "quality_delta": quality_delta,
            "speed_state": speed_state,
            "quality_state": quality_state,
            "overall_state": overall_state,
        })

    state_order = {
        "danger": 0,
        "success": 1,
        "stable": 2,
    }

    pulse_rows.sort(
        key=lambda row: (
            state_order[row["overall_state"]],
            (
                row["journey"].user.last_name
                or row["journey"].user.username
            ).lower(),
        ),
    )

    return pulse_rows


def _get_next_applicable_stage(journey):
    """
    Возвращает следующий активный этап маршрута
    с учётом типа входа сотрудника.
    """
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
            order__gt=journey.current_stage.order,
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


def _build_l1_transition_state(
    journey,
    sandbox_progress,
):
    """
    Рекомендует переход только тогда, когда:

    - все зачётные задания L1 пройдены;
    - сотрудник всё ещё находится на этапе
      перед выходом в реальные тикеты.
    """
    should_transition = (
        sandbox_progress.is_ready
        and (
            journey.current_stage.group
            == StageGroup.SANDBOX_CANDIDATE
        )
    )

    return {
        "should_transition": should_transition,
        "next_stage": (
            _get_next_applicable_stage(journey)
            if should_transition
            else None
        ),
    }


@login_required
def dashboard(request):
    if not request.user.is_staff:
        raise PermissionDenied

    query = request.GET.get(
        "q",
        "",
    ).strip()

    entry_type_filter = request.GET.get(
        "entry_type",
        "",
    )

    stage_filter = request.GET.get(
        "stage",
        "",
    )

    attention_filter = request.GET.get(
        "attention",
        "",
    )

    status_filter = request.GET.get(
        "status",
        "active",
    )

    valid_entry_types = {
        value
        for value, _label in EntryType.choices
    }

    if entry_type_filter not in valid_entry_types:
        entry_type_filter = ""

    if attention_filter not in {
        "",
        "1",
        "0",
    }:
        attention_filter = ""

    if status_filter not in {
        "active",
        "completed",
        "all",
    }:
        status_filter = "active"

    stage_id = None

    if stage_filter:
        try:
            stage_id = int(stage_filter)
        except (TypeError, ValueError):
            stage_filter = ""

    weekly_metrics_queryset = (
        WeeklyMetric.objects
        .order_by("week_number")
    )

    journeys_queryset = (
        TraineeJourney.objects
        .select_related(
            "user",
            "current_stage",
        )
        .prefetch_related(
            Prefetch(
                "weekly_metrics",
                queryset=weekly_metrics_queryset,
            ),
        )
    )

    if status_filter == "active":
        journeys_queryset = (
            journeys_queryset.exclude(
                current_stage__group=StageGroup.DONE,
            )
        )

    elif status_filter == "completed":
        journeys_queryset = (
            journeys_queryset.filter(
                current_stage__group=StageGroup.DONE,
            )
        )

    if query:
        journeys_queryset = (
            journeys_queryset.filter(
                Q(
                    user__first_name__icontains=query,
                )
                | Q(
                    user__last_name__icontains=query,
                )
                | Q(
                    user__username__icontains=query,
                )
            )
        )

    if entry_type_filter:
        journeys_queryset = (
            journeys_queryset.filter(
                entry_type=entry_type_filter,
            )
        )

    if stage_id is not None:
        journeys_queryset = (
            journeys_queryset.filter(
                current_stage_id=stage_id,
            )
        )

    journeys = list(
        journeys_queryset.order_by(
            "current_stage__order",
            "user__last_name",
            "user__first_name",
            "user__username",
        )
    )

    sandbox_progress_by_user_id = (
        build_sandbox_queue_progress_map(
            users=[
                journey.user
                for journey in journeys
            ],
        )
    )

    ready_to_transition_count = 0
    needs_attention_count = 0

    group_counts = {}
    rows = []
    filtered_journeys = []

    for journey in journeys:
        risk = journey.risk_level

        attention_summary = (
            build_attention_summary(
                journey,
            )
        )

        if (
            attention_filter == "1"
            and not (
                attention_summary
                .requires_attention
            )
        ):
            continue

        if (
            attention_filter == "0"
            and (
                attention_summary
                .requires_attention
            )
        ):
            continue

        group = journey.current_stage.group

        group_counts[group] = (
            group_counts.get(group, 0) + 1
        )

        sandbox_l1_progress = (
            sandbox_progress_by_user_id[
                journey.user_id
            ]
        )

        l1_transition_state = (
            _build_l1_transition_state(
                journey=journey,
                sandbox_progress=(
                    sandbox_l1_progress
                ),
            )
        )

        if (
            l1_transition_state[
                "should_transition"
            ]
        ):
            ready_to_transition_count += 1

        if (
            attention_summary
            .requires_attention
        ):
            needs_attention_count += 1

        filtered_journeys.append(
            journey,
        )

        rows.append({
            "journey": journey,
            "risk": risk,
            "attention_summary": (
                attention_summary
            ),
            "progress_percent": (
                journey.progress_percent
            ),
            "days_total": (
                journey.days_total
            ),
            "days_left": (
                journey
                .days_left_until_probation_end
            ),
            "expected_transition": (
                None
                if group == StageGroup.DONE
                else (
                    journey
                    .expected_stage_transition_date
                )
            ),
            "sandbox_l1_progress": (
                sandbox_l1_progress
            ),
            "l1_transition_state": (
                l1_transition_state
            ),
        })

    if status_filter == "completed":
        summary_groups = [
            choice
            for choice in StageGroup.choices
            if choice[0] == StageGroup.DONE
        ]

    elif status_filter == "all":
        summary_groups = list(
            StageGroup.choices,
        )

    else:
        summary_groups = [
            choice
            for choice in StageGroup.choices
            if choice[0] != StageGroup.DONE
        ]

    summary_cards = [
        {
            "label": label,
            "count": group_counts.get(
                value,
                0,
            ),
        }
        for value, label in summary_groups
    ]

    context = {
        "rows": rows,
        "filtered_count": len(rows),
        "summary_cards": summary_cards,
        "needs_attention_count": (
            needs_attention_count
        ),
        "ready_to_transition_count": (
            ready_to_transition_count
        ),
        "weekly_pulse": (
            _build_weekly_pulse(
                filtered_journeys,
            )
        ),
        "entry_type_choices": [
            (value, label)
            for value, label in EntryType.choices
            if value
        ],
        "stage_choices": (
            TraineeStage.objects
            .filter(is_active=True)
            .order_by("order")
        ),
        "filters": {
            "q": query,
            "entry_type": (
                entry_type_filter
            ),
            "stage": stage_filter,
            "attention": (
                attention_filter
            ),
            "status": status_filter,
        },
    }

    return render(
        request,
        "traineediary/dashboard.html",
        context,
    )


def _build_kanban_columns():
    stages = list(
        TraineeStage.objects
        .filter(is_active=True)
        .order_by("order", "id")
    )

    journeys = list(
        TraineeJourney.objects
        .select_related(
            "user",
            "current_stage",
        )
        .order_by(
            "user__last_name",
            "user__first_name",
            "user__username",
        )
    )

    sandbox_progress_by_user_id = (
        build_sandbox_queue_progress_map(
            users=[
                journey.user
                for journey in journeys
            ],
        )
    )

    cards_by_stage = {}

    for journey in journeys:
        sandbox_l1_progress = (
            sandbox_progress_by_user_id[
                journey.user_id
            ]
        )

        l1_transition_state = (
            _build_l1_transition_state(
                journey=journey,
                sandbox_progress=sandbox_l1_progress,
            )
        )

        card = {
            "journey": journey,
            "sandbox_l1_progress": (
                sandbox_l1_progress
            ),
            "l1_transition_state": (
                l1_transition_state
            ),
            "show_sandbox_progress": (
                journey.current_stage.group
                == StageGroup.SANDBOX_CANDIDATE
            ),
        }

        cards_by_stage.setdefault(
            journey.current_stage_id,
            [],
        ).append(card)

    working_columns = []
    done_column = None

    for stage in stages:
        column = {
            "stage": stage,
            "cards": cards_by_stage.get(
                stage.id,
                [],
            ),
        }

        if stage.group == StageGroup.DONE:
            done_column = column
        else:
            working_columns.append(column)

    return working_columns, done_column


@login_required
def trainees_kanban(request):
    if not request.user.is_staff:
        raise PermissionDenied

    working_columns, done_column = _build_kanban_columns()

    context = {
        "columns": working_columns,
        "done_column": done_column,
    }
    return render(request, "traineediary/trainees_kanban.html", context)


@login_required
def kanban_board_fragment(request):
    if not request.user.is_staff:
        raise PermissionDenied

    working_columns, done_column = _build_kanban_columns()

    context = {
        "columns": working_columns,
        "done_column": done_column,
    }
    return render(request, "traineediary/_kanban_board_fragment.html", context)


@login_required
def create_trainee(request):
    if not request.user.is_staff:
        raise PermissionDenied

    if request.method == "POST":
        form = NewTraineeForm(
            request.POST,
        )

        if form.is_valid():
            (
                user,
                journey,
                generated_password,
            ) = form.save(
                changed_by=request.user,
            )

            is_adaptation = journey is not None

            return render(
                request,
                (
                    "traineediary/"
                    "trainee_created.html"
                ),
                {
                    "user": user,
                    "journey": journey,
                    "password": (
                        generated_password
                    ),
                    "is_adaptation": (
                        is_adaptation
                    ),
                    "account_type_label": (
                        "Новая адаптация"
                        if is_adaptation
                        else (
                            "Сотрудник "
                            "из другого отдела"
                        )
                    ),
                },
            )
    else:
        form = NewTraineeForm()

    return render(
        request,
        "traineediary/create_trainee.html",
        {
            "form": form,
            "internal_transfer_value": (
                EntryType.INTERNAL_TRANSFER
            ),
        },
    )


@login_required
def edit_trainee(
    request,
    journey_id,
):
    if not request.user.is_staff:
        raise PermissionDenied

    journey = get_object_or_404(
        TraineeJourney.objects
        .select_related(
            "user",
            "current_stage",
        ),
        id=journey_id,
    )

    if request.method == "POST":
        form = EditTraineeForm(
            request.POST,
            journey=journey,
        )

        if form.is_valid():
            journey = form.save()

            messages.success(
                request,
                (
                    f"Карточка сотрудника "
                    f"«{journey}» обновлена."
                ),
            )

            return redirect(
                "traineediary:trainee_detail",
                journey_id=journey.id,
            )
    else:
        form = EditTraineeForm(
            journey=journey,
        )

    return render(
        request,
        "traineediary/edit_trainee.html",
        {
            "journey": journey,
            "form": form,
        },
    )


def _build_gantt_rows(journey, history_entries, today):
    """
    Готовит этапы для шкалы «план против факта».

    Для каждого применимого этапа считаются:
    - плановые min/max дни;
    - фактическое количество дней из StageHistory;
    - состояние этапа;
    - превышение максимального срока.
    """
    applicable_field = (
        "applies_to_internal_transfer"
        if journey.entry_type == EntryType.INTERNAL_TRANSFER
        else "applies_to_new_hire"
    )

    stages = (
        TraineeStage.objects
        .filter(
            is_active=True,
            **{applicable_field: True},
        )
        .exclude(group=StageGroup.DONE)
        .order_by("order")
    )

    history_by_stage = {}

    for history_entry in history_entries:
        history_by_stage.setdefault(
            history_entry.stage_id,
            [],
        ).append(history_entry)

    gantt_rows = []

    for stage in stages:
        stage_history = history_by_stage.get(stage.id, [])
        has_started = bool(stage_history)

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
                    if entry.ended_at is not None
                )

            for entry in stage_history:
                effective_end_date = entry.ended_at or today

                actual_days += max(
                    (
                        effective_end_date
                        - entry.started_at
                    ).days,
                    0,
                )

        max_days = max(stage.max_days, 1)

        actual_width_percent = (
            min(
                round(actual_days / max_days * 100),
                100,
            )
            if has_started
            else 0
        )

        min_marker_percent = min(
            round(stage.min_days / max_days * 100),
            100,
        )

        is_current = (
            journey.current_stage_id == stage.id
        )
        is_overdue = (
            has_started
            and actual_days > stage.max_days
        )

        gantt_rows.append({
            "stage": stage,
            "has_started": has_started,
            "is_current": is_current,
            "is_completed": (
                has_started
                and not is_current
                and all(
                    entry.ended_at is not None
                    for entry in stage_history
                )
            ),
            "actual_days": actual_days,
            "actual_width_percent": actual_width_percent,
            "min_marker_percent": min_marker_percent,
            "is_overdue": is_overdue,
            "overdue_days": (
                max(actual_days - stage.max_days, 0)
            ),
            "fact_started_at": fact_started_at,
            "fact_ended_at": fact_ended_at,
        })

    return gantt_rows


def _build_weekly_metric_chart(
    metrics,
    value_field,
    target,
    minimum_scale_max,
):
    """
    Готовит координаты для SVG-графика недельной метрики.

    Координаты возвращаются в диапазоне 0–100,
    поэтому график остаётся адаптивным без JavaScript.
    """
    values = []

    for metric in metrics:
        value = getattr(metric, value_field)

        if value is None:
            continue

        values.append({
            "week_number": metric.week_number,
            "value": float(value),
        })

    if not values:
        return {
            "points": [],
            "polyline": "",
            "target_y": None,
            "scale_max": minimum_scale_max,
        }

    first_week = min(
        item["week_number"]
        for item in values
    )
    last_week = max(
        item["week_number"]
        for item in values
    )
    week_span = last_week - first_week

    scale_max = max(
        float(minimum_scale_max),
        float(target),
        max(item["value"] for item in values),
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

        y = 100 - min(
            item["value"] / scale_max,
            1,
        ) * 100

        points.append({
            **item,
            "x": round(x, 2),
            "y": round(y, 2),
        })

    target_y = 100 - min(
        float(target) / scale_max,
        1,
    ) * 100

    polyline = " ".join(
        f'{point["x"]},{point["y"]}'
        for point in points
    )

    return {
        "points": points,
        "polyline": polyline,
        "target_y": round(target_y, 2),
        "scale_max": scale_max,
    }


@login_required
def trainee_detail(request, journey_id):
    if not request.user.is_staff:
        raise PermissionDenied

    history_queryset = (
        StageHistory.objects
        .select_related("stage", "changed_by")
        .order_by("-started_at", "-id")
    )

    weekly_metrics_queryset = (
        WeeklyMetric.objects
        .order_by("week_number")
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
                queryset=history_queryset,
            ),
            Prefetch(
                "weekly_metrics",
                queryset=weekly_metrics_queryset,
            ),
        ),
        id=journey_id,
    )

    sandbox_l1_progress = (
        build_sandbox_queue_progress(
            user=journey.user,
        )
    )

    l1_transition_state = (
        _build_l1_transition_state(
            journey=journey,
            sandbox_progress=sandbox_l1_progress,
        )
    )

    today = timezone.localdate()
    history_rows = []

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
        for metric in weekly_metrics_entries
        if metric.speed_hours is not None
    ]

    quality_values = [
        metric.quality_percent
        for metric in weekly_metrics_entries
        if metric.quality_percent is not None
    ]

    average_speed = None

    if speed_values:
        average_speed = (
            sum(speed_values, Decimal("0"))
            / Decimal(len(speed_values))
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
                    for value in quality_values
                )
                / Decimal(len(quality_values))
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
        "count": len(weekly_metrics_entries),
        "average_speed": average_speed,
        "average_quality": average_quality,
        "latest": latest_weekly_metric,
    }

    speed_chart = _build_weekly_metric_chart(
        metrics=weekly_metrics_entries,
        value_field="speed_hours",
        target=WEEKLY_SPEED_TARGET,
        minimum_scale_max=Decimal("8.0"),
    )

    quality_chart = _build_weekly_metric_chart(
        metrics=weekly_metrics_entries,
        value_field="quality_percent",
        target=WEEKLY_QUALITY_TARGET,
        minimum_scale_max=100,
    )

    gantt_rows = _build_gantt_rows(
        journey=journey,
        history_entries=history_entries,
        today=today,
    )

    for history_entry in history_entries:
        effective_end_date = history_entry.ended_at or today

        history_rows.append({
            "entry": history_entry,
            "is_current": history_entry.ended_at is None,
            "duration_days": max(
                (effective_end_date - history_entry.started_at).days,
                0,
            ),
        })

    probation_end_date = (
        journey.probation_start_date
        + timedelta(days=journey.probation_days_total)
    )

    context = {
        "journey": journey,
        "history_rows": history_rows,
        "gantt_rows": gantt_rows,
        "probation_end_date": probation_end_date,
        "progress_percent": journey.progress_percent,
        "risk": journey.risk_level,
        "weekly_metrics_summary": weekly_metrics_summary,
        "weekly_feedback_rows": (
            weekly_feedback_rows
        ),
        "speed_chart": speed_chart,
        "quality_chart": quality_chart,
        "weekly_speed_target": WEEKLY_SPEED_TARGET,
        "weekly_quality_target": WEEKLY_QUALITY_TARGET,
        "sandbox_l1_progress": sandbox_l1_progress,
        "l1_transition_state": l1_transition_state,
    }

    return render(
        request,
        "traineediary/trainee_detail.html",
        context,
    )


def _weekly_metric_value_state(value, target):
    if value is None:
        return "empty"

    if value >= target:
        return "success"

    return "warning"


def _get_stage_for_date(
    journey,
    history_entries,
    target_date,
):
    """
    Возвращает этап, на котором стажёр находился
    в указанную дату.
    """
    matching_entries = [
        entry
        for entry in history_entries
        if (
            entry.started_at <= target_date
            and (
                entry.ended_at is None
                or target_date < entry.ended_at
            )
        )
    ]

    if matching_entries:
        latest_entry = max(
            matching_entries,
            key=lambda entry: (
                entry.started_at,
                entry.id,
            ),
        )
        return latest_entry.stage

    # Fallback для старых записей или тестовых данных,
    # где StageHistory ещё не создан.
    if (
        journey.current_stage.group
        in TICKET_METRIC_GROUPS
        and journey.stage_started_at <= target_date
    ):
        return journey.current_stage

    return None


def _get_ticket_metrics_start_date(
    journey,
    history_entries,
):
    """
    Дата первого выхода в реальные тикеты.
    """
    ticket_stage_dates = [
        entry.started_at
        for entry in history_entries
        if (
            entry.stage.group
            in TICKET_METRIC_GROUPS
        )
    ]

    if ticket_stage_dates:
        return min(ticket_stage_dates)

    if (
        journey.current_stage.group
        in TICKET_METRIC_GROUPS
    ):
        return journey.stage_started_at

    return None


@login_required
def weekly_metrics(request):
    if not request.user.is_staff:
        raise PermissionDenied

    history_queryset = (
        StageHistory.objects
        .select_related("stage")
        .order_by("started_at", "id")
    )

    journeys = list(
        TraineeJourney.objects
        .select_related(
            "user",
            "current_stage",
        )
        .filter(
            current_stage__group__in=(
                TICKET_METRIC_GROUPS
            ),
        )
        .prefetch_related(
            "weekly_metrics",
            Prefetch(
                "stage_history",
                queryset=history_queryset,
            ),
        )
        .order_by(
            "user__last_name",
            "user__first_name",
            "user__username",
        )
    )

    prepared_rows = []
    max_week_number = 1

    for journey in journeys:
        metrics = list(
            journey.weekly_metrics.all(),
        )

        history_entries = list(
            journey.stage_history.all(),
        )

        ticket_start_date = (
            _get_ticket_metrics_start_date(
                journey=journey,
                history_entries=history_entries,
            )
        )

        if ticket_start_date is None:
            continue

        metrics_by_week = {
            metric.week_number: metric
            for metric in metrics
        }

        last_week_number = max(
            metrics_by_week,
            default=0,
        )
        next_week_number = last_week_number + 1

        max_week_number = max(
            max_week_number,
            next_week_number,
        )

        prepared_rows.append({
            "journey": journey,
            "metrics_by_week": metrics_by_week,
            "next_week_number": next_week_number,
            "ticket_start_date": ticket_start_date,
            "history_entries": history_entries,
        })

    week_numbers = list(
        range(1, max_week_number + 1),
    )

    rows = []

    for prepared_row in prepared_rows:
        journey = prepared_row["journey"]
        metrics_by_week = (
            prepared_row["metrics_by_week"]
        )
        next_week_number = (
            prepared_row["next_week_number"]
        )
        ticket_start_date = (
            prepared_row["ticket_start_date"]
        )
        history_entries = (
            prepared_row["history_entries"]
        )

        cells = []

        for week_number in week_numbers:
            metric = metrics_by_week.get(
                week_number,
            )

            is_next_week = (
                metric is None
                and week_number == next_week_number
            )

            is_editable = (
                metric is not None
                or is_next_week
            )

            if (
                metric is not None
                and metric.week_start_date is not None
            ):
                week_start_date = (
                    metric.week_start_date
                )
            else:
                week_start_date = (
                    ticket_start_date
                    + timedelta(
                        weeks=week_number - 1,
                    )
                )

            stage_for_week = _get_stage_for_date(
                journey=journey,
                history_entries=history_entries,
                target_date=week_start_date,
            )

            quality_belongs_to_week = (
                stage_for_week is not None
                and stage_for_week.group
                == StageGroup.WITH_REVIEW
            )

            # После выхода из этапа с проверками
            # старое качество больше не редактируем.
            quality_editable = (
                quality_belongs_to_week
                and journey.current_stage.group
                == StageGroup.WITH_REVIEW
                and not journey.quality_is_fixed
            )

            form = None

            if is_editable:
                form = WeeklyMetricForm(
                    instance=metric,
                    quality_required=(
                        quality_editable
                    ),
                    auto_id=(
                        f"id_metric_{journey.pk}_"
                        f"{week_number}_%s"
                    ),
                )

            cells.append({
                "week_number": week_number,
                "metric": metric,
                "form": form,
                "is_editable": is_editable,
                "is_next_week": is_next_week,
                "week_start_date": week_start_date,
                "stage_for_week": stage_for_week,
                "quality_belongs_to_week": (
                    quality_belongs_to_week
                ),
                "quality_editable": quality_editable,
                "speed_state": (
                    _weekly_metric_value_state(
                        metric.speed_hours,
                        WEEKLY_SPEED_TARGET,
                    )
                    if metric
                    else "empty"
                ),
                "quality_state": (
                    _weekly_metric_value_state(
                        metric.quality_percent,
                        WEEKLY_QUALITY_TARGET,
                    )
                    if (
                        metric
                        and metric.quality_percent
                        is not None
                    )
                    else "empty"
                ),
            })

        rows.append({
            "journey": journey,
            "cells": cells,
            "ticket_start_date": (
                ticket_start_date
            ),
        })

    return render(
        request,
        "traineediary/weekly_metrics.html",
        {
            "rows": rows,
            "week_numbers": week_numbers,
            "speed_target": WEEKLY_SPEED_TARGET,
            "quality_target": (
                WEEKLY_QUALITY_TARGET
            ),
        },
    )


@login_required
@require_POST
def save_weekly_metric(
    request,
    journey_id,
    week_number,
):
    if not request.user.is_staff:
        raise PermissionDenied

    journey = get_object_or_404(
        TraineeJourney,
        id=journey_id,
    )

    if (
    journey.current_stage.group
        not in TICKET_METRIC_GROUPS
    ):
        messages.error(
            request,
            (
                "Недельные метрики доступны только "
                "после выхода в реальные тикеты."
            ),
        )
        return redirect(
            "traineediary:weekly_metrics",
        )

    if week_number < 1:
        messages.error(
            request,
            "Номер недели должен быть больше нуля.",
        )
        return redirect(
            "traineediary:weekly_metrics",
        )

    existing_metric = (
        WeeklyMetric.objects
        .filter(
            journey=journey,
            week_number=week_number,
        )
        .first()
    )

    last_week_number = (
        journey.weekly_metrics
        .aggregate(
            max_week=Max("week_number"),
        )
        ["max_week"]
        or 0
    )

    next_week_number = last_week_number + 1

    if (
        existing_metric is None
        and week_number != next_week_number
    ):
        messages.error(
            request,
            (
                f"Нельзя добавить неделю {week_number}: "
                f"сначала заполни неделю "
                f"{next_week_number}."
            ),
        )
        return redirect(
            "traineediary:weekly_metrics",
        )

    history_entries = list(
        journey.stage_history
        .select_related("stage")
        .order_by("started_at", "id")
    )

    ticket_start_date = (
        _get_ticket_metrics_start_date(
            journey=journey,
            history_entries=history_entries,
        )
    )

    if ticket_start_date is None:
        messages.error(
            request,
            "Не удалось определить дату выхода в тикеты.",
        )
        return redirect(
            "traineediary:weekly_metrics",
        )

    week_start_date = (
        existing_metric.week_start_date
        if (
            existing_metric is not None
            and existing_metric.week_start_date
            is not None
        )
        else (
            ticket_start_date
            + timedelta(
                weeks=week_number - 1,
            )
        )
    )

    stage_for_week = _get_stage_for_date(
        journey=journey,
        history_entries=history_entries,
        target_date=week_start_date,
    )

    quality_belongs_to_week = (
        stage_for_week is not None
        and stage_for_week.group
        == StageGroup.WITH_REVIEW
    )

    quality_editable = (
        quality_belongs_to_week
        and journey.current_stage.group
        == StageGroup.WITH_REVIEW
        and not journey.quality_is_fixed
    )

    form = WeeklyMetricForm(
        request.POST,
        instance=existing_metric,
        quality_required=quality_editable,
    )

    if not form.is_valid():
        error_messages = [
            str(message)
            for errors in form.errors.values()
            for message in errors
        ]

        messages.error(
            request,
            " ".join(error_messages)
            or "Не удалось сохранить метрику.",
        )
        return redirect(
            "traineediary:weekly_metrics",
        )

    metric = form.save(commit=False)
    metric.journey = journey
    metric.week_number = week_number

    if metric.week_start_date is None:
        metric.week_start_date = week_start_date

    metric.full_clean()
    metric.save()

    messages.success(
        request,
        (
            f"{journey}: неделя "
            f"{week_number} сохранена."
        ),
    )

    return redirect(
        "traineediary:weekly_metrics",
    )


@login_required
@require_POST
def move_trainee_stage(request, journey_id):
    if not request.user.is_staff:
        raise PermissionDenied

    journey = get_object_or_404(
        TraineeJourney.objects.select_related("current_stage"),
        id=journey_id,
    )

    try:
        payload = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse(
            {"error": "Некорректный JSON в запросе."},
            status=400,
        )

    if not isinstance(payload, dict):
        return JsonResponse(
            {"error": "Некорректный формат запроса."},
            status=400,
        )

    new_stage_id = payload.get("stage_id")
    if not new_stage_id:
        return JsonResponse(
            {"error": "Не указан новый этап."},
            status=400,
        )

    transition_date_raw = payload.get("transition_date")
    note = str(payload.get("note", "")).strip()

    if transition_date_raw:
        transition_date = parse_date(str(transition_date_raw))

        if transition_date is None:
            return JsonResponse(
                {
                    "error": (
                        "Некорректная дата перехода. "
                        "Используй формат ГГГГ-ММ-ДД."
                    ),
                },
                status=400,
            )
    else:
        # Пока сохраняем совместимость со старым kanban.js.
        transition_date = timezone.localdate()

    new_stage = get_object_or_404(
        TraineeStage,
        id=new_stage_id,
        is_active=True,
    )

    try:
        previous_stage = journey.move_to_stage(
            new_stage,
            changed_by=request.user,
            note=note,
            transition_date=transition_date,
        )
    except ValidationError as exc:
        return JsonResponse(
            {"error": "; ".join(exc.messages)},
            status=400,
        )

    return JsonResponse({
        "ok": True,
        "previous_stage_id": previous_stage.id,
        "current_stage_id": journey.current_stage_id,
        "stage_started_at": journey.stage_started_at.isoformat(),
        "progress_percent": journey.progress_percent,
        "risk": journey.risk_level,
    })
