from datetime import timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from assessment.constants import ExamAttemptStatus
from assessment.models import (
    ExamAnswer,
    ExamQuestionSnapshot,
)
from assessment.services.answer_grading import (
    grade_snapshot_answer,
)


@transaction.atomic
def submit_exam_answer(
    snapshot,
    *,
    response_payload,
    now=None,
):
    now = now or timezone.now()

    snapshot = (
        ExamQuestionSnapshot.objects
        .select_for_update()
        .select_related(
            "attempt",
        )
        .get(pk=snapshot.pk)
    )

    attempt = snapshot.attempt

    if (
        attempt.status
        != ExamAttemptStatus.IN_PROGRESS
    ):
        raise ValidationError(
            "Эта попытка уже не активна."
        )

    if snapshot.started_at is None:
        raise ValidationError(
            "Вопрос ещё не был открыт."
        )

    deadline = (
        snapshot.started_at
        + timedelta(
            seconds=snapshot.time_limit_seconds,
        )
    )

    existing_answer = (
        ExamAnswer.objects
        .filter(snapshot=snapshot)
        .first()
    )

    if existing_answer:
        if not attempt.allow_back_navigation:
            raise ValidationError(
                "Ответ на этот вопрос уже отправлен."
            )

        if now >= deadline:
            raise ValidationError(
                "Время на этот вопрос уже закончилось."
            )

        score = grade_snapshot_answer(
            snapshot,
            response_payload,
        )

        response_time_seconds = max(
            0,
            int(
                (
                    now - snapshot.started_at
                ).total_seconds()
            ),
        )

        existing_answer.response_payload = (
            response_payload
        )
        existing_answer.score_percentage = score
        existing_answer.is_correct = (
            score == 100
        )
        existing_answer.timed_out = False
        existing_answer.response_time_seconds = (
            response_time_seconds
        )

        existing_answer.save(
            update_fields=[
                "response_payload",
                "score_percentage",
                "is_correct",
                "timed_out",
                "response_time_seconds",
                "updated_at",
            ]
        )

        return existing_answer, False

    timed_out = now >= deadline

    elapsed_seconds = max(
        0,
        int(
            (
                now - snapshot.started_at
            ).total_seconds()
        ),
    )

    response_time_seconds = min(
        elapsed_seconds,
        snapshot.time_limit_seconds,
    )

    if timed_out:
        score = Decimal("0.00")
        response_payload = {}
    else:
        score = grade_snapshot_answer(
            snapshot,
            response_payload,
        )

    answer = ExamAnswer.objects.create(
        snapshot=snapshot,
        response_payload=response_payload,
        score_percentage=score,
        is_correct=(
            not timed_out
            and score == 100
        ),
        timed_out=timed_out,
        response_time_seconds=(
            response_time_seconds
        ),
    )

    return answer, True
