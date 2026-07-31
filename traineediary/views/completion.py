from django.contrib import messages
from django.contrib.auth.decorators import (
    login_required,
)
from django.core.exceptions import (
    PermissionDenied,
    ValidationError,
)
from django.shortcuts import (
    get_object_or_404,
    redirect,
    render,
)

from ..forms import CompleteProbationForm
from ..models import TraineeJourney


@login_required
def complete_trainee(
    request,
    journey_id,
):
    if not request.user.is_staff:
        raise PermissionDenied

    journey = get_object_or_404(
        TraineeJourney.objects.select_related(
            "user",
            "current_stage",
            "completed_by",
        ),
        pk=journey_id,
    )

    if journey.completion_status:
        messages.info(
            request,
            (
                "Испытательный срок этого "
                "сотрудника уже завершён."
            ),
        )

        return redirect(
            "traineediary:trainee_detail",
            journey.id,
        )

    if request.method == "POST":
        form = CompleteProbationForm(
            request.POST,
            journey=journey,
        )

        if form.is_valid():
            try:
                journey.complete_probation(
                    status=(
                        form.cleaned_data[
                            "completion_status"
                        ]
                    ),
                    completed_at=(
                        form.cleaned_data[
                            "completed_at"
                        ]
                    ),
                    completed_by=request.user,
                    comment=(
                        form.cleaned_data[
                            "completion_comment"
                        ]
                    ),
                )

            except ValidationError as error:
                if hasattr(
                    error,
                    "message_dict",
                ):
                    for field, error_messages in (
                        error.message_dict.items()
                    ):
                        form_field = (
                            field
                            if field in form.fields
                            else None
                        )

                        for error_message in (
                            error_messages
                        ):
                            form.add_error(
                                form_field,
                                error_message,
                            )
                else:
                    form.add_error(
                        None,
                        error,
                    )

            else:
                messages.success(
                    request,
                    (
                        "Испытательный срок "
                        "успешно завершён."
                    ),
                )

                return redirect(
                    "traineediary:trainee_detail",
                    journey.id,
                )

    else:
        form = CompleteProbationForm(
            journey=journey,
        )

    return render(
        request,
        (
            "traineediary/"
            "complete_trainee.html"
        ),
        {
            "journey": journey,
            "form": form,
        },
    )
