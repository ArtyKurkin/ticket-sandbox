import math
import uuid
from datetime import timedelta

from django.contrib import messages
from django.contrib.admin.views.decorators import (
    staff_member_required,
)
from django.db import transaction
from django.db.models import Count, Q
from django.contrib.auth.decorators import login_required
from django.core.exceptions import (
    PermissionDenied,
    ValidationError,
)
from django.shortcuts import (
    get_object_or_404,
    redirect,
    render,
)
from django.utils import timezone
from django.views.decorators.http import require_POST

from .constants import (
    ExamAttemptStatus,
    QuestionType,
)
from .models import (
    AnswerOption,
    ExamAssignment,
    ExamAttempt,
    ExamQuestionSnapshot,
    MatchingPair,
    OrderingItem,
    SelectableLine,
    SupportProfile,
    Question,
    QuestionFamily,
    Skill,
    Topic,
)
from .services.attempts import start_exam_attempt
from .services.answers import (
    submit_exam_answer,
)
from .services.question_flow import (
    get_current_question,
    open_current_question,
)
from .services.results import (
    complete_exam_attempt,
)
from .forms import (
    AnswerOptionEditorFormSet,
    MatchingPairEditorFormSet,
    OrderingItemEditorFormSet,
    QuestionEditorForm,
    QuestionDiagnosticBlockEditorFormSet,
    QuestionFamilyEditorForm,
    SelectableLineEditorFormSet,
)


def _get_employee_profile(request):
    profile = (
        SupportProfile.objects
        .filter(
            user=request.user,
            is_active=True,
        )
        .first()
    )

    if profile is None:
        raise PermissionDenied(
            "Для пользователя не настроен "
            "профиль оценки знаний."
        )

    return profile


def _get_assignment_state(
    assignment,
    *,
    now,
):
    attempts = list(
        assignment.attempts.all()
    )

    active_attempt = next(
        (
            attempt
            for attempt in attempts
            if (
                attempt.status
                == ExamAttemptStatus.IN_PROGRESS
            )
        ),
        None,
    )

    if active_attempt:
        return {
            "code": "in_progress",
            "label": "В процессе",
            "tone": "primary",
            "description": (
                "Тест уже начат. Можно продолжить "
                "с того места, где остановились."
            ),
            "attempt": active_attempt,
        }

    campaign = assignment.campaign
    blueprint = campaign.blueprint

    if not blueprint.is_active:
        return {
            "code": "unavailable",
            "label": "Недоступен",
            "tone": "neutral",
            "description": (
                "Тест пока недоступен для прохождения."
            ),
            "attempt": None,
        }

    if not campaign.is_active:
        return {
            "code": "unavailable",
            "label": "Недоступен",
            "tone": "neutral",
            "description": (
                "Кампания тестирования пока не активна."
            ),
            "attempt": None,
        }

    if (
        campaign.opens_at
        and now < campaign.opens_at
    ):
        return {
            "code": "upcoming",
            "label": "Скоро",
            "tone": "warning",
            "description": (
                "Тест станет доступен "
                "в указанное время."
            ),
            "attempt": None,
        }

    if (
        campaign.closes_at
        and now >= campaign.closes_at
    ):
        return {
            "code": "expired",
            "label": "Срок завершён",
            "tone": "neutral",
            "description": (
                "Срок прохождения этого теста закончился."
            ),
            "attempt": None,
        }

    attempts_used = len(attempts)

    if attempts_used >= assignment.attempt_limit:
        return {
            "code": "completed",
            "label": "Завершён",
            "tone": "success",
            "description": (
                "Доступные попытки использованы. "
                "Результат сохранён."
            ),
            "attempt": (
                attempts[0]
                if attempts
                else None
            ),
        }

    if attempts_used:
        description = (
            "Доступна новая попытка."
        )
    else:
        description = (
            "Тест готов к прохождению."
        )

    return {
        "code": "available",
        "label": "Доступен",
        "tone": "success",
        "description": description,
        "attempt": None,
    }


