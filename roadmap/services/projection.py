"""Read-only adapters. No transitions, backfill or completion writes."""
from dataclasses import asdict
from django.utils import timezone
from sandbox.services.progress import build_sandbox_queue_progress
from traineediary.models import CompletionStatus, EntryType, StageGroup
from traineediary.services.assessment import build_readiness_summary
from traineediary.services.stages import stage_applies
from .registry import MODULES, REQUIREMENTS_V1
from .actions import attach_actions

WORK_SLUGS = {"with-review": "with_review", "optional-review": "optional_review", "no-review": "no_review"}
SUCCESSORS = {"with-review": "optional-review", "optional-review": "no-review", "no-review": "done"}


def _probation(journey):
    if journey.current_stage.group != StageGroup.DONE:
        return "active" if not journey.completion_status else "insufficient_data"
    if not (journey.completed_at and journey.completed_by_id
            and journey.probation_start_date <= journey.completed_at <= timezone.localdate()
            and journey.stage_started_at == journey.completed_at):
        return "insufficient_data"
    if journey.completion_status == CompletionStatus.SUCCESS:
        return "success"
    if journey.completion_status == CompletionStatus.TERMINATED and journey.completion_comment.strip():
        return "terminated"
    return "insufficient_data"


def _working_evidence(journey, history, outcome):
    problems = []
    today = timezone.localdate()
    valid = bool(history)
    for index, row in enumerate(history):
        if (row.started_at < journey.probation_start_date or row.started_at > today
                or not stage_applies(row.stage, journey.stage_scheme, journey.entry_type)):
            valid = False
        if index < len(history) - 1:
            following = history[index + 1]
            if row.ended_at != following.started_at or row.started_at > following.started_at:
                valid = False
        elif (row.stage_id != journey.current_stage_id or row.ended_at is not None
              or row.started_at != journey.stage_started_at):
            valid = False
    if not valid:
        problems.append({"code": "ambiguous_stage_history", "description": "История неполна или не согласована с текущим этапом; завершения не засчитаны."})
    evidence = {}
    for slug, code in WORK_SLUGS.items():
        visits = [(i, row) for i, row in enumerate(history) if row.stage.slug == slug]
        completed = False
        reason = "no_completion_evidence"
        transition_id = None
        if visits and valid:
            index, row = visits[-1]  # A return invalidates the earlier completion.
            if index + 1 < len(history):
                following = history[index + 1]
                sequential = following.stage.slug == SUCCESSORS[slug]
                staff = following.changed_by is not None and following.changed_by.is_staff
                terminal_ok = slug != "no-review" or outcome == "success"
                completed = sequential and staff and terminal_ok
                reason = "staff_sequential_transition" if completed else "unproven_or_nonsequential_transition"
                transition_id = following.pk
        evidence[code] = {"completed": completed, "code": reason, "transition_id": transition_id}
        if journey.current_stage.slug != slug and not completed:
            problems.append({"code": "unproven_stage_completion", "stage": code, "description": "Нет доказательства последовательного успешного завершения этапа."})
    return evidence, problems


