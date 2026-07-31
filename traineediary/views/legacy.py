from decimal import Decimal

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import render
from django.urls import reverse
from django.db.models import Prefetch, Q

from ..models import (
    CompletionStatus,
    EntryType,
    StageGroup,
    TraineeJourney,
    TraineeStage,
    WeeklyMetric,
)
from ..services.sandbox_progress import (
    build_sandbox_queue_progress_map,
)
from ..services.assessment import (
    build_trainee_assessment,
)
from ..constants import (
    TICKET_METRIC_GROUPS,
)


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

    completion_filter = request.GET.get(
        "completion",
        "",
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

    valid_completion_filters = {
        "",
        CompletionStatus.SUCCESS,
        CompletionStatus.TERMINATED,
        "missing",
    }

    if (
        completion_filter
        not in valid_completion_filters
    ):
        completion_filter = ""

    stage_id = None

    if stage_filter:
        try:
            stage_id = int(
                stage_filter,
            )
        except (
            TypeError,
            ValueError,
        ):
            stage_filter = ""

    weekly_metrics_queryset = (
        WeeklyMetric.objects
        .order_by(
            "week_number",
        )
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
                queryset=(
                    weekly_metrics_queryset
                ),
            ),
        )
    )

    if status_filter == "active":
        journeys_queryset = (
            journeys_queryset.exclude(
                current_stage__group=(
                    StageGroup.DONE
                ),
            )
        )

    elif status_filter == "completed":
        journeys_queryset = (
            journeys_queryset.filter(
                current_stage__group=(
                    StageGroup.DONE
                ),
            )
        )

    if query:
        journeys_queryset = (
            journeys_queryset.filter(
                Q(
                    user__first_name__icontains=(
                        query
                    ),
                )
                | Q(
                    user__last_name__icontains=(
                        query
                    ),
                )
                | Q(
                    user__username__icontains=(
                        query
                    ),
                )
            )
        )

    if entry_type_filter:
        journeys_queryset = (
            journeys_queryset.filter(
                entry_type=(
                    entry_type_filter
                ),
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
            queue_slug="l1",
        )
    )

    ready_to_transition_count = 0
    needs_attention_count = 0

    completion_counts = {
        CompletionStatus.SUCCESS: 0,
        CompletionStatus.TERMINATED: 0,
        "missing": 0,
    }

    group_counts = {}
    rows = []
    filtered_journeys = []

    for journey in journeys:
        sandbox_l1_progress = (
            sandbox_progress_by_user_id[
                journey.user_id
            ]
        )

        assessment = (
            build_trainee_assessment(
                journey,
                sandbox_progress=(
                    sandbox_l1_progress
                ),
            )
        )

        if (
            attention_filter == "1"
            and not (
                assessment
                .requires_attention
            )
        ):
            continue

        if (
            attention_filter == "0"
            and assessment.requires_attention
        ):
            continue

        group = journey.current_stage.group

        completion_bucket = None

        if group == StageGroup.DONE:
            if (
                journey.completion_status
                == CompletionStatus.SUCCESS
            ):
                completion_bucket = (
                    CompletionStatus.SUCCESS
                )

            elif (
                journey.completion_status
                == CompletionStatus.TERMINATED
            ):
                completion_bucket = (
                    CompletionStatus.TERMINATED
                )

            else:
                completion_bucket = "missing"

            completion_counts[
                completion_bucket
            ] += 1

        if (
            completion_filter
            and completion_bucket
            != completion_filter
        ):
            continue

        group_counts[group] = (
            group_counts.get(
                group,
                0,
            )
            + 1
        )

        if assessment.readiness.is_ready:
            ready_to_transition_count += 1

        if assessment.requires_attention:
            needs_attention_count += 1

        filtered_journeys.append(
            journey,
        )

        rows.append({
            "journey": journey,
            "assessment": assessment,
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
        })

    if status_filter == "completed":
        summary_groups = [
            choice
            for choice in StageGroup.choices
            if (
                choice[0]
                == StageGroup.DONE
            )
        ]

    elif status_filter == "all":
        summary_groups = list(
            StageGroup.choices,
        )

    else:
        summary_groups = [
            choice
            for choice in StageGroup.choices
            if (
                choice[0]
                != StageGroup.DONE
            )
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

    completion_card_definitions = [
        {
            "value": "",
            "label": "Всего завершено",
            "count": sum(
                completion_counts.values(),
            ),
            "tone": "",
        },
        {
            "value": CompletionStatus.SUCCESS,
            "label": "Успешно завершили",
            "count": completion_counts[
                CompletionStatus.SUCCESS
            ],
            "tone": "success",
        },
        {
            "value": (
                CompletionStatus.TERMINATED
            ),
            "label": "ИС прекращён",
            "count": completion_counts[
                CompletionStatus.TERMINATED
            ],
            "tone": "danger",
        },
        {
            "value": "missing",
            "label": "Без результата",
            "count": completion_counts[
                "missing"
            ],
            "tone": "muted",
        },
    ]

    completion_summary_cards = []

    for card in completion_card_definitions:
        query_params = request.GET.copy()

        query_params["status"] = "completed"

        if card["value"]:
            query_params["completion"] = (
                card["value"]
            )
        else:
            query_params.pop(
                "completion",
                None,
            )

        completion_summary_cards.append({
            **card,
            "is_active": (
                completion_filter
                == card["value"]
            ),
            "url": (
                reverse(
                    "traineediary:dashboard",
                )
                + "?"
                + query_params.urlencode()
            ),
        })

    context = {
        "rows": rows,
        "filtered_count": len(
            rows,
        ),
        "summary_cards": (
            summary_cards
        ),
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
            (
                value,
                label,
            )
            for value, label
            in EntryType.choices
            if value
        ],
        "stage_choices": (
            TraineeStage.objects
            .filter(
                is_active=True,
            )
            .order_by(
                "order",
            )
        ),
        "completion_summary_cards": (
            completion_summary_cards
        ),
        "completion_filter_choices": [
            (
                CompletionStatus.SUCCESS,
                "Успешно завершили",
            ),
            (
                CompletionStatus.TERMINATED,
                "ИС прекращён",
            ),
            (
                "missing",
                "Без результата",
            ),
        ],
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
            "completion": completion_filter,
        },
    }

    return render(
        request,
        "traineediary/dashboard.html",
        context,
    )
