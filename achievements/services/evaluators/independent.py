from traineediary.models import StageGroup
from .base import Evaluation, at_date, eligible, history_for, unknown


def independent(journey, tiers):
    visits = history_for(journey)
    if visits is None:
        return unknown("ambiguous_stage_history", "continuous confirmed OPTIONAL_REVIEW → NO_REVIEW")
    for previous, current in zip(visits, visits[1:]):
        if previous.stage.group == StageGroup.OPTIONAL_REVIEW and current.stage.group == StageGroup.NO_REVIEW:
            if current.changed_by_id and current.changed_by.is_staff:
                return eligible(tiers[0], {"from_visit_id": previous.pk, "to_visit_id": current.pk,
                                          "confirmed_by_id": current.changed_by_id},
                                {"journey_id": journey.pk}, at_date(current.started_at))
            return unknown("transition_actor_missing", "staff-confirmed transition")
    return Evaluation("not_met", reason="no_normal_confirmed_transition")