def build_roadmap(journey, *, viewer=None):
    internal = journey is not None and journey.entry_type == EntryType.INTERNAL_TRANSFER
    stages = []
    for order, module in enumerate(MODULES, 1):
        applicable = journey is not None and module.code in REQUIREMENTS_V1 and not (internal and order <= 2)
        display = "coming_soon" if module.availability == "coming_soon" else ("not_required" if internal and order <= 2 else "locked")
        stages.append({
            "id": module.code, "order": order, "title": module.title,
            "availability": module.availability, "applicable": applicable,
            "state": "locked" if applicable else None, "display_status": display,
            "source": module.source, "description": module.description, "actions": [],
            **({"badge": "COMING SOON"} if module.availability == "coming_soon" else {}),
        })
    by_code = {row["id"]: row for row in stages}
    problems = []
    journey_data = {"state": "not_started", "entry_type": None, "scheme": None, "id": None}
    adaptation_progress = None
    if journey is not None:
        outcome = _probation(journey)
        history = list(journey.stage_history.select_related("stage", "changed_by").order_by("started_at", "id"))
        working, problems = _working_evidence(journey, history, outcome)
        journey_data = {
            "id": journey.pk, "state": outcome, "entry_type": journey.entry_type,
            "scheme": journey.stage_scheme, "current_stage": {
                "id": journey.current_stage_id, "slug": journey.current_stage.slug,
                "title": journey.current_stage_label, "started_at": journey.stage_started_at,
            }, "probation_outcome": outcome,
            "completed_at": journey.completed_at,
        }
        adaptation_progress = journey.progress_percent
        latest = journey.roadmap_confirmation_events.order_by("-id").first()
        training = by_code["training"]
        training["evidence"] = {
            "event_id": latest.pk if latest else None,
            "action": latest.action if latest else None,
            "recorded_at": latest.created_at if latest else None,
            "actor_id": latest.actor_id if latest else None,
        }
        if training["applicable"] and latest is None:
            problems.append({
                "code": "training_confirmation_missing", "stage": "training",
                "description": "Нет отдельного подтверждения обучения; позиция в дневнике не доказывает его завершение.",
            })
        if training["applicable"]:
            training["state"] = "completed" if latest and latest.action == "confirmed" else "available"
            if training["state"] != "completed" and journey.current_stage.group == StageGroup.TEACHBASE:
                training["state"] = "in_progress"
        sandbox = build_sandbox_queue_progress(journey.user)
        sb = by_code["sandbox"]
        sb["progress"] = {"completed": sandbox.technical_completed_count, "total": sandbox.total_count, "unit": "tasks", "basis": "technical", "scope": "current_catalog"}
        sb["completion"] = {"id": sandbox.completion_id, "completed_at": sandbox.completed_at, "task_ids": list(sandbox.completion_task_ids), "total": len(sandbox.completion_task_ids)}
        sb["notifications"] = [
            {"code": code, "count": count, "blocking": False}
            for code, count in (
                ("text_revision_required", sandbox.needs_revision_count),
                ("text_waiting_for_review", sandbox.on_review_count),
                ("text_answer_not_submitted", sandbox.unsubmitted_count),
                ("unread_mentor_feedback", sandbox.unread_feedback_count),
            )
        ]
        sb["data_quality"] = [asdict(item) for item in sandbox.diagnostics]
        if sb["applicable"]:
            if sandbox.is_completed:
                sb["state"] = "completed"
            elif sandbox.passed_count or journey.current_stage.group == StageGroup.SANDBOX_L1:
                sb["state"] = "in_progress"
            elif training["state"] == "completed":
                sb["state"] = "available"
        for code, evidence in working.items():
            by_code[code]["evidence"] = evidence
            if evidence["completed"]:
                by_code[code]["state"] = "completed"
        current_code = WORK_SLUGS.get(journey.current_stage.slug)
        if current_code:
            by_code[current_code]["state"] = "in_progress"
        # Future modules are not prerequisites. Existing position remains truthful.
        if internal or sb["state"] == "completed":
            if by_code["with_review"]["state"] == "locked":
                by_code["with_review"]["state"] = "available"
        for previous, following in (("with_review", "optional_review"), ("optional_review", "no_review"), ("no_review", "probation")):
            if by_code[previous]["state"] == "completed" and by_code[following]["state"] == "locked":
                by_code[following]["state"] = "available"
        if outcome == "success":
            by_code["probation"]["state"] = "completed"
        elif outcome == "active":
            by_code["probation"]["state"] = "in_progress"
        else:
            by_code["probation"]["state"] = "locked"
        by_code["probation"]["evidence"] = {"outcome": outcome}
        if outcome == "insufficient_data":
            problems.append({"code": "probation_evidence_missing", "description": "Подтверждённый результат ИС отсутствует или неполон."})
        readiness = build_readiness_summary(journey, sandbox_progress=sandbox)
        if current_code:
            by_code[current_code]["readiness"] = {
                "state": readiness.state, "label": readiness.label,
                "reasons": [asdict(reason) for reason in readiness.reasons],
                "next_stage_id": readiness.next_stage.pk if readiness.next_stage else None,
            }
        journey_data["metrics"] = [
            {"week_number": metric.week_number, "week_start_date": metric.week_start_date,
             "speed_tickets_per_hour": metric.speed_hours, "quality_percent": metric.quality_percent}
            for metric in journey.weekly_metrics.order_by("week_number")
        ]
        journey_data["fixed_quality_percent"] = journey.fixed_quality_percent
        for code in WORK_SLUGS.values():
            by_code[code]["periods"] = [
                {"history_id": row.pk, "started_at": row.started_at, "ended_at": row.ended_at,
                 "duration_days": max(0, ((row.ended_at or journey.completed_at or timezone.localdate()) - row.started_at).days)}
                for row in history if WORK_SLUGS.get(row.stage.slug) == code
            ]
    for row in stages:
        if row["applicable"]:
            row["display_status"] = row["state"]
    attach_actions(stages, journey=journey, viewer=viewer)
    count = sum(row["state"] == "completed" and row["applicable"] and row["availability"] == "enabled" for row in stages)
    total = sum(row["applicable"] and row["availability"] == "enabled" for row in stages)
    return {
        "schema_version": 1, "requirements_version": 1, "journey": journey_data,
        "overall": {"completed_count": count, "applicable_count": total, "exempt_count": 0,
                    "percent": round(count / total * 100, 1) if total else 0,
                    "adaptation_progress_percent": adaptation_progress},
        "stages": stages, "data_quality": problems,
    }
