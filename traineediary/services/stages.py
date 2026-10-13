"""One catalog policy for selection, calculations and historical display."""

from django.db.models import Q

from ..models import EntryType, StageScheme, StageScope, TraineeStage


UNIFIED_LABELS = {
    "sandbox-candidate": "Задания в Ticket Sandbox",
    "optional-review": "Проверки по желанию",
}


def stage_label(stage, scheme):
    if scheme == StageScheme.UNIFIED:
        return UNIFIED_LABELS.get(stage.slug, stage.name)
    return stage.name


def stage_applies(stage, scheme, entry_type):
    return (
        scheme in StageScheme.values
        and stage.catalog_scope in (scheme, StageScope.SHARED)
        and stage.applies_to_entry_type(entry_type)
    )


def selectable_stages(scheme, entry_type):
    """Active transition targets; historical/current exceptions never become targets."""
    if scheme not in StageScheme.values or entry_type not in EntryType.values:
        return TraineeStage.objects.none()
    field = (
        "applies_to_internal_transfer"
        if entry_type == EntryType.INTERNAL_TRANSFER
        else "applies_to_new_hire"
    )
    return TraineeStage.objects.filter(
        catalog_scope__in=(scheme, StageScope.SHARED),
        is_active=True,
        **{field: True},
    ).order_by("order", "id")


def journey_stages(journey, *, include_current=False, history_entries=None):
    """Scheme catalog plus actual records for display, even if later deactivated."""
    selected = selectable_stages(journey.stage_scheme, journey.entry_type)
    extra_ids = set()
    if include_current:
        extra_ids.add(journey.current_stage_id)
    if history_entries is not None:
        extra_ids.update(entry.stage_id for entry in history_entries)
    return TraineeStage.objects.filter(
        Q(pk__in=selected.values("pk")) | Q(pk__in=extra_ids),
    ).order_by("order", "id")


def next_stage(journey):
    stage = (
        selectable_stages(journey.stage_scheme, journey.entry_type)
        .filter(
            order__gt=journey.current_stage.order,
        )
        .first()
    )
    if stage is not None:
        stage.display_name = stage_label(stage, journey.stage_scheme)
    return stage


def board_stages(scheme, journeys):
    """Both entry types on a board; retain every actual current stage."""
    selected = selectable_stages(scheme, EntryType.NEW_HIRE).values("pk")
    internal = selectable_stages(scheme, EntryType.INTERNAL_TRANSFER).values("pk")
    return TraineeStage.objects.filter(
        Q(pk__in=selected)
        | Q(pk__in=internal)
        | Q(pk__in=[journey.current_stage_id for journey in journeys]),
    ).order_by("order", "id")
