from django.utils import timezone
from traineediary.models import CompletionStatus, StageGroup
from .base import Evaluation, at_date, eligible, history_for, unknown


def probation(journey, tiers):
    if journey.completion_status == CompletionStatus.TERMINATED:
        return Evaluation("not_met", reason="probation_terminated")
    if journey.completion_status != CompletionStatus.SUCCESS:
        return Evaluation("not_met", reason="no_successful_completion")
    completed = journey.completed_at
    if (completed is None or completed < journey.probation_start_date or completed > timezone.localdate()
            or journey.current_stage.group != StageGroup.DONE or journey.stage_started_at != completed
            or not journey.completed_by_id or not journey.completed_by.is_staff
            or history_for(journey) is None):
        return unknown("unconfirmed_or_inconsistent_completion", "valid actual dates", "staff-confirmed SUCCESS", "consistent DONE visit")
    day = (completed - journey.probation_start_date).days + 1
    matches = [t for t in tiers if day >= t.parameters["min_day"] and day <= t.parameters.get("max_day", day)]
    tier = max(matches, key=lambda t: t.rank)
    return eligible(tier, {"journey_id": journey.pk, "start_date": journey.probation_start_date.isoformat(),
                           "completion_date": completed.isoformat(), "day_number": day,
                           "confirmed_by_id": journey.completed_by_id, "status": "success"},
                    {"journey_id": journey.pk}, at_date(completed))
