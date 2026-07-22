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


class EditTraineeForm(forms.Form):
    first_name = forms.CharField(
        label="Имя",
        max_length=150,
    )

    last_name = forms.CharField(
        label="Фамилия",
        max_length=150,
    )

    entry_type = forms.ChoiceField(
        label="Тип входа",
        choices=EntryType.choices,
        widget=forms.RadioSelect,
    )

    probation_start_date = forms.DateField(
        label="Дата старта ИС",
        widget=forms.DateInput(
            attrs={
                "type": "date",
            },
        ),
    )

    comment = forms.CharField(
        label="Комментарий наставника",
        required=False,
        widget=forms.Textarea(
            attrs={
                "rows": 4,
            },
        ),
    )

    is_active = forms.BooleanField(
        label="Аккаунт активен",
        required=False,
    )

    def __init__(
        self,
        *args,
        journey,
        **kwargs,
    ):
        self.journey = journey

        super().__init__(
            *args,
            **kwargs,
        )

        if not self.is_bound:
            self.initial.update({
                "first_name": (
                    journey.user.first_name
                ),
                "last_name": (
                    journey.user.last_name
                ),
                "entry_type": (
                    journey.entry_type
                ),
                "probation_start_date": (
                    journey.probation_start_date
                ),
                "comment": journey.comment,
                "is_active": (
                    journey.user.is_active
                ),
            })

    def _can_shift_initial_stage_start(self):
        """
        Если сотрудник ещё ни разу не переходил
        между этапами, изменение даты начала ИС
        также меняет дату начала первого этапа.
        """
        if (
            self.journey.stage_started_at
            != self.journey.probation_start_date
        ):
            return False

        history_entries = (
            self.journey.stage_history
            .filter(
                stage=self.journey.current_stage,
                ended_at__isnull=True,
            )
        )

        return (
            self.journey.stage_history.count() == 1
            and history_entries.exists()
        )

    def clean(self):
        cleaned_data = super().clean()

        entry_type = cleaned_data.get(
            "entry_type",
        )

        probation_start_date = (
            cleaned_data.get(
                "probation_start_date",
            )
        )

        if (
            entry_type
            and not (
                self.journey.current_stage
                .applies_to_entry_type(
                    entry_type,
                )
            )
        ):
            self.add_error(
                "entry_type",
                (
                    "Текущий этап не применим "
                    "к выбранному типу входа."
                ),
            )

        if (
            probation_start_date
            and probation_start_date
            > timezone.localdate()
        ):
            self.add_error(
                "probation_start_date",
                (
                    "Дата начала испытательного срока "
                    "не может быть в будущем."
                ),
            )

        if (
            probation_start_date
            and not (
                self._can_shift_initial_stage_start()
            )
            and probation_start_date
            > self.journey.stage_started_at
        ):
            self.add_error(
                "probation_start_date",
                (
                    "Дата начала испытательного срока "
                    "не может быть позже начала "
                    "текущего этапа."
                ),
            )

        return cleaned_data

    @transaction.atomic
    def save(self):
        journey = self.journey
        user = journey.user

        old_probation_start_date = (
            journey.probation_start_date
        )

        new_probation_start_date = (
            self.cleaned_data[
                "probation_start_date"
            ]
        )

        shift_initial_stage = (
            self._can_shift_initial_stage_start()
            and (
                old_probation_start_date
                != new_probation_start_date
            )
        )

        user.first_name = self.cleaned_data[
            "first_name"
        ]
        user.last_name = self.cleaned_data[
            "last_name"
        ]
        user.is_active = self.cleaned_data[
            "is_active"
        ]

        user.save(
            update_fields=[
                "first_name",
                "last_name",
                "is_active",
            ],
        )

        journey.entry_type = self.cleaned_data[
            "entry_type"
        ]
        journey.probation_start_date = (
            new_probation_start_date
        )
        journey.comment = self.cleaned_data.get(
            "comment",
            "",
        )

        update_fields = [
            "entry_type",
            "probation_start_date",
            "comment",
        ]

        if shift_initial_stage:
            journey.stage_started_at = (
                new_probation_start_date
            )

            update_fields.append(
                "stage_started_at",
            )

        journey.full_clean()

        journey.save(
            update_fields=update_fields,
        )

        if shift_initial_stage:
            journey.stage_history.filter(
                stage=journey.current_stage,
                ended_at__isnull=True,
            ).update(
                started_at=(
                    new_probation_start_date
                ),
            )

        return journey


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
            "mentor_comment": forms.Textarea(
                attrs={
                    "class": (
                        "weekly-metric-feedback-input"
                    ),
                    "rows": 3,
                    "placeholder": (
                        "Что получилось, где были сложности"
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
