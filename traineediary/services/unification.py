"""Explicit, baseline-locked v1 data migration. No signals or Sandbox writes.

The standalone audit v1 defines canonical fingerprints of the original fields.
Schema migration 0008 only creates provenance tables; this runner is opt-in.
"""
from collections import Counter
from contextlib import contextmanager
import json
import re

from django.db import connections, transaction
from django.utils import timezone

from deploy import audit_traineediary_unification as audit
from ..models import StageSchemeTransfer, StageSchemeTransferBatch, TraineeJourney

SOURCE_KEYS = ("stages", "journeys", "history", "metrics", "roadmap")


class TransferError(Exception):
    """Only fixed, non-sensitive diagnostic codes may be exposed to operators."""


def read_source(alias):
    data = {}
    with connections[alias].cursor() as cursor:
        for name, query in audit.QUERIES.items():
            cursor.execute(query)
            fields = [d[0] for d in cursor.description]
            data[name] = [dict(zip(fields, row)) for row in cursor.fetchall()]
    return data


def fingerprints(data):
    return {
        "snapshot_sha256": audit.fingerprint({k: data[k] for k in SOURCE_KEYS}),
        "tables": {k: {"rows": len(data[k]), "sha256": audit.fingerprint(data[k])} for k in SOURCE_KEYS},
    }


def load_baseline(path):
    try:
        with open(path) as stream:
            baseline = json.load(stream)
        hashes = baseline["preservation_baseline"]
        if (baseline["audit_version"] != 1 or baseline["status"] != "audited"
                or baseline["integrity"]["ready_for_mapping_review"] is not True
                or baseline["integrity"]["blocked_legacy_journeys"] != 0
                or not re.fullmatch(r"[0-9a-f]{64}", hashes["snapshot_sha256"])):
            raise ValueError
        for key in ("journeys", "history", "metrics"):
            if not re.fullmatch(r"[0-9a-f]{64}", hashes["tables"][key]["sha256"]):
                raise ValueError
        if not isinstance(baseline["counts"], dict) or "legacy_journeys" not in baseline["counts"]:
            raise ValueError
        return baseline
    except (OSError, ValueError, KeyError, TypeError):
        raise TransferError("invalid_baseline") from None


def check_baseline(data, report, baseline):
    actual = fingerprints(data)
    expected = baseline["preservation_baseline"]
    if actual["snapshot_sha256"] != expected["snapshot_sha256"]:
        raise TransferError("source_snapshot_differs_from_reviewed_baseline")
    for key, table in expected["tables"].items():
        if key not in actual["tables"] or table != actual["tables"][key]:
            raise TransferError("source_table_differs_from_reviewed_baseline")
    if any(report["counts"].get(k) != v for k, v in baseline["counts"].items()):
        raise TransferError("source_counts_differ_from_reviewed_baseline")
    if report["catalog_profile"] != baseline["catalog_profile"]:
        raise TransferError("catalog_profile_changed")
    if not report["integrity"]["ready_for_mapping_review"]:
        raise TransferError("audit_has_blockers")
    stages = {s["id"]: s["slug"] for s in data["stages"]}
    legacy = [j for j in data["journeys"] if j["stage_scheme"] == "legacy"]
    for field, actual_counts in (
        ("expected_legacy_stages", dict(Counter(stages[j["current_stage_id"]] for j in legacy))),
        ("expected_legacy_outcomes", dict(Counter(j["completion_status"] for j in legacy))),
    ):
        if field in baseline and actual_counts != baseline[field]:
            raise TransferError("reviewed_distribution_changed")


def schema_available(alias):
    names = connections[alias].introspection.table_names()
    return all(model._meta.db_table in names for model in (StageSchemeTransfer, StageSchemeTransferBatch))


