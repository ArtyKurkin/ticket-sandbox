#!/usr/bin/env python3
"""Standalone audit for the deployed d4aa79c schema; never imports Django.

Run via stdin in Web with python -B -. Uses only its existing DB_* environment.
Every data query runs in a single PostgreSQL REPEATABLE READ, READ ONLY snapshot.
Output is aggregate JSON: no user IDs, names, individual dates or comment text.
"""
from collections import Counter, defaultdict
from datetime import date, datetime, timezone
from decimal import Decimal
from hashlib import sha256
import json
import os
import sys


VERSION = 1
SOURCE_REVISION = "d4aa79c0e4fa5e49cc98e0a27e40319fb7e49a29"
THEORY = frozenset({"first-day", "vds", "managed-services", "client-service", "before-tickets"})
SHARED = frozenset({"sandbox-candidate", "with-review", "optional-review", "no-review", "done"})
MAPPING = {**{s: "training-program" for s in THEORY}, **{s: s for s in SHARED}}
SCHEMES = frozenset({"legacy", "unified"})
ENTRIES = frozenset({"new_hire", "internal_transfer"})
OUTCOMES = frozenset({"", "success", "terminated"})
CATALOG_FIELDS = (
    "order", "min_days", "max_days", "progress_weight_percent", "group",
    "applies_to_new_hire", "applies_to_internal_transfer", "catalog_scope",
)
# Frozen from migration 0007, including the complete confirmed historical profile.
DEFAULT_CATALOG = {
    "first-day": (1, 1, 1, 3, "teachbase", True, False, "legacy"),
    "vds": (2, 5, 7, 15, "teachbase", True, False, "legacy"),
    "managed-services": (3, 2, 3, 8, "teachbase", True, False, "legacy"),
    "client-service": (4, 1, 2, 5, "teachbase", True, False, "legacy"),
    "before-tickets": (6, 1, 1, 4, "teachbase", True, False, "legacy"),
    "sandbox-candidate": (5, 1, 2, 5, "sandbox_candidate", True, False, "shared"),
    "with-review": (7, 15, 20, 35, "with_review", True, True, "shared"),
    "optional-review": (8, 5, 10, 10, "optional_review", True, True, "shared"),
    "no-review": (9, 10, 10, 15, "no_review", True, True, "shared"),
    "done": (10, 0, 0, 0, "done", True, True, "shared"),
    "training-program": (1, 10, 14, 35, "teachbase", True, False, "unified"),
}
CONFIRMED_CATALOG = {
    **DEFAULT_CATALOG,
    "before-tickets": (5, 1, 1, 4, "teachbase", True, False, "legacy"),
    "managed-services": (3, 2, 4, 8, "teachbase", True, False, "legacy"),
    "client-service": (4, 1, 3, 5, "teachbase", True, False, "legacy"),
    "sandbox-candidate": (6, 1, 3, 5, "sandbox_candidate", True, False, "shared"),
    "with-review": (7, 28, 35, 35, "with_review", True, True, "shared"),
    "optional-review": (8, 10, 14, 10, "optional_review", True, True, "shared"),
    "no-review": (9, 10, 14, 15, "no_review", True, True, "shared"),
}

# Static projections deliberately omit auth names, emails, credentials and tokens.
# Full diary rows are needed to fingerprint all original fields, including text.
QUERIES = {
    "stages": "SELECT id, name, slug, \"order\", min_days, max_days, progress_weight_percent, color, \"group\", is_active, catalog_scope, applies_to_new_hire, applies_to_internal_transfer FROM traineediary_traineestage ORDER BY id",
    "journeys": "SELECT id, user_id, entry_type, stage_scheme, probation_start_date, current_stage_id, stage_started_at, comment, manual_risk_override, fixed_quality_percent, quality_fixed_at, completion_status, completed_at, completion_comment, completed_by_id FROM traineediary_traineejourney ORDER BY id",
    "history": "SELECT id, journey_id, stage_id, started_at, ended_at, changed_by_id, note FROM traineediary_stagehistory ORDER BY id",
    "metrics": "SELECT id, journey_id, week_number, week_start_date, speed_hours, quality_percent, mentor_comment, next_week_goal FROM traineediary_weeklymetric ORDER BY id",
    "roadmap": "SELECT id, journey_id, actor_id, stage_code, action, created_at, comment FROM roadmap_trainingconfirmationevent ORDER BY id",
    "user_links": "SELECT id, is_staff FROM auth_user ORDER BY id",
    "migrations": "SELECT app, name FROM django_migrations WHERE app IN ('traineediary', 'roadmap') ORDER BY app, name",
}


