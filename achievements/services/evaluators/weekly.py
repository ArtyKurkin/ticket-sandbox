from datetime import timedelta
from decimal import Decimal
from django.utils import timezone
from traineediary.models import StageGroup
from .base import Evaluation, at_date, eligible, history_for, unknown


def weekly(journey, tiers, definition):
    visits = history_for(journey)
    if visits is None:
        return unknown("ambiguous_stage_history", "continuous stage visits consistent with journey")
    quality = definition.evaluator_key == "review_quality"
    field_name = "quality_percent" if quality else "speed_hours"
    group = StageGroup.WITH_REVIEW if quality else StageGroup.NO_REVIEW
    best = None
    ambiguous = False
    for metric in journey.weekly_metrics.order_by("week_number", "id"):
        value = getattr(metric, field_name)
        start = metric.week_start_date
        if start is None:
            ambiguous = True
            continue
        end = start + timedelta(days=7)
        if end > timezone.localdate():
            ambiguous = True
            continue
        covering = [v for v in visits if v.started_at <= start and (v.ended_at is None or v.ended_at >= end)]
        if len(covering) != 1:
            ambiguous = True
            continue
        visit = covering[0]
        if visit.stage.group != group:
            continue
        if value is None:
            ambiguous = True
            continue
        number = Decimal(str(value))
        if not number.is_finite() or number < 0 or (quality and number > 100):
            ambiguous = True
            continue
        matches = [t for t in tiers if t.parameters["automatic"] and
                   (number > Decimal(t.parameters["minimum"]) if t.parameters["strict"]
                    else number >= Decimal(t.parameters["minimum"]))]
        if not matches:
            continue
        tier = max(matches, key=lambda t: t.rank)
        if best is None or tier.rank > best[0].rank or (tier.rank == best[0].rank and number > best[1]):
            best = (tier, number, metric, visit, start, end)
    if best:
        tier, value, metric, visit, start, end = best
        return eligible(tier, {"metric_id": metric.pk, "week_number": metric.week_number,
                               field_name: str(value), "period_start": start.isoformat(), "period_end": end.isoformat(),
                               "stage_history_id": visit.pk, "stage_id": visit.stage_id, "stage_group": group},
                        {"journey_id": journey.pk, "visit_id": visit.pk}, at_date(end))
    if ambiguous:
        return unknown("missing_or_ambiguous_week", "dated finished seven-day period", "single applicable stage visit", field_name)
    return Evaluation("not_met", reason="no_qualifying_week_in_required_stage")
