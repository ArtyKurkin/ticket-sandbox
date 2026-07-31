from django import forms
from django.utils import timezone

from ..models import (
    CompletionStatus,
    TraineeJourney,
)


class CompleteProbationForm(forms.Form):
    completion_status = forms.ChoiceField(
        label="Результат испытательного срока",
        choices=CompletionStatus.choices,
        widget=forms.Select(
            attrs={
                "class": (
                    "trainee-completion-control"
                ),
            },
        ),
    )

    completed_at = forms.DateField(
        label="Дата завершения",
        widget=forms.DateInput(
            attrs={
                "type": "date",
                "class": (
                    "trainee-completion-control"
                ),
            },
        ),
    )

    completion_comment = forms.CharField(
        label="Итоговый комментарий",
        required=False,
        widget=forms.Textarea(
            attrs={
                "rows": 6,
                "class": (
                    "trainee-completion-control"
                ),
                "placeholder": (
                    "Кратко подведи итоги "
                    "испытательного срока"
                ),
            },
        ),
    )

    def __init__(
        self,
        *args,
        journey: TraineeJourney,
        **kwargs,
    ):
        super().__init__(
            *args,
            **kwargs,
        )

        self.journey = journey
        today = timezone.localdate()

        self.fields[
            "completion_status"
        ].initial = CompletionStatus.SUCCESS

        self.fields[
            "completed_at"
        ].initial = today

        self.fields[
            "completed_at"
        ].widget.attrs.update(
            {
                "min": (
                    journey
                    .probation_start_date
                    .isoformat()
                ),
                "max": today.isoformat(),
            },
        )

    def clean_completed_at(self):
        completed_at = self.cleaned_data[
            "completed_at"
        ]

        if (
            completed_at
            < self.journey.probation_start_date
        ):
            raise forms.ValidationError(
                "Дата завершения не может быть "
                "раньше даты начала ИС.",
            )

        if completed_at > timezone.localdate():
            raise forms.ValidationError(
                "Дата завершения не может быть "
                "в будущем.",
            )

        return completed_at

    def clean(self):
        cleaned_data = super().clean()

        status = cleaned_data.get(
            "completion_status",
        )

        comment = (
            cleaned_data.get(
                "completion_comment",
            )
            or ""
        ).strip()

        cleaned_data[
            "completion_comment"
        ] = comment

        if (
            status
            == CompletionStatus.TERMINATED
            and not comment
        ):
            self.add_error(
                "completion_comment",
                (
                    "При прекращении "
                    "испытательного срока "
                    "укажи причину."
                ),
            )

        return cleaned_data
