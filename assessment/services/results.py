from collections import defaultdict
from decimal import Decimal, ROUND_HALF_UP

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from assessment.constants import ExamAttemptStatus
from assessment.models import (
    AssessmentResult,
    ExamAnswer,
    ExamAttempt,
)


ZERO = Decimal("0.00")
HUNDRED = Decimal("100.00")
PRECISION = Decimal("0.01")


def _average_score(scores):
    if not scores:
        return ZERO

    result = (
        sum(scores, ZERO)
        / Decimal(len(scores))
    )

    return result.quantize(
        PRECISION,
        rounding=ROUND_HALF_UP,
    )


def _build_breakdown(answers):
    topics = defaultdict(
        lambda: {
            "name": "",
            "scores": [],
        }
    )

    skills = defaultdict(
        lambda: {
            "name": "",
            "topic_slug": "",
            "topic_name": "",
            "scores": [],
        }
    )

    for answer in answers:
        snapshot = answer.snapshot
        score = answer.score_percentage

        topic = topics[
            snapshot.topic_slug
        ]

        topic["name"] = snapshot.topic_name
        topic["scores"].append(score)

        skill = skills[
            snapshot.skill_slug
        ]

        skill["name"] = snapshot.skill_name
        skill["topic_slug"] = (
            snapshot.topic_slug
        )
        skill["topic_name"] = (
            snapshot.topic_name
        )
        skill["scores"].append(score)

    topic_breakdown = {}

    for slug, data in topics.items():
        average = _average_score(
            data["scores"]
        )

        topic_breakdown[slug] = {
            "name": data["name"],
            "question_count": len(
                data["scores"]
            ),
            "score_percentage": str(
                average
            ),
        }

    skill_breakdown = {}

    for slug, data in skills.items():
        average = _average_score(
            data["scores"]
        )

        skill_breakdown[slug] = {
            "name": data["name"],
            "topic_slug": (
                data["topic_slug"]
            ),
            "topic_name": (
                data["topic_name"]
            ),
            "question_count": len(
                data["scores"]
            ),
            "score_percentage": str(
                average
            ),
        }

    return (
        topic_breakdown,
        skill_breakdown,
    )


@transaction.atomic
def complete_exam_attempt(
    attempt,
    *,
    now=None,
):
    now = now or timezone.now()

    attempt = (
        ExamAttempt.objects
        .select_for_update()
        .select_related(
            "assignment",
            "assignment__employee",
            "assignment__employee__user",
        )
        .get(pk=attempt.pk)
    )

    if (
        attempt.status
        == ExamAttemptStatus.INVALIDATED
    ):
        raise ValidationError(
            "Аннулированную попытку "
            "нельзя завершить."
        )

    if (
        attempt.status
        == ExamAttemptStatus.COMPLETED
    ):
        try:
            return attempt.result, False
        except AssessmentResult.DoesNotExist:
            raise ValidationError(
                "Попытка отмечена завершённой, "
                "но результат отсутствует."
            )

    snapshots_count = (
        attempt.question_snapshots.count()
    )

    if snapshots_count == 0:
        raise ValidationError(
            "В попытке нет вопросов."
        )

    answers = list(
        ExamAnswer.objects.filter(
            snapshot__attempt=attempt,
        )
        .select_related(
            "snapshot",
        )
        .order_by(
            "snapshot__position",
        )
    )

    if len(answers) != snapshots_count:
        raise ValidationError(
            (
                "Нельзя завершить тест: "
                f"отвечено {len(answers)} "
                f"из {snapshots_count} вопросов."
            )
        )

    scores = [
        answer.score_percentage
        for answer in answers
    ]

    score_percentage = _average_score(
        scores
    )

    fully_correct_questions = sum(
        answer.is_correct
        for answer in answers
    )

    (
        topic_breakdown,
        skill_breakdown,
    ) = _build_breakdown(
        answers
    )

    result = AssessmentResult.objects.create(
        attempt=attempt,
        score_percentage=score_percentage,
        passed=(
            score_percentage
            >= Decimal(
                str(attempt.pass_percentage)
            )
        ),
        total_questions=snapshots_count,
        fully_correct_questions=(
            fully_correct_questions
        ),
        topic_breakdown=topic_breakdown,
        skill_breakdown=skill_breakdown,
    )

    attempt.status = (
        ExamAttemptStatus.COMPLETED
    )
    attempt.completed_at = now

    attempt.save(
        update_fields=[
            "status",
            "completed_at",
        ]
    )

    return result, True
