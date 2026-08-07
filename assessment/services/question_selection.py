import hashlib
import random
from collections import defaultdict

from assessment.constants import QuestionStatus
from assessment.models import Question
from assessment.services.blueprint_validation import (
    validate_blueprint_question_pool,
)


def _build_random(seed):
    normalized_seed = str(seed).encode("utf-8")

    digest = hashlib.sha256(
        normalized_seed
    ).digest()

    integer_seed = int.from_bytes(
        digest,
        byteorder="big",
    )

    return random.Random(integer_seed)


def select_questions_for_blueprint(
    blueprint,
    *,
    seed,
):
    """
    Собирает набор вопросов для конкретного прохождения.

    При одинаковых blueprint и seed результат
    должен быть одинаковым.
    """

    validate_blueprint_question_pool(
        blueprint,
    )

    rng = _build_random(seed)

    quotas = (
        blueprint.skill_quotas
        .select_related(
            "skill",
            "skill__topic",
        )
        .order_by(
            "order",
            "skill__topic__order",
            "skill__order",
            "skill__name",
        )
    )

    selected_questions = []

    for quota in quotas:
        questions = list(
            Question.objects.filter(
                level=blueprint.level,
                status=QuestionStatus.ACTIVE,
                family__skill=quota.skill,
                family__is_active=True,
                family__skill__is_active=True,
                family__skill__topic__is_active=True,
            )
            .select_related(
                "family",
                "family__skill",
                "family__skill__topic",
            )
            .order_by(
                "family_id",
                "id",
            )
        )

        questions_by_family = defaultdict(list)

        for question in questions:
            questions_by_family[
                question.family_id
            ].append(question)

        family_ids = sorted(
            questions_by_family.keys()
        )

        selected_family_ids = rng.sample(
            family_ids,
            quota.question_count,
        )

        for family_id in selected_family_ids:
            family_questions = (
                questions_by_family[
                    family_id
                ]
            )

            selected_questions.append(
                rng.choice(
                    family_questions
                )
            )

    if blueprint.shuffle_questions:
        rng.shuffle(
            selected_questions
        )

    return selected_questions
