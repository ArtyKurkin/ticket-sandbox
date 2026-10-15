from datetime import datetime
from django.core.exceptions import ValidationError
from django.utils import timezone
from .base import Evaluation, eligible, unknown


def sandbox(user_id, tiers, definition, evidence_cache=None):
    from sandbox.models import SandboxProgramCompletion, TaskAttempt
    from sandbox.services.completions import validate_completion_snapshot
    from sandbox.services.technical_evidence import get_technical_evidence, with_technical_evidence
    completion = SandboxProgramCompletion.objects.filter(user_id=user_id, program_key="l1").first()
    snapshot_tasks = []
    if completion:
        try:
            validate_completion_snapshot(completion)
        except ValidationError:
            return unknown("invalid_completion_snapshot", "valid frozen program evidence")
        if completion.completed_at > timezone.now():
            return unknown("future_completion", "valid completed_at")
        snapshot_tasks = completion.snapshot["tasks"]
        linked = {a.pk: a for a in TaskAttempt.objects.filter(pk__in=[e["attempt_id"] for e in snapshot_tasks])}
        for entry in snapshot_tasks:
            attempt = linked.get(entry["attempt_id"])
            if attempt and (attempt.user_id != user_id or attempt.task_id != entry["task_id"] or attempt.attempt_number != 1):
                return unknown("completion_identity_mismatch", "frozen credit evidence for the correct owner/task")
    context = {"program_key": "l1"}
    if definition.evaluator_key in ("sandbox_program", "sandbox_first_five_clean_answers"):
        from sandbox.services.ledger_evidence import program_evidence
        from .sandbox_advanced import assess, snapshot, proof_time
        cache = evidence_cache if evidence_cache is not None else {}
        if user_id not in cache:
            cache[user_id] = program_evidence(user_id)
        proof = cache[user_id]
        levels = assess(proof)
        context["levels"] = levels
        if definition.evaluator_key == "sandbox_first_five_clean_answers":
            result = levels["clean_answers"]
            if result["status"] == "eligible":
                return eligible(tiers[0], snapshot(proof), context, proof_time(proof))
            return Evaluation(result["status"], reason=";".join(result["reasons"]),
                              required=tuple(result["reasons"]), context=context)
        for code in ("gold", "silver"):
            if levels[code]["status"] == "eligible":
                tier = next(t for t in tiers if t.code == code)
                return eligible(tier, snapshot(proof), context, proof_time(proof))
        if not completion:
            return Evaluation("not_met",
                              reason="no_saved_completion", context=context)
        return eligible(tiers[0], {"completion_id": completion.pk, "source": completion.source,
                                  "fingerprint": completion.composition_fingerprint,
                                  "task_ids": [e["task_id"] for e in snapshot_tasks]}, context, completion.completed_at)
    successes = {e["task_id"]: {"task_id": e["task_id"], "attempt_id": e["attempt_id"],
                               "passed_at": e["passed_at"], "completion_id": completion.pk}
                 for e in snapshot_tasks}
    # Credit rows remain credit when a practice attempt becomes current.
    attempts = with_technical_evidence(TaskAttempt.objects.filter(user_id=user_id, attempt_number=1, task__queue__slug="l1"))
    for attempt in attempts:
        proof = get_technical_evidence(attempt)
        if proof.is_completed and proof.passed_at and proof.passed_at <= timezone.now():
            candidate = {"task_id": attempt.task_id, "attempt_id": attempt.pk,
                         "check_run_id": proof.check_run_id, "passed_at": proof.passed_at.isoformat()}
            previous = successes.get(attempt.task_id)
            if previous is None or datetime.fromisoformat(previous["passed_at"]) > proof.passed_at:
                successes[attempt.task_id] = candidate
    required = tiers[0].parameters["task_count"]
    ordered = sorted(successes.values(), key=lambda e: (datetime.fromisoformat(e["passed_at"]), e["task_id"]))
    if len(ordered) < required:
        return Evaluation("not_met", reason="insufficient_credit_successes")
    proofs = ordered[:required]
    return eligible(tiers[0], {"distinct_task_count": len(proofs), "tasks": proofs}, context,
                    datetime.fromisoformat(proofs[-1]["passed_at"]))
