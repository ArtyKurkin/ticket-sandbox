from django.contrib import messages
from django.contrib.auth.decorators import (
    login_required,
)
from django.core.exceptions import (
    PermissionDenied,
)
from django.shortcuts import (
    get_object_or_404,
    redirect,
    render,
)

from ..forms import (
    EditTraineeForm,
    NewTraineeForm,
    StartAdaptationForm,
)
from ..models import (
    EntryType,
    TraineeJourney,
)
from ..queries import (
    get_pre_adaptation_users_queryset,
)
from ..services.sandbox_progress import (
    build_sandbox_queue_progress,
    build_sandbox_queue_progress_map,
)


@login_required
def start_adaptation(
    request,
    user_id,
):
    if not request.user.is_staff:
        raise PermissionDenied

    trainee_user = get_object_or_404(
        get_pre_adaptation_users_queryset().filter(
            is_active=True,
        ),
        pk=user_id,
    )

    sandbox_l1_progress = (
        build_sandbox_queue_progress(
            user=trainee_user,
            queue_slug="l1",
        )
    )

    if request.method == "POST":
        form = StartAdaptationForm(
            request.POST,
            user=trainee_user,
        )

        if form.is_valid():
            journey = form.save(
                changed_by=request.user,
            )

            messages.success(
                request,
                (
                    f"Адаптация для "
                    f"{trainee_user.get_full_name() or trainee_user.username} "
                    f"начата."
                ),
            )

            return redirect(
                "traineediary:trainee_detail",
                journey_id=journey.id,
            )

    else:
        form = StartAdaptationForm(
            user=trainee_user,
        )

    return render(
        request,
        (
            "traineediary/"
            "start_adaptation.html"
        ),
        {
            "form": form,
            "trainee_user": trainee_user,
            "sandbox_l1_progress": (
                sandbox_l1_progress
            ),
        },
    )


@login_required
def pre_adaptation_users(request):
    if not request.user.is_staff:
        raise PermissionDenied

    users = list(
        get_pre_adaptation_users_queryset()
    )

    sandbox_progress_by_user_id = (
        build_sandbox_queue_progress_map(
            users=users,
            queue_slug="l1",
        )
    )

    for trainee_user in users:
        # Атрибут используется только при
        # отображении страницы и не сохраняется
        # в базе данных.
        trainee_user.sandbox_l1_progress = (
            sandbox_progress_by_user_id[
                trainee_user.id
            ]
        )

    return render(
        request,
        (
            "traineediary/"
            "pre_adaptation_users.html"
        ),
        {
            "pre_adaptation_users": users,
        },
    )


@login_required
def create_trainee(request):
    if not request.user.is_staff:
        raise PermissionDenied

    if request.method == "POST":
        form = NewTraineeForm(
            request.POST,
        )

        if form.is_valid():
            (
                user,
                journey,
                generated_password,
            ) = form.save(
                changed_by=request.user,
            )

            is_adaptation = (
                journey is not None
            )

            return render(
                request,
                (
                    "traineediary/"
                    "trainee_created.html"
                ),
                {
                    "user": user,
                    "journey": journey,
                    "password": (
                        generated_password
                    ),
                    "is_adaptation": (
                        is_adaptation
                    ),
                    "account_type_label": (
                        "Новая адаптация"
                        if is_adaptation
                        else (
                            "Сотрудник "
                            "из другого отдела"
                        )
                    ),
                },
            )

    else:
        form = NewTraineeForm()

    return render(
        request,
        (
            "traineediary/"
            "create_trainee.html"
        ),
        {
            "form": form,
            "internal_transfer_value": (
                EntryType.INTERNAL_TRANSFER
            ),
        },
    )


@login_required
def edit_trainee(
    request,
    journey_id,
):
    if not request.user.is_staff:
        raise PermissionDenied

    journey = get_object_or_404(
        TraineeJourney.objects
        .select_related(
            "user",
            "current_stage",
        ),
        id=journey_id,
    )

    if request.method == "POST":
        form = EditTraineeForm(
            request.POST,
            journey=journey,
        )

        if form.is_valid():
            journey = form.save()

            messages.success(
                request,
                (
                    f"Карточка сотрудника "
                    f"«{journey}» обновлена."
                ),
            )

            return redirect(
                "traineediary:trainee_detail",
                journey_id=journey.id,
            )

    else:
        form = EditTraineeForm(
            journey=journey,
        )

    return render(
        request,
        (
            "traineediary/"
            "edit_trainee.html"
        ),
        {
            "journey": journey,
            "form": form,
        },
    )