def canonical(value):
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat()
    if isinstance(value, (date, Decimal)):
        return str(value)
    raise TypeError("Unsupported audit value")


def fingerprint(value):
    return sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                             separators=(",", ":"), default=canonical).encode()).hexdigest()


def allowed(value, choices):
    """Never echo unknown strings from the database into an aggregate label."""
    return value if value in choices else "__unknown__"


def distribution(rows, fields, choices):
    counts = Counter(tuple(allowed(row[f], choices[f]) for f in fields) for row in rows)
    return [{**dict(zip(fields, key)), "count": n} for key, n in sorted(counts.items())]


def progress(journey, stages, scheme, today, current=None):
    current = current or stages[journey["current_stage_id"]]
    if current["group"] == "done":
        return 100
    applicable_field = "applies_to_internal_transfer" if journey["entry_type"] == "internal_transfer" else "applies_to_new_hire"
    selected = [s for s in stages.values() if s["id"] == current["id"] or (
        s["is_active"] and s[applicable_field] and s["catalog_scope"] in (scheme, "shared")
    )]
    total = sum(s["progress_weight_percent"] for s in selected) or 1
    before = sum(s["progress_weight_percent"] for s in selected if s["order"] < current["order"])
    days = max((today - journey["stage_started_at"]).days, 0)
    fraction = min(days / max(current["max_days"], 1), 1)
    return round((before + current["progress_weight_percent"] * fraction) / total * 100)


def probation_outcome(journey, current, today):
    """Matches Roadmap's conservative probation evidence check at d4aa79c."""
    if current["group"] != "done":
        return "active" if not journey["completion_status"] else "insufficient_data"
    if not (journey["completed_at"] and journey["completed_by_id"]
            and journey["probation_start_date"] <= journey["completed_at"] <= today
            and journey["stage_started_at"] == journey["completed_at"]):
        return "insufficient_data"
    if journey["completion_status"] == "success":
        return "success"
    if journey["completion_status"] == "terminated" and journey["completion_comment"].strip():
        return "terminated"
    return "insufficient_data"


def working_completions(journey, history, stages, users, today):
    """Read-only equivalent of the three work-stage Roadmap evidence rules."""
    current = stages.get(journey["current_stage_id"])
    valid = bool(history) and current is not None
    for index, row in enumerate(history):
        stage = stages.get(row["stage_id"])
        field = "applies_to_internal_transfer" if journey["entry_type"] == "internal_transfer" else "applies_to_new_hire"
        if (not stage or not stage[field] or stage["catalog_scope"] not in (journey["stage_scheme"], "shared")
                or not journey["probation_start_date"] <= row["started_at"] <= today):
            valid = False
        if index < len(history) - 1:
            following = history[index + 1]
            if row["ended_at"] != following["started_at"] or row["started_at"] > following["started_at"]:
                valid = False
        elif (row["stage_id"] != journey["current_stage_id"] or row["ended_at"] is not None
              or row["started_at"] != journey["stage_started_at"]):
            valid = False
    completed = set()
    if not valid:
        return completed, False
    successors = {"with-review": "optional-review", "optional-review": "no-review", "no-review": "done"}
    for slug, successor in successors.items():
        visits = [i for i, row in enumerate(history) if stages[row["stage_id"]]["slug"] == slug]
        if not visits or visits[-1] + 1 >= len(history):
            continue
        following = history[visits[-1] + 1]
        actor = users.get(following["changed_by_id"])
        if (stages[following["stage_id"]]["slug"] == successor and actor and actor["is_staff"]
                and (slug != "no-review" or probation_outcome(journey, current, today) == "success")):
            completed.add(slug)
    return completed, True


