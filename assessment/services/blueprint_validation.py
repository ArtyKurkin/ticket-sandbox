from django.core.exceptions import ValidationError

from assessment.constants import QuestionStatus
from assessment.models import Question


def get_blueprint_pool_status(blueprint):
    result = []

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

    for quota in quotas:
        available_family_count = (
            Question.objects.filter(
                level=blueprint.level,
                status=QuestionStatus.ACTIVE,
                family__skill=quota.skill,
                family__is_active=True,
                family__skill__is_active=True,
                family__skill__topic__is_active=True,
            )
            .values("family_id")
            .distinct()
            .count()
        )

        result.append(
            {
                "topic": quota.skill.topic,
                "skill": quota.skill,
                "required_count": quota.question_count,
                "available_family_count": (
                    available_family_count
                ),
                "is_sufficient": (
                    available_family_count
                    >= quota.question_count
                ),
            }
        )

    return result


def validate_blueprint_question_pool(blueprint):
    pool_status = get_blueprint_pool_status(
        blueprint,
    )

    if not pool_status:
        raise ValidationError(
            {
                "skill_quotas": (
                    "Добавь хотя бы одну квоту "
                    "по проверяемому навыку."
                ),
            }
        )

    shortages = []

    for item in pool_status:
        if item["is_sufficient"]:
            continue

        shortages.append(
            (
                f"{item['topic'].name} → "
                f"{item['skill'].name}: требуется "
                f"{item['required_count']}, доступно "
                f"{item['available_family_count']}."
            )
        )

    if shortages:
        raise ValidationError(
            {
                "skill_quotas": shortages,
            }
        )

    return pool_status