@login_required
def dashboard(request):
    profile = _get_employee_profile(
        request
    )

    assignments = list(
        ExamAssignment.objects
        .filter(
            employee=profile,
            is_active=True,
        )
        .select_related(
            "campaign",
            "campaign__blueprint",
        )
        .prefetch_related(
            "campaign__blueprint__skill_quotas",
            "attempts",
        )
        .order_by(
            "-assigned_at",
        )
    )

    now = timezone.now()

    assignment_cards = []

    for assignment in assignments:
        state = _get_assignment_state(
            assignment,
            now=now,
        )

        attempts = list(
            assignment.attempts.all()
        )

        assignment_cards.append(
            {
                "assignment": assignment,
                "campaign": assignment.campaign,
                "blueprint": (
                    assignment.campaign.blueprint
                ),
                "state": state,
                "attempts_used": len(attempts),
            }
        )

    return render(
        request,
        "assessment/dashboard.html",
        {
            "profile": profile,
            "assignment_cards": (
                assignment_cards
            ),
        },
    )


@login_required
@require_POST
def start_assignment(
    request,
    assignment_id,
):
    profile = _get_employee_profile(
        request
    )

    assignment = get_object_or_404(
        ExamAssignment.objects.select_related(
            "campaign",
            "campaign__blueprint",
            "employee",
        ),
        pk=assignment_id,
        employee=profile,
    )

    try:
        attempt, _ = start_exam_attempt(
            assignment
        )
    except ValidationError as error:
        messages.error(
            request,
            "; ".join(error.messages),
        )

        return redirect(
            "assessment:dashboard"
        )

    return redirect(
        "assessment:attempt_overview",
        attempt_id=attempt.pk,
    )


@login_required
def attempt_overview(
    request,
    attempt_id,
):
    profile = _get_employee_profile(
        request
    )

    attempt = get_object_or_404(
        ExamAttempt.objects
        .select_related(
            "assignment",
            "assignment__campaign",
            "assignment__employee",
        ),
        pk=attempt_id,
        assignment__employee=profile,
    )

    snapshots = list(
        attempt.question_snapshots
        .order_by("position")
        .prefetch_related("answer")
    )

    answered_count = sum(
        1
        for snapshot in snapshots
        if hasattr(snapshot, "answer")
    )

    return render(
        request,
        "assessment/attempt_overview.html",
        {
            "profile": profile,
            "attempt": attempt,
            "question_count": len(snapshots),
            "answered_count": answered_count,
        },
    )


def _get_employee_attempt(
    request,
    *,
    attempt_id,
):
    profile = _get_employee_profile(
        request
    )

    return get_object_or_404(
        ExamAttempt.objects.select_related(
            "assignment",
            "assignment__campaign",
            "assignment__employee",
        ),
        pk=attempt_id,
        assignment__employee=profile,
    )


def _build_response_payload(
    request,
    snapshot,
):
    if snapshot.question_type in {
        QuestionType.SINGLE_CHOICE,
        QuestionType.MULTIPLE_CHOICE,
        QuestionType.LINE_SELECTION,
    }:
        return {
            "selected_keys": (
                request.POST.getlist(
                    "selected_keys"
                )
            ),
        }

    if (
        snapshot.question_type
        == QuestionType.MATCHING
    ):
        matches = {}

        for item in (
            snapshot.visible_payload.get(
                "left_items",
                [],
            )
        ):
            left_key = item["key"]

            right_key = request.POST.get(
                f"match_{left_key}",
                "",
            )

            if right_key:
                matches[left_key] = (
                    right_key
                )

        return {
            "matches": matches,
        }

    if (
        snapshot.question_type
        == QuestionType.ORDERING
    ):
        return {
            "order": request.POST.getlist(
                "order"
            ),
        }

    raise ValidationError(
        "Неизвестный тип вопроса."
    )


