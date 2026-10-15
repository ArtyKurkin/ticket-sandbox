from dataclasses import dataclass, field
from datetime import datetime, time
from django.utils import timezone
from traineediary.services.stages import stage_applies


@dataclass(frozen=True)
class Evaluation:
    status: str
    tier_code: str | None = None
    reason: str = ""
    required: tuple = ()
    evidence: dict = field(default_factory=dict)
    context: dict = field(default_factory=dict)
    occurred_at: datetime | None = None
    rule_version: int = 1

    def report(self):
        return dict(status=self.status, tier=self.tier_code, reason=self.reason,
                    required=list(self.required), evidence=self.evidence, context=self.context,
                    occurred_at=self.occurred_at.isoformat() if self.occurred_at else None,
                    rule_version=self.rule_version)

def at_date(date):
    return timezone.make_aware(datetime.combine(date, time.min))

def unknown(reason, *required):
    return Evaluation("unknown", reason=reason, required=required)

def eligible(tier, evidence, context, occurred_at):
    return Evaluation("eligible", tier_code=tier.code, evidence=evidence, context=context,
                      occurred_at=occurred_at, rule_version=tier.rule_version)

def history_for(journey):
    """Require a continuous, applicable chain and agreement with the current card.

    Zero-day visits are allowed; they cannot cover any measurement period.
    Authors are required for transition awards, not initial visit creation.
    """
    visits = list(journey.stage_history.select_related("stage", "changed_by").order_by("started_at", "id"))
    today = timezone.localdate()
    if not visits or journey.probation_start_date > today:
        return None
    for i, visit in enumerate(visits):
        if (visit.started_at < journey.probation_start_date or visit.started_at > today
                or not stage_applies(visit.stage, journey.stage_scheme, journey.entry_type)):
            return None
        if visit.ended_at is not None and (visit.ended_at < visit.started_at or visit.ended_at > today):
            return None
        if i < len(visits) - 1:
            if visit.ended_at != visits[i + 1].started_at:
                return None
        elif (visit.ended_at is not None or visit.stage_id != journey.current_stage_id
              or visit.started_at != journey.stage_started_at):
            return None
    return visits
