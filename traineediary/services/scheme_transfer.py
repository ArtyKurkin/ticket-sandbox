"""Read-only interpretation of the immutable source history after transfer."""

THEORY_SLUGS = frozenset({
    "first-day", "vds", "managed-services", "client-service", "before-tickets",
})


def effective_history_stage(entry):
    journey = entry.journey
    if journey.stage_scheme != "unified" or entry.stage.slug not in THEORY_SLUGS:
        return entry.stage
    transfer = getattr(journey, "scheme_transfer", None)
    if transfer is None or transfer.batch.reverted_at is not None or entry.pk not in transfer.source_history_ids:
        return entry.stage
    from ..models import TraineeStage

    # The destination may be a shared work stage, not the training program.
    if not hasattr(transfer, "_program_stage"):
        transfer._program_stage = TraineeStage.objects.using(entry._state.db).get(slug="training-program")
    return transfer._program_stage