@contextmanager
def readonly_snapshot(alias):
    connection = connections[alias]
    old_query_only = None
    if connection.vendor == "sqlite":
        with connection.cursor() as cursor:
            cursor.execute("PRAGMA query_only")
            old_query_only = cursor.fetchone()[0]
            cursor.execute("PRAGMA query_only=ON")
    try:
        with transaction.atomic(using=alias):
            if connection.vendor == "postgresql":
                with connection.cursor() as cursor:
                    cursor.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
                    cursor.execute("SET LOCAL statement_timeout = '15s'")
                    cursor.execute("SET LOCAL lock_timeout = '2s'")
            yield
    finally:
        if old_query_only is not None:
            with connection.cursor() as cursor:
                cursor.execute(f"PRAGMA query_only={int(old_query_only)}")


def lock_sources(alias):
    connection = connections[alias]
    if connection.vendor == "postgresql":
        # No Sandbox, achievements, terminal, auth or task tables are locked.
        names = ["traineediary_traineestage", "traineediary_traineejourney",
                 "traineediary_stagehistory", "traineediary_weeklymetric",
                 "roadmap_trainingconfirmationevent", StageSchemeTransfer._meta.db_table,
                 StageSchemeTransferBatch._meta.db_table]
        quoted = ", ".join(connection.ops.quote_name(n) for n in sorted(names))
        with connection.cursor() as cursor:
            cursor.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
            cursor.execute("SET LOCAL statement_timeout = '15s'")
            cursor.execute("SET LOCAL lock_timeout = '2s'")
            cursor.execute(f"LOCK TABLE {quoted} IN SHARE ROW EXCLUSIVE MODE")


def basis_for(journey, stages, data, today):
    stage = stages[journey["current_stage_id"]]
    field = "applies_to_internal_transfer" if journey["entry_type"] == "internal_transfer" else "applies_to_new_hire"
    applicable = [s for s in stages.values() if s["id"] == stage["id"] or (
        s["is_active"] and s[field] and s["catalog_scope"] in ("legacy", "shared")
    )]
    history = sorted([h for h in data["history"] if h["journey_id"] == journey["id"]], key=lambda h: (h["started_at"], h["id"]))
    users = {u["id"]: u for u in data["user_links"]}
    completed, _ = audit.working_completions(journey, history, stages, users, today)
    return {
        "total_weight": sum(s["progress_weight_percent"] for s in applicable),
        "weight_before": sum(s["progress_weight_percent"] for s in applicable if s["order"] < stage["order"]),
        "current_weight": stage["progress_weight_percent"], "max_days": stage["max_days"],
        "percent_at_transfer": audit.progress(journey, stages, "legacy", today),
        "completed_work_stages": sorted(completed),
        "probation_outcome": audit.probation_outcome(journey, stage, today),
    }


def expected_after(data):
    stages = {s["id"]: s for s in data["stages"]}
    targets = {s["slug"]: s["id"] for s in data["stages"]}
    result = {key: list(rows) for key, rows in data.items()}
    result["journeys"] = []
    for journey in data["journeys"]:
        row = dict(journey)
        if row["stage_scheme"] == "legacy":
            row["stage_scheme"] = "unified"
            row["current_stage_id"] = targets[audit.MAPPING[stages[journey["current_stage_id"]]["slug"]]]
        result["journeys"].append(row)
    return result


def verify_runtime(batch, alias, *, immediate=False):
    """No Sandbox projection: only existing diary and work-stage evidence rules."""
    from roadmap.services.projection import _probation, _working_evidence
    from achievements.services.evaluators.base import history_for
    from .integrity import check_journey_integrity

    transfers = list(batch.transfers.using(alias).select_related("journey__current_stage", "batch"))
    for transfer in transfers:
        journey = transfer.journey
        # Avoid a second provenance query and ensure the audit alias is retained.
        journey.scheme_transfer = transfer
        history = list(journey.stage_history.select_related("stage", "changed_by").order_by("started_at", "id"))
        if check_journey_integrity(journey):
            raise TransferError("post_migration_journey_integrity_failed")
        if history_for(journey) is None:
            raise TransferError("post_migration_award_history_changed")
        work, _ = _working_evidence(journey, history, _probation(journey))
        completed = sorted(slug.replace("_", "-") for slug, value in work.items() if value["completed"])
        if (completed != transfer.progress_basis["completed_work_stages"]
                or _probation(journey) != transfer.progress_basis["probation_outcome"]):
            raise TransferError("post_migration_roadmap_evidence_changed")
        if immediate and journey.progress_percent != transfer.progress_basis["percent_at_transfer"]:
            raise TransferError("post_migration_progress_changed")
    return len(transfers)


