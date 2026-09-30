from collections import Counter

from sandbox.ai_review_constants import AI_REVIEW_CHECK_LABELS
from sandbox.models import AIReview


def _comparison_counts():
    return {
        "comparisons": 0,
        "agreement": 0,
        "false_critical": 0,
        "missed_revision": 0,
    }


def _with_percentages(counts):
    total = counts["comparisons"]
    return {
        **counts,
        **{
            f"{key}_percent": counts[key] * 100 / total if total else None
            for key in ("agreement", "false_critical", "missed_revision")
        },
    }


def build_ai_review_stats_context():
    """Compare answer snapshots, independently of the current attempt state."""
    approved = AIReview.MentorDecision.APPROVED
    needs_revision = AIReview.MentorDecision.NEEDS_REVISION
    stats = {"total": 0, "completed": 0, **_comparison_counts()}
    matrix = {
        approved: {approved: 0, needs_revision: 0},
        needs_revision: {approved: 0, needs_revision: 0},
    }
    criteria = {
        key: {
            "label": label, "critical": 0, "minor": 0, "ok": 0,
            "false_critical": 0,
        }
        for key, label in AI_REVIEW_CHECK_LABELS.items()
    }
    prompts = {}
    models = Counter()
    recent = []

    # Read only the fields needed for statistics; answers and raw AI responses
    # can be large. Ordering also defines the most recent snapshot disagreements.
    reviews = AIReview.objects.order_by("-created_at", "-id").values(
        "id", "status", "checks", "mentor_decision", "prompt_version", "model",
    )
    for review in reviews.iterator():
        stats["total"] += 1
        models[(review["model"] or "").strip()] += 1
        if review["status"] != AIReview.Status.COMPLETED:
            continue

        stats["completed"] += 1
        checks = review["checks"]
        critical_keys = [
            key for key, check in checks.items()
            if check.get("severity") == "critical"
        ]
        for key, criterion in criteria.items():
            severity = checks.get(key, {}).get("severity")
            if severity in ("critical", "minor", "ok"):
                criterion[severity] += 1

        mentor_decision = review["mentor_decision"]
        if mentor_decision not in (approved, needs_revision):
            continue

        ai_decision = needs_revision if critical_keys else approved
        matrix[ai_decision][mentor_decision] += 1
        if ai_decision == mentor_decision:
            outcome = "agreement"
        elif critical_keys:
            outcome = "false_critical"
            for key in critical_keys:
                if key in criteria:
                    criteria[key]["false_critical"] += 1
        else:
            outcome = "missed_revision"

        version = (review["prompt_version"] or "").strip()
        prompt = prompts.setdefault(version, _comparison_counts())
        for counts in (stats, prompt):
            counts["comparisons"] += 1
            counts[outcome] += 1

        if outcome != "agreement" and len(recent) < 10:
            recent.append({
                "id": review["id"],
                "ai_decision": ai_decision,
                "critical_labels": [
                    AI_REVIEW_CHECK_LABELS.get(key, key) for key in critical_keys
                ],
            })

    # Load ticket/trainee details only for the ten displayed snapshots, in one
    # query. Never consult TaskAttempt.mentor_decision for historical comparisons.
    recent_reviews = {
        review.pk: review
        for review in AIReview.objects.filter(
            pk__in=[item["id"] for item in recent],
        ).select_related("attempt__task", "attempt__user").only(
            "id", "created_at", "mentor_decision", "attempt__id",
            "attempt__task__title", "attempt__user__username",
        )
    }
    for item in recent:
        item["review"] = recent_reviews[item["id"]]

    return {
        "stats": _with_percentages(stats),
        "matrix": matrix,
        "criteria": list(criteria.values()),
        "false_critical_criteria": sorted(
            criteria.values(), key=lambda item: -item["false_critical"],
        ),
        "prompt_stats": [
            {"version": version, **_with_percentages(counts)}
            for version, counts in sorted(prompts.items())
        ],
        "model_stats": [
            {"model": model, "count": count}
            for model, count in sorted(models.items())
        ],
        "recent_disagreements": recent,
    }
