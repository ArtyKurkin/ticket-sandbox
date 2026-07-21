import secrets

from django import forms
from django.db import transaction
from django.contrib.auth.models import User
from django.utils import timezone

from .models import (
    EntryType,
    TraineeJourney,
    TraineeStage,
    WeeklyMetric,
)
from sandbox.models import TraineeProfile


class NewTraineeForm(forms.Form):
    first_name = forms.CharField(label="Имя", max_length=150)
    last_name = forms.CharField(label="Фамилия", max_length=150)
    username = forms.CharField(label="Логин (для входа в систему)", max_length=150)
    entry_type = forms.ChoiceField(
        label="Тип входа", choices=EntryType.choices, widget=forms.RadioSelect,
    )
    probation_start_date = forms.DateField(
        label="Дата старта ИС",
        initial=timezone.now().date,
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    current_stage = forms.ModelChoiceField(
        label="Текущий этап",
        queryset=TraineeStage.objects.filter(is_active=True).order_by("order"),
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    comment = forms.CharField(
        label="Комментарий", required=False, widget=forms.Textarea(attrs={"rows": 3}),
    )

    def clean_username(self):
        username = self.cleaned_data["username"].strip()
        if User.objects.filter(username=username).exists():
            raise forms.ValidationError("Такой логин уже занят.")
        return username

    def clean(self):
        cleaned_data = super().clean()
        entry_type = cleaned_data.get("entry_type")
        stage = cleaned_data.get("current_stage")
        if entry_type and stage and not stage.applies_to_entry_type(entry_type):
            self.add_error(
                "current_stage",
                "Этот этап не применим к выбранному типу входа.",
            )
        return cleaned_data

    @transaction.atomic
    def save(self):
        generated_password = secrets.token_urlsafe(9)

        user = User.objects.create_user(
            username=self.cleaned_data["username"],
            first_name=self.cleaned_data["first_name"],
            last_name=self.cleaned_data["last_name"],
            password=generated_password,
        )

        TraineeProfile.objects.update_or_create(
            user=user,
            defaults={
                "level": TraineeProfile.Level.L1,
            },
        )

        stage = self.cleaned_data["current_stage"]
        probation_start_date = self.cleaned_data["probation_start_date"]

        journey = TraineeJourney.objects.create(
            user=user,
            entry_type=self.cleaned_data["entry_type"],
            probation_start_date=probation_start_date,
            current_stage=stage,
            stage_started_at=probation_start_date,
            comment=self.cleaned_data.get("comment", ""),
        )

        return journey, generated_password


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
            self.fields["quality_percent"].required = True
        else:
            # Полностью исключаем поле из формы.
            # Даже если его передадут вручную в POST,
            # старое значение качества не изменится.
            self.fields.pop(
                "quality_percent",
                None,
            )

    class Meta:
        model = WeeklyMetric
        fields = (
            "speed_hours",
            "quality_percent",
        )
        labels = {
            "speed_hours": "Скорость",
            "quality_percent": "Качество",
        }
        widgets = {
            "speed_hours": forms.NumberInput(
                attrs={
                    "class": "weekly-metric-input",
                    "min": "0",
                    "step": "0.1",
                    "inputmode": "decimal",
                    "placeholder": "6.0",
                },
            ),
            "quality_percent": forms.NumberInput(
                attrs={
                    "class": "weekly-metric-input",
                    "min": "0",
                    "max": "100",
                    "step": "1",
                    "inputmode": "numeric",
                    "placeholder": "80",
                },
            ),
        }

    def clean(self):
        cleaned_data = super().clean()

        if cleaned_data.get("speed_hours") is None:
            self.add_error(
                "speed_hours",
                "Заполни скорость.",
            )

        if (
            self.quality_required
            and cleaned_data.get(
                "quality_percent",
            ) is None
        ):
            self.add_error(
                "quality_percent",
                "Заполни качество.",
            )

        return cleaned_data