@login_required
def attempt_question(
    request,
    attempt_id,
):
    attempt = _get_employee_attempt(
        request,
        attempt_id=attempt_id,
    )

    if (
        attempt.status
        != ExamAttemptStatus.IN_PROGRESS
    ):
        return redirect(
            "assessment:attempt_overview",
            attempt_id=attempt.pk,
        )

    now = timezone.now()

    snapshot = open_current_question(
        attempt,
        now=now,
    )

    if snapshot is None:
        complete_exam_attempt(
            attempt,
            now=now,
        )

        return redirect(
            "assessment:attempt_overview",
            attempt_id=attempt.pk,
        )

    deadline = (
        snapshot.started_at
        + timedelta(
            seconds=snapshot.time_limit_seconds,
        )
    )

    remaining_seconds = max(
        0,
        math.ceil(
            (
                deadline - now
            ).total_seconds()
        ),
    )

    question_count = (
        attempt.question_snapshots.count()
    )

    answered_count = (
        attempt.question_snapshots
        .filter(
            answer__isnull=False,
        )
        .count()
    )

    return render(
        request,
        "assessment/question.html",
        {
            "attempt": attempt,
            "snapshot": snapshot,
            "question_count": question_count,
            "answered_count": answered_count,
            "remaining_milliseconds": (
                remaining_seconds * 1000
            ),
        },
    )


@login_required
@require_POST
def submit_question_answer(
    request,
    attempt_id,
    snapshot_id,
):
    attempt = _get_employee_attempt(
        request,
        attempt_id=attempt_id,
    )

    if (
        attempt.status
        != ExamAttemptStatus.IN_PROGRESS
    ):
        return redirect(
            "assessment:attempt_overview",
            attempt_id=attempt.pk,
        )

    snapshot = get_object_or_404(
        ExamQuestionSnapshot,
        pk=snapshot_id,
        attempt=attempt,
    )

    current_snapshot = get_current_question(
        attempt
    )

    if current_snapshot is None:
        complete_exam_attempt(
            attempt
        )

        return redirect(
            "assessment:attempt_overview",
            attempt_id=attempt.pk,
        )

    if current_snapshot.pk != snapshot.pk:
        messages.info(
            request,
            "Этот вопрос уже пройден.",
        )

        return redirect(
            "assessment:attempt_question",
            attempt_id=attempt.pk,
        )

    try:
        response_payload = (
            _build_response_payload(
                request,
                snapshot,
            )
        )

        answer, _ = submit_exam_answer(
            snapshot,
            response_payload=(
                response_payload
            ),
        )

    except ValidationError as error:
        messages.error(
            request,
            "; ".join(error.messages),
        )

        return redirect(
            "assessment:attempt_question",
            attempt_id=attempt.pk,
        )

    if answer.timed_out:
        messages.info(
            request,
            "Время на вопрос закончилось. "
            "Переходим дальше.",
        )

    next_snapshot = get_current_question(
        attempt
    )

    if next_snapshot is None:
        complete_exam_attempt(
            attempt
        )

        return redirect(
            "assessment:attempt_overview",
            attempt_id=attempt.pk,
        )

    return redirect(
        "assessment:attempt_question",
        attempt_id=attempt.pk,
    )


@staff_member_required
def mentor_question_list(request):
    questions = (
        Question.objects
        .select_related(
            "family",
            "family__skill",
            "family__skill__topic",
        )
        .order_by(
            "family__skill__topic__order",
            "family__skill__order",
            "family__order",
            "order",
            "title",
        )
    )

    query = request.GET.get(
        "q",
        "",
    ).strip()

    level = request.GET.get(
        "level",
        "",
    ).strip()

    topic_slug = request.GET.get(
        "topic",
        "",
    ).strip()

    status = request.GET.get(
        "status",
        "",
    ).strip()

    if query:
        questions = questions.filter(
            Q(title__icontains=query)
            | Q(prompt__icontains=query)
            | Q(scenario__icontains=query)
            | Q(diagnostic_data__icontains=query)
            | Q(family__name__icontains=query)
            | Q(family__skill__name__icontains=query)
        )

    if level:
        questions = questions.filter(
            level=level,
        )

    if topic_slug:
        questions = questions.filter(
            family__skill__topic__slug=topic_slug,
        )

    if status:
        questions = questions.filter(
            status=status,
        )

    topics = (
        Topic.objects
        .filter(is_active=True)
        .order_by(
            "order",
            "name",
        )
    )

    return render(
        request,
        "assessment/mentor/question_list.html",
        {
            "questions": questions,
            "question_count": questions.count(),
            "topics": topics,
            "filters": {
                "q": query,
                "level": level,
                "topic": topic_slug,
                "status": status,
            },
        },
    )


