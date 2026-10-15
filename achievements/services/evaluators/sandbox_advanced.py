"""Independent v1 conditions over the public SELECT-only Ledger DTO.

Platinum is assessed but never activated: repository digests do not attest the
checker executed in a trainee-controlled container.
"""
from datetime import datetime
from django.utils import timezone

POLICY = "sandbox-ledger-v1"
PLATINUM_TRUST_REASON = "runtime_checker_integrity_unproven"


def state(status, *reasons):
    return {"status": status, "reasons": sorted(set(reasons))}


def assess(proof):
    manifest = proof.get("manifest")
    if not manifest or manifest.get("source") != "from_start":
        missing = state("unknown", "requirements_not_frozen_from_start")
        return {code: missing.copy() for code in ("silver", "gold", "platinum", "clean_answers")}
    timestamps = [manifest["recorded_at"]]
    timestamps += [s["submitted_at"] for a in proof["attempts"] for s in a["submissions"]]
    timestamps += [s["reviewed_at"] for a in proof["attempts"] for s in a["submissions"] if s.get("reviewed_at")]
    timestamps += [c["finished_at"] or c["requested_at"] for a in proof["attempts"] for c in a["technical_checks"]]
    if any(timezone.is_naive(datetime.fromisoformat(t)) or datetime.fromisoformat(t) > timezone.now() for t in timestamps):
        return {code: state("unknown", "future_or_naive_evidence_time") for code in ("silver", "gold", "platinum", "clean_answers")}
    attempts = proof["attempts"]
    axes = proof["coverage"]["sources"]

    def coverage(*names):
        reasons = [r for name in names if axes[name]["status"] != "complete" for r in axes[name]["reasons"]]
        return state("unknown", *reasons) if reasons else None

    def technical():
        # Completion identity/composition is checked by the provider, independently
        # of the current Task catalogue. Never infer completeness from empty rows.
        if not attempts or len(attempts) != len(manifest["tasks"]):
            return state("unknown", "credit_attempt_missing")
        if any(a["technical_completed"] is None for a in attempts):
            return state("unknown", "technical_evidence_missing")
        if not all(a["credit"] and a["technical_completed"] for a in attempts):
            return state("not_met", "technical_program_incomplete")
        # A positive mutable projection / raw CheckRun alone is not an advanced
        # completion. Unknown earlier checks may coexist with a genuine later pass.
        for attempt in attempts:
            if not any(c["result"] == "passed" and c["checker_started"] is True and c["check_run_id"]
                       for c in attempt["technical_checks"]):
                return state("unknown", "technical_success_not_registered")
            conflicts = {"check_run_mutated", "check_run_details_mismatch", "technical_evidence_outside_ledger"}
            reasons = conflicts.intersection(attempt["coverage"]["reasons"])
            if reasons:
                return state("unknown", *reasons)
        return None

    silver = coverage("resets") or technical()
    if silver is None:
        resets = proof["successful_resets"]
        silver = state("unknown", "reset_count_unknown") if resets is None else state(
            "eligible" if resets <= 2 else "not_met", *([] if resets <= 2 else ["too_many_resets"]))
    gold = coverage("resets", "answers") or technical()
    required = [a for a in attempts if a["requires_review"]]
    if gold is None:
        if proof["successful_resets"] is None or proof["valid_returns"] is None:
            gold = state("unknown", "answer_or_reset_count_unknown")
        elif proof["successful_resets"] > 2 or proof["valid_returns"] > 2:
            gold = state("not_met", "reset_or_revision_limit_exceeded")
        elif any(not a["submissions"] or a["submissions"][-1]["decision"] != "approved" for a in required):
            gold = state("not_met", "required_answers_not_approved")
        else:
            gold = state("eligible")
    platinum = coverage("checks", "resets", "answers") or technical()
    if platinum is None:
        if proof["successful_resets"] != 0:
            platinum = state("not_met", "trainee_reset")
        elif any(not a["first_answer_approved"] for a in required):
            platinum = state("not_met", "first_submission_not_approved")
        elif any(a["first_check"] is None for a in attempts):
            platinum = state("unknown", "first_real_check_unknown")
        elif any(a["first_check"]["result"] != "passed" for a in attempts):
            platinum = state("not_met", "first_real_check_failed")
        else:
            platinum = state("unknown", PLATINUM_TRUST_REASON)
    clean = coverage("answers")
    if clean is None:
        if len(required) < 5:
            clean = state("not_met", "fewer_than_five_required_answers")
        else:
            first = proof["first_five_answers"]
            if first is None:
                clean = state("unknown", "first_answers_order_unknown")
            elif len(first) < 5:
                clean = state("not_met", "fewer_than_five_submitted_answers")
            elif any(s["decision"] != "approved" or s["ordinal"] != 1 for s in first):
                clean = state("not_met", "first_five_not_clean")
            else:
                clean = state("eligible")
    return dict(silver=silver, gold=gold, platinum=platinum, clean_answers=clean)


def snapshot(proof):
    """Compact, private proof references: never copy answer text or comments."""
    return {"policy": POLICY, "manifest_id": proof["manifest"]["id"],
            "manifest_digest": proof["manifest"]["digest"], "completion_id": proof["completion_id"],
            "successful_resets": proof["successful_resets"], "valid_returns": proof["valid_returns"],
            "attempts": [{k: a[k] for k in ("task_id", "attempt_id", "requires_review", "technical_completed", "first_check", "submissions")}
                         for a in proof["attempts"]]}


def proof_time(proof):
    times = [proof["manifest"]["recorded_at"]]
    times += [s["submitted_at"] for a in proof["attempts"] for s in a["submissions"]]
    times += [s["reviewed_at"] for a in proof["attempts"] for s in a["submissions"] if s.get("reviewed_at")]
    times += [c["finished_at"] or c["requested_at"] for a in proof["attempts"] for c in a["technical_checks"]]
    return max(datetime.fromisoformat(t) for t in times)