def build_report(data, today, transaction_state):
    stages = {s["id"]: s for s in data["stages"]}
    by_slug = {s["slug"]: s for s in stages.values()}
    journeys = {j["id"]: j for j in data["journeys"]}
    users = {u["id"]: u for u in data["user_links"]}
    histories, metrics, confirmations = defaultdict(list), defaultdict(list), defaultdict(list)
    issues = defaultdict(set)
    issue_rows = Counter()
    warnings = defaultdict(set)
    global_blockers = Counter()
    profile = "unsupported"
    for name, expected in (("default", DEFAULT_CATALOG), ("confirmed_2026_10_30", CONFIRMED_CATALOG)):
        if set(by_slug) == set(expected) and all(tuple(by_slug[s][f] for f in CATALOG_FIELDS) == spec for s, spec in expected.items()):
            profile = name
            break
    if profile == "unsupported":
        global_blockers["unsupported_stage_catalog"] += 1
    if not by_slug.get("training-program", {}).get("is_active"):
        global_blockers["training_program_unavailable"] += 1
    migration_pairs = {(m["app"], m["name"]) for m in data["migrations"]}
    schema_ready = {("traineediary", "0007_classify_stage_catalog"), ("roadmap", "0001_initial")} <= migration_pairs
    if not schema_ready:
        global_blockers["required_migration_not_recorded"] += 1
    orphan_counts = Counter()
    for key, grouped in (("history", histories), ("metrics", metrics), ("roadmap", confirmations)):
        for row in data[key]:
            if row["journey_id"] not in journeys:
                orphan_counts[key] += 1
            else:
                grouped[row["journey_id"]].append(row)
    for kind, n in orphan_counts.items():
        global_blockers["orphan_" + kind] += n

    mapping = Counter()
    work_evidence = Counter()
    completion = Counter()
    naive_progress = Counter()
    theory_coverage = Counter()
    for jid, j in journeys.items():
        def problem(code):
            issues[code].add(jid)

        if j["stage_scheme"] not in SCHEMES:
            problem("unknown_stage_scheme")
        if j["entry_type"] not in ENTRIES:
            problem("unknown_entry_type")
        if j["user_id"] not in users:
            problem("missing_user_link")
        if j["completed_by_id"] is not None and j["completed_by_id"] not in users:
            problem("missing_completed_by_link")
        current = stages.get(j["current_stage_id"])
        if not current:
            problem("missing_current_stage_link")
            continue
        history = sorted(histories[jid], key=lambda r: (r["started_at"], r["id"]))
        opened = [h for h in history if h["ended_at"] is None]
        field = "applies_to_internal_transfer" if j["entry_type"] == "internal_transfer" else "applies_to_new_hire"
        if not current[field] or current["catalog_scope"] not in (j["stage_scheme"], "shared"):
            problem("current_stage_not_applicable")
        if not j["probation_start_date"] <= j["stage_started_at"] <= today:
            problem("invalid_journey_dates")
        if not history:
            problem("missing_stage_history")
        elif history[0]["started_at"] != j["probation_start_date"]:
            problem("history_start_date_mismatch")
        if len(opened) != 1 or not history or opened[0] != history[-1]:
            problem("ambiguous_open_history")
        elif opened[0]["stage_id"] != j["current_stage_id"] or opened[0]["started_at"] != j["stage_started_at"]:
            problem("current_history_mismatch")
        for h in history:
            stage = stages.get(h["stage_id"])
            if not stage:
                problem("missing_history_stage_link")
            elif not stage[field] or stage["catalog_scope"] not in (j["stage_scheme"], "shared"):
                problem("history_stage_not_applicable")
            if h["changed_by_id"] is not None and h["changed_by_id"] not in users:
                problem("missing_history_author_link")
            if not j["probation_start_date"] <= h["started_at"] <= today:
                problem("invalid_history_start_date")
            if h["ended_at"] is not None and not h["started_at"] <= h["ended_at"] <= today:
                problem("invalid_history_interval")
        for left, right in zip(history, history[1:]):
            if left["ended_at"] != right["started_at"]:
                problem("history_gap_or_overlap")
        if current["group"] != "done" and any(j[f] for f in (
            "completion_status", "completed_at", "completion_comment", "completed_by_id",
        )):
            problem("completion_data_outside_done")
        if j["completion_status"] not in OUTCOMES:
            problem("unknown_completion_status")
        if j["completed_at"] and (not j["probation_start_date"] <= j["completed_at"] <= today
                                  or current["group"] == "done" and j["completed_at"] != j["stage_started_at"]):
            problem("invalid_completion_date")
        outcome = probation_outcome(j, current, today)
        completion[(allowed(j["stage_scheme"], SCHEMES), current["group"] == "done", outcome)] += 1
        if current["group"] == "done" and outcome == "insufficient_data":
            warnings["done_without_proven_probation_outcome"].add(jid)
        for m in metrics[jid]:
            if (m["week_number"] < 1 or m["speed_hours"] is not None and m["speed_hours"] < 0
                    or m["quality_percent"] is not None and not 0 <= m["quality_percent"] <= 100):
                problem("invalid_weekly_metric")
            if m["week_start_date"] is None:
                warnings["weekly_metric_date_missing_preserved"].add(jid)
        if len({m["week_number"] for m in metrics[jid]}) != len(metrics[jid]):
            problem("duplicate_metric_week")
        for event in confirmations[jid]:
            if event["actor_id"] not in users:
                problem("missing_roadmap_actor_link")
            if event["stage_code"] != "training" or event["action"] not in ("confirmed", "revoked"):
                problem("invalid_roadmap_confirmation")
            if j["entry_type"] == "internal_transfer":
                warnings["internal_transfer_has_training_confirmation"].add(jid)
        completed, valid = working_completions(j, history, stages, users, today)
        for slug in completed:
            work_evidence[(allowed(j["stage_scheme"], SCHEMES), slug)] += 1
        if not valid:
            warnings["roadmap_work_history_insufficient"].add(jid)
        if j["stage_scheme"] != "legacy":
            continue
        slug = current["slug"]
        target = by_slug.get(MAPPING.get(slug))
        mapping[(allowed(slug, MAPPING), target["slug"] if target else "__unmapped__", allowed(j["entry_type"], ENTRIES))] += 1
        if not target or not target[field]:
            problem("target_stage_not_applicable")
            continue
        source_progress = progress(j, stages, "legacy", today)
        naive = progress(j, stages, "unified", today, current=target)
        naive_progress["lower" if naive < source_progress else "higher" if naive > source_progress else "equal"] += 1
        visited_theory = {stages[h["stage_id"]]["slug"] for h in history if h["stage_id"] in stages} & THEORY
        if slug in THEORY:
            theory_coverage["currently_in_theory"] += 1
            # Visits are not evidence of training completion.
            theory_coverage["all_five_theory_stages_visited" if len(visited_theory) == 5 else "subset_of_theory_stages_visited"] += 1
            if any(h["stage_id"] in stages and stages[h["stage_id"]]["slug"] == "sandbox-candidate" for h in history):
                warnings["theory_after_sandbox_requires_review"].add(jid)
        if j["entry_type"] == "internal_transfer" and (visited_theory or slug == "sandbox-candidate"):
            problem("internal_transfer_has_inapplicable_theory")

    legacy_ids = {j["id"] for j in journeys.values() if j["stage_scheme"] == "legacy"}
    blocked_legacy = set().union(*(ids & legacy_ids for ids in issues.values())) if issues else set()
    for code, ids in issues.items():
        issue_rows[code] = len(ids)
    latest_confirmations = Counter()
    for jid, events in confirmations.items():
        if events:
            latest = max(events, key=lambda e: e["id"])
            latest_confirmations[(allowed(journeys[jid]["stage_scheme"], SCHEMES), allowed(latest["action"], {"confirmed", "revoked"}))] += 1
    choices = {"stage_scheme": SCHEMES, "entry_type": ENTRIES,
               "completion_status": OUTCOMES, "slug": set(DEFAULT_CATALOG)}
    stage_rows = [{**j, "slug": stages.get(j["current_stage_id"], {}).get("slug")} for j in journeys.values()]
    return {
        "audit_version": VERSION, "status": "audited", "as_of": today.isoformat(),
        "expected_application_revision": SOURCE_REVISION,
        "transaction": transaction_state, "catalog_profile": profile,
        "required_schema_recorded": schema_ready,
        "counts": {"journeys": len(journeys), "legacy_journeys": len(legacy_ids),
                   "unified_journeys": sum(j["stage_scheme"] == "unified" for j in journeys.values()),
                   "legacy_done": sum(j["stage_scheme"] == "legacy" and stages.get(j["current_stage_id"], {}).get("group") == "done" for j in journeys.values()),
                   "history_rows": len(data["history"]), "weekly_metric_rows": len(data["metrics"]),
                   "roadmap_confirmation_rows": len(data["roadmap"])},
        "by_scheme_entry_and_stage": distribution(stage_rows, ("stage_scheme", "entry_type", "slug"), choices),
        "by_scheme_and_completion_status": distribution(data["journeys"], ("stage_scheme", "completion_status"), choices),
        "probation_evidence": [{"scheme": s, "in_done": done, "outcome": outcome, "count": n}
                               for (s, done, outcome), n in sorted(completion.items())],
        "proposed_mapping": [{"from": a, "to": b, "entry_type": e, "count": n}
                             for (a, b, e), n in sorted(mapping.items())],
        "theory": dict(sorted(theory_coverage.items())),
        "naive_progress_recalculation": {"warning": "diagnostic_only_do_not_apply",
                                         **{key: naive_progress[key] for key in ("lower", "equal", "higher")}},
        "roadmap": {
            "latest_training_confirmation": [{"scheme": s, "action": a, "count": n} for (s, a), n in sorted(latest_confirmations.items())],
            "proven_work_stage_completions": [{"scheme": s, "stage": st, "count": n} for (s, st), n in sorted(work_evidence.items())],
            "sandbox_and_award_tables_read": False,
            "sandbox_progress_evaluated": False,
        },
        "integrity": {
            "global_blockers": dict(sorted(global_blockers.items())),
            "issue_journey_counts": dict(sorted(issue_rows.items())),
            "affected_legacy_counts": {code: len(ids & legacy_ids) for code, ids in sorted(issues.items())},
            "warning_journey_counts": {code: len(ids) for code, ids in sorted(warnings.items())},
            "blocked_legacy_journeys": len(blocked_legacy),
            "ready_for_mapping_review": not global_blockers and not blocked_legacy,
            "migration_authorized": False,
        },
        "preservation_baseline": {
            "snapshot_sha256": fingerprint({k: data[k] for k in ("stages", "journeys", "history", "metrics", "roadmap")}),
            "tables": {k: {"rows": len(data[k]), "sha256": fingerprint(data[k])}
                       for k in ("stages", "journeys", "history", "metrics", "roadmap")},
            "nonempty_text_counts": {
                "journey_comments": sum(bool(j["comment"].strip()) for j in data["journeys"]),
                "completion_comments": sum(bool(j["completion_comment"].strip()) for j in data["journeys"]),
                "history_notes": sum(bool(h["note"].strip()) for h in data["history"]),
                "metric_mentor_comments": sum(bool(m["mentor_comment"].strip()) for m in data["metrics"]),
                "metric_next_week_goals": sum(bool(m["next_week_goal"].strip()) for m in data["metrics"]),
                "roadmap_comments": sum(bool(e["comment"].strip()) for e in data["roadmap"]),
            },
            "post_migration_preservation_verified": False,
        },
        "proposed_preservation_policy": {
            "new_journeys": 0, "history_rows_deleted_or_rewritten": 0,
            "metric_rows_changed": 0, "roadmap_confirmations_created": 0,
            "award_events_created": 0, "original_dates_and_comments": "preserve",
            "training_confirmation": "never_infer_from_stage_or_time",
            "original_history": "retain_and_project_via_explicit_transfer_provenance",
            "partial_progress": "retain_source_calculation_until_next_real_transition",
            "internal_transfer": "no_theory_or_sandbox_requirement",
            "completed_probation": "same_journey_same_outcome_no_new_adaptation",
        },
    }


