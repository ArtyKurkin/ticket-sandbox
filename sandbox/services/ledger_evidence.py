"""SELECT-only Ledger provider: no grants, no restored attempts, no raw texts in DTO."""

from sandbox.models import TaskAttempt, CheckRun, SandboxProgramCompletion
from sandbox.ledger_models import (
    SandboxLedgerBoundary,
    SandboxProgramManifest,
    SandboxAttemptCoverage,
    SandboxEvidenceGap,
    TechnicalCheckExecution,
    SandboxEnvironmentEvent,
    SandboxAnswerSubmission,
)
from sandbox.services.technical_evidence import get_technical_evidence, with_technical_evidence
from collections import defaultdict


def _load(attempts, attempt_ids):
    """Request-scoped batch; the same checks/DTO serve single and program reads."""
    ids = list(attempt_ids)
    data = {"attempts": {a.pk: a for a in attempts},
            "coverage": {c.attempt_id: c for c in SandboxAttemptCoverage.objects.filter(attempt_id__in=ids)}}
    queries = {
        "gaps": SandboxEvidenceGap.objects.filter(attempt_id__in=ids),
        "checks": TechnicalCheckExecution.objects.filter(attempt_id__in=ids).prefetch_related("events").order_by("ordinal"),
        "environment": SandboxEnvironmentEvent.objects.filter(attempt_id__in=ids).order_by("pk"),
        "submissions": SandboxAnswerSubmission.objects.filter(attempt_id__in=ids).prefetch_related("reviews").order_by("ordinal"),
        "runs": CheckRun.objects.filter(attempt_id__in=ids).only("id", "attempt_id", "exit_code", "result"),
    }
    for name, rows in queries.items():
        data[name] = defaultdict(list)
        for row in rows:
            data[name][row.attempt_id].append(row)
    return data


def attempt_evidence(attempt_id):
    attempts = list(with_technical_evidence(TaskAttempt.objects.select_related("task", "task__queue").filter(pk=attempt_id)))
    return _attempt_evidence(attempt_id, _load(attempts, [attempt_id]))


