from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.decorators import (
    login_required,
)
from django.core.exceptions import (
    PermissionDenied,
)
from django.db.models import (
    Max,
    Prefetch,
)
from django.shortcuts import (
    get_object_or_404,
    redirect,
    render,
)
from django.views.decorators.http import (
    require_POST,
)

from ..constants import (
    TICKET_METRIC_GROUPS,
    WEEKLY_QUALITY_TARGET,
    WEEKLY_SPEED_TARGET,
)
from ..forms import WeeklyMetricForm
from ..models import (
    StageGroup,
    StageHistory,
    TraineeJourney,
    WeeklyMetric,
)


def _weekly_metric_value_state(
    value,
    target,
):
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
    Возвращает этап, на котором сотрудник
    находился в указанную дату.
    """
    matching_entries = [
        entry
        for entry in history_entries
        if (
            entry.started_at <= target_date
            and (
                entry.ended_at is None
                or target_date
                < entry.ended_at
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

    # Fallback для старых записей или
    # тестовых данных без StageHistory.
    if (
        journey.current_stage.group
        in TICKET_METRIC_GROUPS
        and journey.stage_started_at
        <= target_date
    ):
        return journey.current_stage

    return None


def _get_ticket_metrics_start_date(
    journey,
    history_entries,
):
    """
    Возвращает дату первого выхода
    сотрудника в реальные тикеты.
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
        return min(
            ticket_stage_dates,
        )

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
        .select_related(
            "stage",
        )
        .order_by(
            "started_at",
            "id",
        )
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
                history_entries=(
                    history_entries
                ),
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

        next_week_number = (
            last_week_number + 1
        )

        max_week_number = max(
            max_week_number,
            next_week_number,
        )

        prepared_rows.append({
            "journey": journey,
            "metrics_by_week": (
                metrics_by_week
            ),
            "next_week_number": (
                next_week_number
            ),
            "ticket_start_date": (
                ticket_start_date
            ),
            "history_entries": (
                history_entries
            ),
        })

    week_numbers = list(
        range(
            1,
            max_week_number + 1,
        ),
    )

    rows = []

    for prepared_row in prepared_rows:
        journey = prepared_row[
            "journey"
        ]

        metrics_by_week = (
            prepared_row[
                "metrics_by_week"
            ]
        )

        next_week_number = (
            prepared_row[
                "next_week_number"
            ]
        )

        ticket_start_date = (
            prepared_row[
                "ticket_start_date"
            ]
        )

        history_entries = (
            prepared_row[
                "history_entries"
            ]
        )

        cells = []

        for week_number in week_numbers:
            metric = metrics_by_week.get(
                week_number,
            )

            is_next_week = (
                metric is None
                and week_number
                == next_week_number
            )

            is_editable = (
                metric is not None
                or is_next_week
            )

            if (
                metric is not None
                and metric.week_start_date
                is not None
            ):
                week_start_date = (
                    metric.week_start_date
                )
            else:
                week_start_date = (
                    ticket_start_date
                    + timedelta(
                        weeks=(
                            week_number - 1
                        ),
                    )
                )

            stage_for_week = (
                _get_stage_for_date(
                    journey=journey,
                    history_entries=(
                        history_entries
                    ),
                    target_date=(
                        week_start_date
                    ),
                )
            )

            quality_belongs_to_week = (
                stage_for_week is not None
                and stage_for_week.group
                == StageGroup.WITH_REVIEW
            )

            # После выхода из этапа
            # с проверками старое качество
            # больше не редактируем.
            quality_editable = (
                quality_belongs_to_week
                and (
                    journey
                    .current_stage
                    .group
                    == StageGroup.WITH_REVIEW
                )
                and not (
                    journey.quality_is_fixed
                )
            )

            form = None

            if is_editable:
                form = WeeklyMetricForm(
                    instance=metric,
                    quality_required=(
                        quality_editable
                    ),
                    auto_id=(
                        f"id_metric_"
                        f"{journey.pk}_"
                        f"{week_number}_%s"
                    ),
                )

            cells.append({
                "week_number": (
                    week_number
                ),
                "metric": metric,
                "form": form,
                "is_editable": (
                    is_editable
                ),
                "is_next_week": (
                    is_next_week
                ),
                "week_start_date": (
                    week_start_date
                ),
                "stage_for_week": (
                    stage_for_week
                ),
                "quality_belongs_to_week": (
                    quality_belongs_to_week
                ),
                "quality_editable": (
                    quality_editable
                ),
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
                        and (
                            metric
                            .quality_percent
                            is not None
                        )
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
        (
            "traineediary/"
            "weekly_metrics.html"
        ),
        {
            "rows": rows,
            "week_numbers": (
                week_numbers
            ),
            "speed_target": (
                WEEKLY_SPEED_TARGET
            ),
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
        TraineeJourney.objects
        .select_related(
            "current_stage",
        ),
        id=journey_id,
    )

    if (
        journey.current_stage.group
        not in TICKET_METRIC_GROUPS
    ):
        messages.error(
            request,
            (
                "Недельные метрики доступны "
                "только после выхода "
                "в реальные тикеты."
            ),
        )

        return redirect(
            "traineediary:weekly_metrics",
        )

    if week_number < 1:
        messages.error(
            request,
            (
                "Номер недели должен "
                "быть больше нуля."
            ),
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
            max_week=Max(
                "week_number",
            ),
        )["max_week"]
        or 0
    )

    next_week_number = (
        last_week_number + 1
    )

    if (
        existing_metric is None
        and week_number
        != next_week_number
    ):
        messages.error(
            request,
            (
                f"Нельзя добавить неделю "
                f"{week_number}: сначала "
                f"заполни неделю "
                f"{next_week_number}."
            ),
        )

        return redirect(
            "traineediary:weekly_metrics",
        )

    history_entries = list(
        journey.stage_history
        .select_related(
            "stage",
        )
        .order_by(
            "started_at",
            "id",
        )
    )

    ticket_start_date = (
        _get_ticket_metrics_start_date(
            journey=journey,
            history_entries=(
                history_entries
            ),
        )
    )

    if ticket_start_date is None:
        messages.error(
            request,
            (
                "Не удалось определить "
                "дату выхода в тикеты."
            ),
        )

        return redirect(
            "traineediary:weekly_metrics",
        )

    week_start_date = (
        existing_metric.week_start_date
        if (
            existing_metric is not None
            and (
                existing_metric
                .week_start_date
                is not None
            )
        )
        else (
            ticket_start_date
            + timedelta(
                weeks=(
                    week_number - 1
                ),
            )
        )
    )

    stage_for_week = (
        _get_stage_for_date(
            journey=journey,
            history_entries=(
                history_entries
            ),
            target_date=(
                week_start_date
            ),
        )
    )

    quality_belongs_to_week = (
        stage_for_week is not None
        and stage_for_week.group
        == StageGroup.WITH_REVIEW
    )

    quality_editable = (
        quality_belongs_to_week
        and (
            journey.current_stage.group
            == StageGroup.WITH_REVIEW
        )
        and not journey.quality_is_fixed
    )

    form = WeeklyMetricForm(
        request.POST,
        instance=existing_metric,
        quality_required=(
            quality_editable
        ),
    )

    if not form.is_valid():
        error_messages = [
            str(
                message,
            )
            for errors
            in form.errors.values()
            for message in errors
        ]

        messages.error(
            request,
            (
                " ".join(
                    error_messages,
                )
                or (
                    "Не удалось сохранить "
                    "метрику."
                )
            ),
        )

        return redirect(
            "traineediary:weekly_metrics",
        )

    metric = form.save(
        commit=False,
    )

    metric.journey = journey
    metric.week_number = week_number

    if metric.week_start_date is None:
        metric.week_start_date = (
            week_start_date
        )

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