def verify_batch(batch, data, alias):
    transfers = list(batch.transfers.using(alias).all())
    if len(transfers) != batch.baseline["counts"]["legacy_journeys"]:
        raise TransferError("transfer_provenance_incomplete")
    if batch.reverted_at is not None:
        if fingerprints(data) != batch.verification["before"]:
            raise TransferError("source_changed_since_rollback")
        return {"status": "already_rolled_back", "changed": False, "verified": True}
    if (fingerprints(data) != batch.verification["after"]
            or audit.fingerprint(data["user_links"]) != batch.verification["user_links_sha256"]):
        raise TransferError("post_snapshot_changed_rerun_and_rollback_refused")
    source = {key: list(rows) for key, rows in data.items()}
    by_journey = {t.journey_id: t for t in transfers}
    source["journeys"] = [
        {**j, "stage_scheme": by_journey[j["id"]].source_scheme,
         "current_stage_id": by_journey[j["id"]].source_stage_id}
        if j["id"] in by_journey else j for j in data["journeys"]
    ]
    if fingerprints(source) != batch.verification["before"]:
        raise TransferError("transfer_provenance_source_mismatch")
    stages = {s["id"]: s for s in source["stages"]}
    targets = {s["slug"]: s["id"] for s in source["stages"]}
    for j in source["journeys"]:
        transfer = by_journey.get(j["id"])
        if transfer is None:
            continue
        history = [h for h in source["history"] if h["journey_id"] == j["id"]]
        opened = [h for h in history if h["ended_at"] is None]
        if (transfer.source_sha256 != audit.fingerprint(j)
                or transfer.audit_sha256 != batch.source_snapshot_sha256
                or transfer.source_scheme != "legacy"
                or transfer.source_stage_started_at != j["stage_started_at"]
                or transfer.target_stage_id != targets[audit.MAPPING[stages[j["current_stage_id"]]["slug"]]]
                or sorted(transfer.source_history_ids) != [h["id"] for h in history]
                or len(opened) != 1 or opened[0]["id"] != transfer.source_open_history_id
                or transfer.progress_basis != basis_for(j, stages, source, batch.as_of)):
            raise TransferError("transfer_provenance_corrupt")
    count = verify_runtime(batch, alias)
    return {"status": "already_applied", "changed": False, "verified": True,
            "transferred": count, "checks": batch.verification}