def _attempt_evidence(attempt_id, data):
    attempt = data["attempts"].get(attempt_id)
    coverage = data["coverage"].get(attempt_id)
    reasons = []
    if attempt is None:
        reasons.append("attempt_details_missing")
    if coverage is None or coverage.origin != "creation":
        reasons.append("history_not_recorded_from_creation")
    if (
        coverage
        and attempt
        and (
            (coverage.user_id, coverage.task_id, coverage.attempt_number)
            != (attempt.user_id, attempt.task_id, attempt.attempt_number)
        )
    ):
        reasons.append("identity_mismatch")
    gaps = [g.reason for g in data["gaps"][attempt_id]]
    if gaps:
        reasons.append("ledger_gap")
    checks = data["checks"][attempt_id]
    technical = []
    runs = {}
    for execution in checks:
        finish = next(
            (e for e in execution.events.all() if e.phase == "finished"), None
        )
        if (
            finish
            and finish.checker_started
            and (not any((e.phase == "started" for e in execution.events.all())))
        ):
            reasons.append("check_start_missing")
        if coverage and (
            execution.user_id,
            execution.task_id,
            execution.attempt_number,
        ) != (coverage.user_id, coverage.task_id, coverage.attempt_number):
            reasons.append("identity_mismatch")
        technical.append(
            {
                "run_id": str(execution.run_id),
                "ordinal": execution.ordinal,
                "requested_at": execution.requested_at.isoformat(),
                "finished_at": finish.occurred_at.isoformat() if finish else None,
                "result": finish.result if finish else "unknown",
                "failure_class": finish.failure_class if finish else "unknown",
                "checker_started": finish.checker_started if finish else None,
                "check_run_id": finish.check_run_id if finish else None,
                "reason": finish.reason if finish else "execution_pending",
            }
        )
        if not finish:
            reasons.append("execution_pending")
        elif finish.result == "unknown" and (
            not (
                finish.failure_class == "infrastructure"
                and finish.checker_started is False
            )
        ):
            reasons.append("check_outcome_unknown")
        if finish and finish.check_run_id:
            runs[finish.check_run_id] = finish
        if execution.source != "service":
            reasons.append("unregistered_execution")
    if [e.ordinal for e in checks] != list(range(1, len(checks) + 1)):
        reasons.append("check_ordinals_missing")
    environment = data["environment"][attempt_id]
    requests = [e for e in environment if e.phase == "requested"]
    ends = {e.operation_id: e for e in environment if e.phase == "finished"}
    resets = 0
    all_resets = 0
    for request in requests:
        if coverage and (request.user_id, request.task_id, request.attempt_number) != (
            coverage.user_id,
            coverage.task_id,
            coverage.attempt_number,
        ):
            reasons.append("identity_mismatch")
        if request.origin == "unknown":
            reasons.append("environment_origin_unknown")
        if request.origin == "trainee" and request.actor_id != request.user_id:
            reasons.append("reset_actor_mismatch")
        end = ends.get(request.operation_id)
        if not end:
            reasons.append("environment_pending")
        elif end.outcome == "unknown":
            reasons.append("environment_outcome_unknown")
        if request.kind == "reset":
            if request.origin == "unknown":
                reasons.append("reset_origin_unknown")
            if end and end.outcome == "success":
                all_resets += 1
                if request.origin == "trainee" and request.attempt_number == 1:
                    resets += 1
    submissions = data["submissions"][attempt_id]
    answers = []
    returns = 0
    for submission in submissions:
        if coverage and (
            submission.user_id,
            submission.task_id,
            submission.attempt_number,
        ) != (coverage.user_id, coverage.task_id, coverage.attempt_number):
            reasons.append("identity_mismatch")
        reviews = sorted(submission.reviews.all(), key=lambda e: e.pk)
        for index, event in enumerate(reviews):
            expected = reviews[index - 1].pk if index else None
            if event.supersedes_id != expected or event.kind != (
                "correction" if index else "decision"
            ):
                reasons.append("review_chain_invalid")
        last = reviews[-1] if reviews else None
        count = bool(last and last.decision == "needs_revision")
        returns += count
        answers.append(
            {
                "submission_id": submission.pk,
                "ordinal": submission.ordinal,
                "submitted_at": submission.submitted_at.isoformat(),
                "digest": submission.digest,
                "decision": last.decision if last else "not_reviewed",
                "review_ids": [e.pk for e in reviews],
                "reviewed_at": last.reviewed_at.isoformat() if last else None,
                "valid_return": count,
            }
        )
    if [s.ordinal for s in submissions] != list(range(1, len(submissions) + 1)):
        reasons.append("submission_ordinals_missing")
    if attempt:
        if get_technical_evidence(attempt).is_completed and (
            not any((e["result"] == "passed" for e in technical))
        ):
            reasons.append("technical_evidence_outside_ledger")
        initial = coverage.initial_counts if coverage else {"checks": 0, "resets": 0}
        if attempt.attempts_count != len(checks) + initial["checks"]:
            reasons.append("check_count_mismatch")
        if attempt.restart_count != all_resets + initial["resets"]:
            reasons.append("reset_count_mismatch")
        actual_runs = {
            r.pk: r
            for r in data["runs"][attempt_id]
        }
        if set(actual_runs) != set(runs):
            reasons.append("check_run_details_mismatch")
        for pk, fact in runs.items():
            raw = actual_runs.get(pk)
            if raw and (
                raw.exit_code != fact.exit_code
                or raw.result != ("passed" if fact.result == "passed" else "failed")
            ):
                reasons.append("check_run_mutated")
        if submissions and attempt.status in ["on_review", "passed"]:
            latest = submissions[-1]
            if (latest.client_answer.strip(), latest.trainee_report.strip()) != (
                attempt.client_answer,
                attempt.trainee_report,
            ):
                reasons.append("submitted_text_mismatch")
            reviews = sorted(latest.reviews.all(), key=lambda e: e.pk)
            if attempt.mentor_decision != (
                reviews[-1].decision if reviews else "not_reviewed"
            ):
                reasons.append("review_projection_mismatch")
    physical = [e for e in technical if e["checker_started"] is True]
    first = physical[0] if physical else None
    axes = source_axes(reasons, gaps)
    return {
        "attempt_id": attempt_id,
        "credit": (
            coverage.attempt_number == 1
            if coverage
            else attempt.attempt_number == 1 if attempt else None
        ),
        "coverage": {
            "status": "unknown" if reasons else "complete",
            "ledger_version": coverage.ledger_version if coverage else None,
            "origin": coverage.origin if coverage else None,
            "recorded_at": coverage.recorded_at.isoformat() if coverage else None,
            "reasons": sorted(set(reasons)),
            "sources": axes,
        },
        "successful_resets": resets if axes["resets"]["status"] == "complete" else None,
        "observed_successful_resets": resets,
        "technical_checks": technical,
        "first_check": first if axes["checks"]["status"] == "complete" else None,
        "observed_first_check": first,
        "submissions": answers,
        "valid_returns": returns if axes["answers"]["status"] == "complete" else None,
        "first_answer_approved": (
            bool(len(answers) == 1 and answers[0]["decision"] == "approved")
            if axes["answers"]["status"] == "complete"
            else None
        ),
        "technical_completed": (
            get_technical_evidence(attempt).is_completed if attempt else None
        ),
    }


