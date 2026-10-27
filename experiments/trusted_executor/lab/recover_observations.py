"""Lab-only recovery of abandoned HTTP observations."""

import argparse
import os
import sys
from datetime import timedelta

os.environ.setdefault(
    "DJANGO_SETTINGS_MODULE",
    "config.e2e_settings",
)

import django
django.setup()

from django.utils import timezone
from sandbox.models import HTTPObservationRun


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--min-age", type=int, default=120)
    args = parser.parse_args()

    if args.min_age < 60:
        parser.error("min-age must be at least 60 seconds")

    cutoff = timezone.now() - timedelta(seconds=args.min_age)

    queued = list(
        HTTPObservationRun.objects.filter(
            status="queued",
            requested_at__lt=cutoff,
        ).values_list("run_id", flat=True)
    )

    running = list(
        HTTPObservationRun.objects.filter(
            status="running",
            started_at__lt=cutoff,
        ).values_list("run_id", flat=True)
    )

    print("STALE QUEUED:", len(queued))
    print("STALE RUNNING:", len(running))
    print("MODE:", "APPLY" if args.apply else "DRY RUN")

    changed = 0

    if args.apply:
        # Safe to retire queued entries without launching Docker.
        # Concurrent gateway claims race on the status predicate.
        for run_id in queued:
            changed += HTTPObservationRun.objects.filter(
                run_id=run_id,
                status="queued",
                requested_at__lt=cutoff,
            ).update(
                status="finished",
                http="unknown",
                reason="dispatch_unavailable",
                finished_at=timezone.now(),
            )

    print("QUEUED FINISHED:", changed)
    print("RUNNING REQUIRE MANUAL REVIEW:", len(running))

    if running:
        print(
            "WARNING: running observations were NOT modified. "
            "Inspect gateway, Docker verifier and ownership before recovery."
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