def migrate_schemes(baseline, *, alias="default", execute=False, action="apply"):
    if action not in ("apply", "verify", "rollback") or (action == "verify" and execute):
        raise TransferError("invalid_action")
    # For PostgreSQL, acquire locks before taking the source snapshot. An
    # introspection SELECT inside REPEATABLE READ would take it too early.
    if execute and not schema_available(alias):
        raise TransferError("schema_migration_0008_required")
    context = transaction.atomic(using=alias) if execute else readonly_snapshot(alias)
    with context:
        if execute:
            lock_sources(alias)
        available = schema_available(alias)
        today = timezone.localdate()
        data = read_source(alias)
        source_hash = baseline["preservation_baseline"]["snapshot_sha256"]
        batch = (StageSchemeTransferBatch.objects.using(alias).filter(source_snapshot_sha256=source_hash).first()
                 if available else None)
        if batch is not None:
            result = verify_batch(batch, data, alias)
            if action != "rollback" or batch.reverted_at is not None:
                return result
            result["status"] = "rollback_ready"
            if not execute:
                return result
            for transfer in batch.transfers.using(alias).all():
                count = TraineeJourney.objects.using(alias).filter(pk=transfer.journey_id, stage_scheme="unified").update(
                    stage_scheme=transfer.source_scheme, current_stage_id=transfer.source_stage_id,
                )
                if count != 1:
                    raise TransferError("rollback_concurrent_change")
            after = read_source(alias)
            if fingerprints(after) != batch.verification["before"]:
                raise TransferError("rollback_source_not_restored")
            StageSchemeTransferBatch.objects.using(alias).filter(pk=batch.pk).update(reverted_at=timezone.now())
            return {"status": "rolled_back", "changed": True, "verified": True,
                    "source_restored": fingerprints(after)}
        if action != "apply":
            raise TransferError("no_matching_transfer_batch")
        report = audit.build_report(data, today, {"read_only": not execute})
        check_baseline(data, report, baseline)
        candidates = [j for j in data["journeys"] if j["stage_scheme"] == "legacy"]
        if available and StageSchemeTransfer.objects.using(alias).filter(journey_id__in=[j["id"] for j in candidates]).exists():
            raise TransferError("journey_already_has_transfer_provenance")
        if not candidates:
            return {"status": "nothing_to_transfer", "changed": False, "verified": True}
        planned = expected_after(data)
        changes = sum(a["current_stage_id"] != b["current_stage_id"] for a, b in zip(data["journeys"], planned["journeys"]))
        result = {"status": "dry_run", "changed": False, "baseline_match": True,
                  "schema_ready": available, "journeys_to_transfer": len(candidates),
                  "changed_fields": {"stage_scheme": len(candidates), "current_stage_id": changes},
                  "mapping": report["proposed_mapping"], "warnings": report["integrity"]["warning_journey_counts"],
                  "history_rows": len(data["history"]), "metric_rows": len(data["metrics"]),
                  "expected_after": fingerprints(planned), "progress_policy": "keep_original_formula_until_real_transition"}
        if not execute:
            return result
        batch = StageSchemeTransferBatch.objects.using(alias).create(
            source_snapshot_sha256=source_hash, baseline=baseline, as_of=today,
        )
        stages = {s["id"]: s for s in data["stages"]}
        targets = {s["slug"]: s["id"] for s in data["stages"]}
        for journey in candidates:
            history = [h for h in data["history"] if h["journey_id"] == journey["id"]]
            opened = next(h for h in history if h["ended_at"] is None)
            target = targets[audit.MAPPING[stages[journey["current_stage_id"]]["slug"]]]
            StageSchemeTransfer.objects.using(alias).create(
                batch=batch, journey_id=journey["id"], source_stage_id=journey["current_stage_id"],
                target_stage_id=target, source_stage_started_at=journey["stage_started_at"],
                source_open_history_id=opened["id"], source_history_ids=[h["id"] for h in history],
                progress_basis=basis_for(journey, stages, data, today), audit_sha256=source_hash,
                source_sha256=audit.fingerprint(journey),
            )
            if TraineeJourney.objects.using(alias).filter(pk=journey["id"], stage_scheme="legacy").update(
                stage_scheme="unified", current_stage_id=target,
            ) != 1:
                raise TransferError("source_changed_concurrently")
        actual = read_source(alias)
        if fingerprints(actual) != fingerprints(planned):
            raise TransferError("protected_fields_changed")
        verified = verify_runtime(batch, alias, immediate=True)
        checks = {"before": fingerprints(data), "after": fingerprints(actual),
                  "user_links_sha256": audit.fingerprint(data["user_links"]),
                  "progress_unchanged": verified, "roadmap_evidence_unchanged": verified,
                  "award_history_unchanged": verified,
                  "new_journeys": 0, "new_roadmap_confirmations": 0, "new_award_events": 0}
        StageSchemeTransferBatch.objects.using(alias).filter(pk=batch.pk).update(verification=checks)
        return {**result, "status": "applied", "changed": True, "verified": True, "checks": checks}
