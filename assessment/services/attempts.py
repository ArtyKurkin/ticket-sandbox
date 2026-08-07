import secrets

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Max
from django.utils import timezone

from assessment.constants import ExamAttemptStatus
from assessment.models import (
    ExamAssignment,
    ExamAttempt,
    ExamQuestionSnapshot,
)
from assessment.services.question_selection import (
    select_questions_for_blueprint,
)
from assessment.services.question_snapshot import (
    build_question_snapshot_data,
)


def _validate_assignment_for_start(
    assignment,
    *,
    now,
):
    campaign = assignment.campaign
    blueprint = campaign.blueprint
    employee = assignment.employee

    if not assignment.is_active:
        raise ValidationError(
            "Назначение теста неактивно."
        )

    if not employee.is_active:
        raise ValidationError(
            "Профиль сотрудника неактивен."
        )

    if employee.level != blueprint.level:
        raise ValidationError(
            "Уровень сотрудника не совпадает "
            "с уровнем теста."
        )

    if not campaign.is_active:
        raise ValidationError(
            "Кампания тестирования неактивна."
        )

    if not blueprint.is_active:
        raise ValidationError(
            "Шаблон теста неактивен."
        )

    if (
        campaign.opens_at
        and now < campaign.opens_at
    ):
        raise ValidationError(
            "Тестирование ещё не началось."
        )

    if (
        campaign.closes_at
        and now >= campaign.closes_at
    ):
        raise ValidationError(
            "Срок прохождения теста закончился."
        )


@transaction.atomic
def start_exam_attempt(
    assignment,
    *,
    seed=None,
    now=None,
):
    now = now or timezone.now()

    assignment = (
        ExamAssignment.objects
        .select_for_update()
        .select_related(
            "campaign",
            "campaign__blueprint",
            "employee",
            "employee__user",
        )
        .get(pk=assignment.pk)
    )

    existing_attempt = (
        assignment.attempts
        .filter(
            status=ExamAttemptStatus.IN_PROGRESS,
        )
        .order_by("-attempt_number")
        .first()
    )

    if existing_attempt:
        return existing_attempt, False

    _validate_assignment_for_start(
        assignment,
        now=now,
    )

    attempt_count = (
        assignment.attempts.count()
    )

    if attempt_count >= assignment.attempt_limit:
        raise ValidationError(
            "Доступные попытки закончились."
        )

    last_attempt_number = (
        assignment.attempts.aggregate(
            value=Max("attempt_number")
        )["value"]
        or 0
    )

    selection_seed = (
        seed
        if seed is not None
        else secrets.token_hex(16)
    )

    blueprint = assignment.campaign.blueprint

    selected_questions = (
        select_questions_for_blueprint(
            blueprint,
            seed=selection_seed,
        )
    )

    attempt = ExamAttempt.objects.create(
        assignment=assignment,
        attempt_number=(
            last_attempt_number + 1
        ),
        status=ExamAttemptStatus.IN_PROGRESS,
        selection_seed=selection_seed,
        campaign_name=assignment.campaign.name,
        blueprint_name=blueprint.name,
        level=blueprint.level,
        pass_percentage=blueprint.pass_percentage,
        allow_back_navigation=(
            blueprint.allow_back_navigation
        ),
        shuffle_questions=(
            blueprint.shuffle_questions
        ),
        shuffle_answer_options=(
            blueprint.shuffle_answer_options
        ),
    )

    for position, question in enumerate(
        selected_questions,
        start=1,
    ):
        snapshot_data = (
            build_question_snapshot_data(
                question,
                seed=selection_seed,
                shuffle_answer_options=(
                    blueprint.shuffle_answer_options
                ),
            )
        )

        ExamQuestionSnapshot.objects.create(
            attempt=attempt,
            position=position,
            **snapshot_data,
        )

    return attempt, True
