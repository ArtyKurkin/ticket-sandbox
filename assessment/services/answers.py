from django.core.exceptions import ValidationError
from django.db import transaction

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
):
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

    score = grade_snapshot_answer(
        snapshot,
        response_payload,
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

        existing_answer.response_payload = (
            response_payload
        )
        existing_answer.score_percentage = score
        existing_answer.is_correct = (
            score == 100
        )

        existing_answer.save(
            update_fields=[
                "response_payload",
                "score_percentage",
                "is_correct",
                "updated_at",
            ]
        )

        return existing_answer, False

    answer = ExamAnswer.objects.create(
        snapshot=snapshot,
        response_payload=response_payload,
        score_percentage=score,
        is_correct=(score == 100),
    )

    return answer, True
