import json

from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_POST

from .forms import NewTraineeForm
from .models import StageGroup, TraineeJourney, TraineeStage


@login_required
def dashboard(request):
    if not request.user.is_staff:
        raise PermissionDenied

    journeys = (
        TraineeJourney.objects
        .select_related("user", "current_stage")
        .exclude(current_stage__group=StageGroup.DONE)
        .order_by("current_stage__order", "user__last_name")
    )

    group_counts = {}
    needs_attention_count = 0
    rows = []

    for journey in journeys:
        group = journey.current_stage.group
        group_counts[group] = group_counts.get(group, 0) + 1

        risk = journey.risk_level
        if risk == "high":
            needs_attention_count += 1

        rows.append({
            "journey": journey,
            "risk": risk,
            "progress_percent": journey.progress_percent,
            "days_total": journey.days_total,
            "days_left": journey.days_left_until_probation_end,
            "expected_transition": journey.expected_stage_transition_date,
        })

    summary_cards = [
        {"label": label, "count": group_counts.get(value, 0)}
        for value, label in StageGroup.choices
        if value != StageGroup.DONE
    ]

    context = {
        "rows": rows,
        "summary_cards": summary_cards,
        "needs_attention_count": needs_attention_count,
    }
    return render(request, "traineediary/dashboard.html", context)


def _build_kanban_columns():
    stages = TraineeStage.objects.filter(is_active=True).order_by("order")
    journeys = (
        TraineeJourney.objects
        .select_related("user", "current_stage")
        .order_by("user__last_name")
    )

    journeys_by_stage = {}
    for journey in journeys:
        journeys_by_stage.setdefault(journey.current_stage_id, []).append(journey)

    working_columns = []
    done_column = None

    for stage in stages:
        column = {"stage": stage, "journeys": journeys_by_stage.get(stage.id, [])}
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
        form = NewTraineeForm(request.POST)
        if form.is_valid():
            journey, generated_password = form.save()
            return render(
                request,
                "traineediary/trainee_created.html",
                {"journey": journey, "password": generated_password},
            )
    else:
        form = NewTraineeForm()

    return render(request, "traineediary/create_trainee.html", {"form": form})


@login_required
@require_POST
def move_trainee_stage(request, journey_id):
    if not request.user.is_staff:
        raise PermissionDenied

    journey = get_object_or_404(TraineeJourney, id=journey_id)

    try:
        payload = json.loads(request.body)
        new_stage_id = payload["stage_id"]
    except (ValueError, KeyError):
        return JsonResponse({"error": "Некорректный запрос."}, status=400)

    new_stage = get_object_or_404(TraineeStage, id=new_stage_id)

    try:
        journey.move_to_stage(new_stage, changed_by=request.user)
    except ValidationError as exc:
        return JsonResponse({"error": "; ".join(exc.messages)}, status=400)

    return JsonResponse({
        "ok": True,
        "progress_percent": journey.progress_percent,
        "risk": journey.risk_level,
    })
