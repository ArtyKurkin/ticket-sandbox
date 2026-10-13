import json

from django.contrib.auth.decorators import (
    login_required,
)
from django.core.exceptions import (
    PermissionDenied,
    ValidationError,
)
from django.db.models import Prefetch
from django.http import JsonResponse
from django.shortcuts import (
    get_object_or_404,
    render,
)
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.views.decorators.http import (
    require_POST,
)

from ..models import (
    StageGroup,
    StageScheme,
    TraineeJourney,
    TraineeStage,
    WeeklyMetric,
)
from ..queries import (
    get_pre_adaptation_users_queryset,
)
from ..services.assessment import (
    build_trainee_assessment,
)
from ..services.sandbox_progress import (
    build_sandbox_queue_progress_map,
)

from ..services.stages import board_stages, selectable_stages, stage_label


def _build_kanban_boards():
    weekly_metrics_queryset = (
        WeeklyMetric.objects
        .order_by(
            "week_number",
        )
    )

    journeys = list(
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
            queue_slug="l1",
        )
    )

    cards_by_stage = {}

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

        card = {
            "journey": journey,
            "assessment": assessment,
            "sandbox_l1_progress": (
                sandbox_l1_progress
            ),
            "show_sandbox_progress": (
                journey.current_stage.group
                == StageGroup.SANDBOX_L1
            ),
        }

        cards_by_stage.setdefault(
            (journey.stage_scheme, journey.current_stage_id),
            [],
        ).append(
            card,
        )

    boards = []
    for scheme, label in StageScheme.choices:
        scheme_journeys = [j for j in journeys if j.stage_scheme == scheme]
        if scheme == StageScheme.LEGACY and not scheme_journeys:
            continue
        columns = []
        done_columns = []
        for stage in board_stages(scheme, scheme_journeys):
            stage.display_name = stage_label(stage, scheme)
            column = {
                "stage": stage,
                "cards": cards_by_stage.get((scheme, stage.id), []),
            }
            if stage.group == StageGroup.DONE:
                done_columns.append(column)
            else:
                columns.append(column)
        boards.append({
            "scheme": scheme, "label": label,
            "columns": columns, "done_columns": done_columns,
        })
    return boards


def _kanban_context():
    boards = _build_kanban_boards()
    done_columns = [column for board in boards for column in board["done_columns"]]
    return {
        "boards": boards,
        "columns": [column for board in boards for column in board["columns"]],
        "done_column": done_columns[-1] if done_columns else None,
    }


@login_required
def trainees_kanban(request):
    if not request.user.is_staff:
        raise PermissionDenied

    context = _kanban_context()
    context["pre_adaptation_count"] = get_pre_adaptation_users_queryset().count()

    return render(
        request,
        "traineediary/trainees_kanban.html",
        context,
    )


@login_required
def kanban_board_fragment(request):
    if not request.user.is_staff:
        raise PermissionDenied

    context = _kanban_context()

    return render(
        request,
        (
            "traineediary/"
            "_kanban_board_fragment.html"
        ),
        context,
    )


@login_required
@require_POST
def move_trainee_stage(
    request,
    journey_id,
):
    if not request.user.is_staff:
        raise PermissionDenied

    journey = get_object_or_404(
        TraineeJourney.objects.select_related(
            "current_stage",
        ),
        id=journey_id,
    )

    try:
        payload = json.loads(
            request.body,
        )
    except json.JSONDecodeError:
        return JsonResponse(
            {
                "error": (
                    "Некорректный JSON "
                    "в запросе."
                ),
            },
            status=400,
        )

    if not isinstance(
        payload,
        dict,
    ):
        return JsonResponse(
            {
                "error": (
                    "Некорректный формат "
                    "запроса."
                ),
            },
            status=400,
        )

    new_stage_id = payload.get(
        "stage_id",
    )

    if not new_stage_id:
        return JsonResponse(
            {
                "error": (
                    "Не указан новый этап."
                ),
            },
            status=400,
        )

    transition_date_raw = payload.get(
        "transition_date",
    )

    note = str(
        payload.get(
            "note",
            "",
        ),
    ).strip()

    if transition_date_raw:
        transition_date = parse_date(
            str(
                transition_date_raw,
            ),
        )

        if transition_date is None:
            return JsonResponse(
                {
                    "error": (
                        "Некорректная дата перехода. "
                        "Используй формат "
                        "ГГГГ-ММ-ДД."
                    ),
                },
                status=400,
            )
    else:
        # Сохраняем совместимость со старыми
        # клиентами, которые могли не присылать
        # дату перехода.
        transition_date = (
            timezone.localdate()
        )

    new_stage = get_object_or_404(
        TraineeStage,
        id=new_stage_id,
        is_active=True,
    )

    if journey.completion_status:
        return JsonResponse(
            {
                "error": (
                    "Испытательный срок сотрудника "
                    "уже завершён."
                ),
                "code": (
                    "probation_completed"
                ),
            },
            status=400,
        )

    if not selectable_stages(journey.stage_scheme, journey.entry_type).filter(
        pk=new_stage.pk,
    ).exists():
        return JsonResponse(
            {"error": "Этот этап не разрешён для схемы и типа входа сотрудника."},
            status=400,
        )

    if new_stage.group == StageGroup.DONE:
        return JsonResponse(
            {
                "error": (
                    "Для выхода с испытательного "
                    "срока необходимо заполнить "
                    "результат завершения."
                ),
                "code": (
                    "completion_required"
                ),
                "redirect_url": reverse(
                    (
                        "traineediary:"
                        "complete_trainee"
                    ),
                    args=[
                        journey.id,
                    ],
                ),
            },
            status=409,
        )

    try:
        previous_stage = (
            journey.move_to_stage(
                new_stage,
                changed_by=request.user,
                note=note,
                transition_date=(
                    transition_date
                ),
            )
        )
    except ValidationError as error:
        return JsonResponse(
            {
                "error": "; ".join(
                    error.messages,
                ),
            },
            status=400,
        )

    return JsonResponse({
        "ok": True,
        "previous_stage_id": (
            previous_stage.id
        ),
        "current_stage_id": (
            journey.current_stage_id
        ),
        "stage_started_at": (
            journey
            .stage_started_at
            .isoformat()
        ),
        "progress_percent": (
            journey.progress_percent
        ),
        "risk": journey.risk_level,
    })