def read_snapshot(connection):
    """An explicit rollback always ends the one audit transaction."""
    from psycopg.rows import dict_row

    with connection.cursor(row_factory=dict_row) as cursor:
        try:
            cursor.execute("BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
            cursor.execute("SELECT current_setting('transaction_read_only') AS read_only, current_setting('transaction_isolation') AS isolation, (CURRENT_TIMESTAMP AT TIME ZONE 'Europe/Moscow')::date AS as_of")
            state = cursor.fetchone()
            if state["read_only"] != "on" or state["isolation"] != "repeatable read":
                raise RuntimeError("readonly_not_enforced")
            data = {}
            for name, query in QUERIES.items():
                cursor.execute(query)
                data[name] = cursor.fetchall()
            return build_report(data, state["as_of"], {
                "read_only": True, "isolation": "repeatable read", "end": "rollback",
                "statement_timeout_ms": 15000, "lock_timeout_ms": 2000,
            })
        finally:
            connection.rollback()


def run():
    """No ORM, shell, .env loading, Django startup, Docker API or broker clients."""
    import psycopg

    required = ("DB_NAME", "DB_USER", "DB_PASSWORD", "DB_HOST")
    if any(not os.environ.get(key) for key in required):
        raise RuntimeError("required_database_environment_missing")
    with psycopg.connect(
        dbname=os.environ["DB_NAME"], user=os.environ["DB_USER"], password=os.environ["DB_PASSWORD"],
        host=os.environ["DB_HOST"], port=os.environ.get("DB_PORT", "5432"),
        connect_timeout=5, autocommit=True, application_name="traineediary-unification-audit-v1",
        options="-c default_transaction_read_only=on -c statement_timeout=15000 -c lock_timeout=2000 -c idle_in_transaction_session_timeout=60000",
    ) as connection:
        return read_snapshot(connection)


def main():
    try:
        report = run()
    except Exception as exc:
        # Never disclose server errors, connection parameters, SQL or row contents.
        state = getattr(exc, "sqlstate", None)
        safe_state = state if isinstance(state, str) and len(state) == 5 and state.isalnum() else None
        report = {"audit_version": VERSION, "status": "error", "error": "audit_failed",
                  "sqlstate": safe_state, "migration_authorized": False}
        print(json.dumps(report, ensure_ascii=False))
        return 1
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