def program_evidence(user_id, program_key="l1"):
    manifest = SandboxProgramManifest.objects.filter(
        user_id=user_id, program_key=program_key
    ).first()
    completion = SandboxProgramCompletion.objects.filter(
        user_id=user_id, program_key=program_key
    ).first()
    reasons = []
    if not manifest:
        reasons.append("manifest_missing")
    elif manifest.source != "from_start":
        reasons.append("requirements_not_frozen_from_start")
    entries = []
    if manifest:
        from sandbox.services.ledger import digest

        snapshot = manifest.snapshot
        if (
            not isinstance(snapshot, dict)
            or snapshot.get("schema_version") != 1
            or manifest.requirements_version != 1
            or not isinstance(snapshot.get("tasks"), list)
            or digest(snapshot) != manifest.digest
        ):
            reasons.append("manifest_invalid_or_unknown_version")
        else:
            entries = snapshot["tasks"]
        if not entries:
            reasons.append("manifest_empty")
    ids = [e["task_id"] for e in entries]
    if completion and set(ids) != {e["task_id"] for e in completion.snapshot["tasks"]}:
        reasons.append("completion_manifest_composition_mismatch")
    credit = list(with_technical_evidence(TaskAttempt.objects.select_related("task", "task__queue").filter(
        user_id=user_id, task_id__in=ids, attempt_number=1)))
    by_task = {a.task_id: a for a in credit}
    data = _load(credit, [a.pk for a in credit])
    attempts = []
    for entry in entries:
        attempt = by_task.get(entry["task_id"])
        if not attempt:
            reasons.append("credit_attempt_missing")
            continue
        if completion and any(
            (
                e["task_id"] == entry["task_id"] and e["attempt_id"] != attempt.pk
                for e in completion.snapshot["tasks"]
            )
        ):
            reasons.append("completion_attempt_identity_mismatch")
        evidence = _attempt_evidence(attempt.pk, data)
        attempts.append(
            {
                "task_id": entry["task_id"],
                "requires_review": entry["requires_review"],
                **evidence,
            }
        )
        reasons.extend(evidence["coverage"]["reasons"])
        if entry["requires_review"] is None:
            reasons.append("answer_requirement_unknown")
        if entry["criteria_digest"] is None:
            reasons.append("criteria_version_unknown")
        if any(c.criteria_digest != entry["criteria_digest"] for c in data["checks"][attempt.pk]):
            reasons.append("criteria_version_changed")
    first_answers = sorted(
        [
            {"task_id": a["task_id"], **a["submissions"][0]}
            for a in attempts
            if a["requires_review"] and a["submissions"]
        ],
        key=lambda e: (e["submitted_at"], e["submission_id"]),
    )[:5]
    common = [
        r
        for r in reasons
        if r.startswith(("manifest_", "requirements_", "completion_", "credit_"))
    ]
    axes = {}
    for name in ["checks", "resets", "answers"]:
        bad = common[:]
        if name == "checks":
            bad += [r for r in reasons if r.startswith("criteria_")]
        if name == "answers":
            bad += [r for r in reasons if r.startswith("answer_requirement_")]
        for evidence in attempts:
            if name == "answers" and evidence["requires_review"] is False:
                continue
            if evidence["coverage"]["sources"][name]["status"] == "unknown":
                bad.extend(evidence["coverage"]["sources"][name]["reasons"])
        axes[name] = {
            "status": "unknown" if bad else "complete",
            "reasons": sorted(set(bad)),
        }
    boundary = SandboxLedgerBoundary.objects.filter(pk=1).first()
    return {
        "user_id": user_id,
        "program_key": program_key,
        "ledger_enabled_at": boundary.enabled_at.isoformat() if boundary else None,
        "manifest": (
            {
                "id": manifest.pk,
                "digest": manifest.digest,
                "source": manifest.source,
                "recorded_at": manifest.recorded_at.isoformat(),
                **manifest.snapshot,
            }
            if manifest
            else None
        ),
        "completion_id": completion.pk if completion else None,
        "coverage": {
            "status": "unknown" if reasons else "complete",
            "reasons": sorted(set(reasons)),
            "sources": axes,
        },
        "attempts": attempts,
        "successful_resets": (
            sum((a["observed_successful_resets"] for a in attempts))
            if axes["resets"]["status"] == "complete"
            else None
        ),
        "valid_returns": (
            sum((a["valid_returns"] or 0 for a in attempts if a["requires_review"]))
            if axes["answers"]["status"] == "complete"
            else None
        ),
        "first_five_answers": (
            first_answers if axes["answers"]["status"] == "complete" else None
        ),
        "observed_first_answers": first_answers,
        "all_required_answers_approved": (
            all(
                (
                    a["submissions"] and a["submissions"][-1]["decision"] == "approved"
                    for a in attempts
                    if a["requires_review"]
                )
            )
            if entries and (not reasons)
            else None
        ),
    }


def source_axes(reasons, gaps=()):
    """Keep confidence for independent reset/check/answer conditions explicit."""
    check_prefixes = (
        "check_",
        "execution_",
        "technical_",
        "unregistered_check",
        "unregistered_execution",
    )
    reset_prefixes = (
        "reset_",
        "environment_",
        "legacy_environment_",
        "unregistered_environment_",
    )
    answer_prefixes = ("review_", "submission_", "submitted_")
    common = [
        r
        for r in reasons
        if r != "ledger_gap"
        and (not r.startswith(check_prefixes + reset_prefixes + answer_prefixes))
    ]
    for gap_reason in gaps:
        if not gap_reason.startswith(check_prefixes + reset_prefixes + answer_prefixes):
            common.append(gap_reason)
    result = {}
    for name, prefixes in [
        ("checks", check_prefixes),
        ("resets", reset_prefixes),
        ("answers", answer_prefixes),
    ]:
        bad = common + [r for r in [*reasons, *gaps] if r.startswith(prefixes)]
        result[name] = {
            "status": "unknown" if bad else "complete",
            "reasons": sorted(set(bad)),
        }
    return result
