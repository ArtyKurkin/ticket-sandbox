from datetime import timedelta

from django.db import transaction
from django.db.models import Subquery
from django.utils import timezone

from assessment.constants import ExamAttemptStatus
from assessment.models import (
    ExamAnswer,
    ExamAttempt,
    ExamQuestionSnapshot,
)
from assessment.services.answers import (
    submit_exam_answer,
)


def _unanswered_snapshots(attempt):
    answered_snapshot_ids = (
        ExamAnswer.objects
        .filter(
            snapshot__attempt=attempt,
        )
        .values("snapshot_id")
    )

    return (
        ExamQuestionSnapshot.objects
        .filter(
            attempt=attempt,
        )
        .exclude(
            pk__in=Subquery(
                answered_snapshot_ids
            ),
        )
    )


def get_current_question(attempt):
    return (
        _unanswered_snapshots(attempt)
        .order_by("position")
        .first()
    )


def get_question_deadline(snapshot):
    if snapshot.started_at is None:
        return None

    return (
        snapshot.started_at
        + timedelta(
            seconds=snapshot.time_limit_seconds,
        )
    )


@transaction.atomic
def open_current_question(
    attempt,
    *,
    now=None,
):
    now = now or timezone.now()

    attempt = (
        ExamAttempt.objects
        .select_for_update()
        .get(pk=attempt.pk)
    )

    if (
        attempt.status
        != ExamAttemptStatus.IN_PROGRESS
    ):
        return None

    while True:
        snapshot = (
            _unanswered_snapshots(attempt)
            .select_for_update()
            .order_by("position")
            .first()
        )

        if snapshot is None:
            return None

        if snapshot.started_at is None:
            snapshot.started_at = now

            snapshot.save(
                update_fields=[
                    "started_at",
                ]
            )

            return snapshot

        deadline = get_question_deadline(
            snapshot
        )

        if now < deadline:
            return snapshot

        # Время вопроса истекло.
        # Фиксируем timeout и ищем следующий.
        submit_exam_answer(
            snapshot,
            response_payload={},
            now=now,
        )