def _editor_answer_type(
    request,
    question,
):
    if request.method == "POST":
        return request.POST.get(
            "answer_type",
            QuestionType.SINGLE_CHOICE,
        )

    if question.pk:
        return question.answer_type

    return QuestionType.SINGLE_CHOICE


def _build_question_formsets(
    request,
    *,
    question,
    answer_type,
):
    post_data = (
        request.POST
        if request.method == "POST"
        else None
    )

    choice_data = (
        post_data
        if answer_type in {
            QuestionType.SINGLE_CHOICE,
            QuestionType.MULTIPLE_CHOICE,
        }
        else None
    )

    matching_data = (
        post_data
        if answer_type
        == QuestionType.MATCHING
        else None
    )

    ordering_data = (
        post_data
        if answer_type
        == QuestionType.ORDERING
        else None
    )

    lines_data = (
        post_data
        if answer_type
        == QuestionType.LINE_SELECTION
        else None
    )

    diagnostic_data = (
        post_data
        if (
            post_data is not None
            and "diagnostics-TOTAL_FORMS"
            in post_data
        )
        else None
    )

    return {
        "options": (
            AnswerOptionEditorFormSet(
                choice_data,
                instance=question,
                prefix="options",
            )
        ),
        "matching": (
            MatchingPairEditorFormSet(
                matching_data,
                instance=question,
                prefix="matching",
            )
        ),
        "ordering": (
            OrderingItemEditorFormSet(
                ordering_data,
                instance=question,
                prefix="ordering",
            )
        ),
        "lines": (
            SelectableLineEditorFormSet(
                lines_data,
                instance=question,
                prefix="lines",
            )
        ),
        "diagnostics": (
            QuestionDiagnosticBlockEditorFormSet(
                diagnostic_data,
                instance=question,
                prefix="diagnostics",
            )
        ),
    }


def _active_question_formset(
    formsets,
    answer_type,
):
    if answer_type in {
        QuestionType.SINGLE_CHOICE,
        QuestionType.MULTIPLE_CHOICE,
    }:
        return formsets["options"]

    if answer_type == QuestionType.MATCHING:
        return formsets["matching"]

    if answer_type == QuestionType.ORDERING:
        return formsets["ordering"]

    if answer_type == QuestionType.LINE_SELECTION:
        return formsets["lines"]

    return None


def _delete_unused_question_configuration(
    question,
):
    if question.answer_type not in {
        QuestionType.SINGLE_CHOICE,
        QuestionType.MULTIPLE_CHOICE,
    }:
        AnswerOption.objects.filter(
            question=question
        ).delete()

    if (
        question.answer_type
        != QuestionType.MATCHING
    ):
        MatchingPair.objects.filter(
            question=question
        ).delete()

    if (
        question.answer_type
        != QuestionType.ORDERING
    ):
        OrderingItem.objects.filter(
            question=question
        ).delete()

    if (
        question.answer_type
        != QuestionType.LINE_SELECTION
    ):
        SelectableLine.objects.filter(
            question=question
        ).delete()


