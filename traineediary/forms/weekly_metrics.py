from django import forms

from ..models import WeeklyMetric


class WeeklyMetricForm(forms.ModelForm):
    def __init__(
        self,
        *args,
        quality_required=True,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)

        self.quality_required = quality_required
        self.fields["speed_hours"].required = True

        if quality_required:
            self.fields[
                "quality_percent"
            ].required = True
        else:
            # Полностью исключаем поле из формы.
            # Даже если его передадут вручную
            # в POST, старое значение качества
            # не изменится.
            self.fields.pop(
                "quality_percent",
                None,
            )

    class Meta:
        model = WeeklyMetric

        fields = (
            "speed_hours",
            "quality_percent",
            "mentor_comment",
            "next_week_goal",
        )

        labels = {
            "speed_hours": "Скорость",
            "quality_percent": "Качество",
            "mentor_comment": "Итоги недели",
            "next_week_goal": (
                "Цель на следующую неделю"
            ),
        }

        widgets = {
            "speed_hours": forms.NumberInput(
                attrs={
                    "class": (
                        "weekly-metric-input"
                    ),
                    "min": "0",
                    "step": "0.1",
                    "inputmode": "decimal",
                    "placeholder": "6.0",
                },
            ),
            "quality_percent": (
                forms.NumberInput(
                    attrs={
                        "class": (
                            "weekly-metric-input"
                        ),
                        "min": "0",
                        "max": "100",
                        "step": "1",
                        "inputmode": "numeric",
                        "placeholder": "80",
                    },
                )
            ),
            "mentor_comment": forms.Textarea(
                attrs={
                    "class": (
                        "weekly-metric-feedback-input"
                    ),
                    "rows": 3,
                    "placeholder": (
                        "Что получилось, "
                        "где были сложности"
                    ),
                },
            ),
            "next_week_goal": forms.Textarea(
                attrs={
                    "class": (
                        "weekly-metric-feedback-input"
                    ),
                    "rows": 3,
                    "placeholder": (
                        "На чём сделать упор "
                        "на следующей неделе"
                    ),
                },
            ),
        }

    def clean(self):
        cleaned_data = super().clean()

        if (
            cleaned_data.get(
                "speed_hours",
            )
            is None
        ):
            self.add_error(
                "speed_hours",
                "Заполни скорость.",
            )

        if (
            self.quality_required
            and cleaned_data.get(
                "quality_percent",
            )
            is None
        ):
            self.add_error(
                "quality_percent",
                "Заполни качество.",
            )

        return cleaned_data