def _mentor_question_editor(
    request,
    *,
    question,
):
    answer_type = _editor_answer_type(
        request,
        question,
    )

    form = QuestionEditorForm(
        request.POST or None,
        instance=question,
    )

    formsets = _build_question_formsets(
        request,
        question=question,
        answer_type=answer_type,
    )

    if request.method == "POST":
        form_valid = form.is_valid()

        if form_valid:
            candidate = form.save(
                commit=False
            )

            if not candidate.slug:
                candidate.slug = (
                    "question-"
                    + uuid.uuid4().hex[:12]
                )

            for formset in formsets.values():
                formset.instance = candidate

            active_formset = (
                _active_question_formset(
                    formsets,
                    candidate.answer_type,
                )
            )

            diagnostic_formset = (
                formsets["diagnostics"]
            )

            answer_formset_valid = (
                active_formset is not None
                and active_formset.is_valid()
            )

            diagnostic_formset_valid = (
                not diagnostic_formset.is_bound
                or diagnostic_formset.is_valid()
            )

            if (
                answer_formset_valid
                and diagnostic_formset_valid
            ):
                with transaction.atomic():
                    candidate.save()

                    active_formset.instance = (
                        candidate
                    )

                    active_formset.save()

                    if diagnostic_formset.is_bound:
                        diagnostic_formset.instance = (
                            candidate
                        )

                        diagnostic_formset.save()

                    _delete_unused_question_configuration(
                        candidate
                    )

                messages.success(
                    request,
                    "Вопрос сохранён.",
                )

                return redirect(
                    "assessment:mentor_question_edit",
                    question_id=candidate.pk,
                )

    return render(
        request,
        "assessment/mentor/question_form.html",
        {
            "question": question,
            "form": form,
            "formsets": formsets,
            "selected_answer_type": (
                answer_type
            ),
        },
    )


@staff_member_required
def mentor_question_create(request):
    return _mentor_question_editor(
        request,
        question=Question(),
    )


@staff_member_required
def mentor_question_edit(
    request,
    question_id,
):
    question = get_object_or_404(
        Question.objects.select_related(
            "family",
            "family__skill",
            "family__skill__topic",
        ),
        pk=question_id,
    )

    return _mentor_question_editor(
        request,
        question=question,
    )


@staff_member_required
def mentor_family_list(request):
    families = (
        QuestionFamily.objects
        .select_related(
            "skill",
            "skill__topic",
        )
        .annotate(
            question_count=Count(
                "questions"
            )
        )
        .order_by(
            "skill__topic__order",
            "skill__order",
            "order",
            "name",
        )
    )

    query = request.GET.get(
        "q",
        "",
    ).strip()

    topic_slug = request.GET.get(
        "topic",
        "",
    ).strip()

    status = request.GET.get(
        "status",
        "",
    ).strip()

    if query:
        families = families.filter(
            Q(name__icontains=query)
            | Q(
                assessment_goal__icontains=query
            )
            | Q(
                skill__name__icontains=query
            )
        )

    if topic_slug:
        families = families.filter(
            skill__topic__slug=topic_slug,
        )

    if status == "active":
        families = families.filter(
            is_active=True,
        )

    elif status == "inactive":
        families = families.filter(
            is_active=False,
        )

    topics = (
        Topic.objects
        .filter(is_active=True)
        .order_by(
            "order",
            "name",
        )
    )

    return render(
        request,
        "assessment/mentor/family_list.html",
        {
            "families": families,
            "family_count": families.count(),
            "topics": topics,
            "filters": {
                "q": query,
                "topic": topic_slug,
                "status": status,
            },
        },
    )


def _mentor_family_editor(
    request,
    *,
    family,
):
    form = QuestionFamilyEditorForm(
        request.POST or None,
        instance=family,
    )

    if (
        request.method == "POST"
        and form.is_valid()
    ):
        family = form.save(
            commit=False
        )

        if not family.slug:
            family.slug = (
                "family-"
                + uuid.uuid4().hex[:12]
            )

        family.save()

        messages.success(
            request,
            "Семейство сохранено.",
        )

        return redirect(
            "assessment:mentor_family_edit",
            family_id=family.pk,
        )

    return render(
        request,
        "assessment/mentor/family_form.html",
        {
            "family": family,
            "form": form,
        },
    )


@staff_member_required
def mentor_family_create(request):
    return _mentor_family_editor(
        request,
        family=QuestionFamily(),
    )


@staff_member_required
def mentor_family_edit(
    request,
    family_id,
):
    family = get_object_or_404(
        QuestionFamily.objects
        .select_related(
            "skill",
            "skill__topic",
        ),
        pk=family_id,
    )

    return _mentor_family_editor(
        request,
        family=family,
    )
