from datetime import timedelta

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.db.models import Sum
from django.utils import timezone


class StageGroup(models.TextChoices):
    TEACHBASE = "teachbase", "Teachbase"
    SANDBOX_CANDIDATE = "sandbox_candidate", "Задания в ticket-sandbox"
    WITH_REVIEW = "with_review", "В тикетах с проверками"
    OPTIONAL_REVIEW = "optional_review", "Кнопка по желанию"
    NO_REVIEW = "no_review", "Без проверок"
    DONE = "done", "Завершено"


class EntryType(models.TextChoices):
    NEW_HIRE = "new_hire", "Новая адаптация"
    INTERNAL_TRANSFER = "internal_transfer", "Внутренний переход"


class RiskLevel(models.TextChoices):
    LOW = "low", "Низкий"
    MEDIUM = "medium", "Средний"
    HIGH = "high", "Высокий"


# Срок испытательного срока зависит от типа входа:
# внешний найм — 90 дней, внутренний переход — 30 дней.
PROBATION_DAYS_BY_ENTRY_TYPE = {
    EntryType.NEW_HIRE: 90,
    EntryType.INTERNAL_TRANSFER: 30,
}


class TraineeStage(models.Model):
    name = models.CharField(max_length=100)
    slug = models.SlugField(unique=True)
    order = models.PositiveIntegerField()
    min_days = models.PositiveIntegerField(default=1)
    max_days = models.PositiveIntegerField(default=100)
    progress_weight_percent = models.PositiveIntegerField(default=0)
    color = models.CharField(max_length=7, default="#9CA3AF")
    group = models.CharField(max_length=32, choices=StageGroup.choices)
    is_active = models.BooleanField(default=True)

    # Внутренний переход приходит на ИС уже с пройденным Teachbase
    # и заданиями в ticket-sandbox — эти этапы для него неприменимы.
    applies_to_new_hire = models.BooleanField(
        default=True, verbose_name="Актуален для внешнего найма",
    )
    applies_to_internal_transfer = models.BooleanField(
        default=True, verbose_name="Актуален для внутреннего перехода",
    )

    class Meta:
        ordering = ["order"]
        verbose_name = "Этап обучения"
        verbose_name_plural = "Этапы обучения"

    def __str__(self):
        return self.name

    def applies_to_entry_type(self, entry_type):
        if entry_type == EntryType.INTERNAL_TRANSFER:
            return self.applies_to_internal_transfer
        return self.applies_to_new_hire


class TraineeJourney(models.Model):
    user = models.OneToOneField(
        User, on_delete=models.CASCADE, related_name="trainee_journey",
    )
    entry_type = models.CharField(max_length=32, choices=EntryType.choices)
    probation_start_date = models.DateField(verbose_name="Дата старта ИС")
    current_stage = models.ForeignKey(
        TraineeStage, on_delete=models.PROTECT, related_name="+",
    )
    stage_started_at = models.DateField(verbose_name="Дата начала этапа")
    comment = models.TextField(blank=True)
    manual_risk_override = models.CharField(
        max_length=16, choices=RiskLevel.choices, blank=True,
        verbose_name="Риск (ручной override)",
    )

    class Meta:
        verbose_name = "Карточка стажёра"
        verbose_name_plural = "Карточки стажёров"

    def __str__(self):
        return self.user.get_full_name() or self.user.username

    def clean(self):
        if self.current_stage_id and not self.current_stage.applies_to_entry_type(self.entry_type):
            raise ValidationError(
                {"current_stage": "Этот этап не применим к выбранному типу входа."},
            )

    def save(self, *args, **kwargs):
        is_new = self._state.adding
        super().save(*args, **kwargs)
        if is_new:
            StageHistory.objects.create(
                journey=self,
                stage=self.current_stage,
                started_at=self.stage_started_at,
            )

    # --- сроки ---

    @property
    def probation_days_total(self):
        return PROBATION_DAYS_BY_ENTRY_TYPE.get(self.entry_type, 90)

    @property
    def days_total(self):
        return (timezone.now().date() - self.probation_start_date).days

    @property
    def days_left_until_probation_end(self):
        return max(self.probation_days_total - self.days_total, 0)

    @property
    def days_on_stage(self):
        return (timezone.now().date() - self.stage_started_at).days

    @property
    def expected_stage_transition_date(self):
        return self.stage_started_at + timedelta(days=self.current_stage.max_days)

    # --- риск ---

    @property
    def stage_overstay_ratio(self):
        return self.days_on_stage / max(self.current_stage.max_days, 1)

    @property
    def risk_level(self):
        if self.manual_risk_override:
            return self.manual_risk_override
        if self.current_stage.group == StageGroup.DONE:
            return None
        ratio = self.stage_overstay_ratio
        if ratio <= 1.0:
            return RiskLevel.LOW
        if ratio <= 1.3:
            return RiskLevel.MEDIUM
        return RiskLevel.HIGH

    # --- прогресс ---

    def _applicable_stages(self):
        field_name = (
            "applies_to_internal_transfer"
            if self.entry_type == EntryType.INTERNAL_TRANSFER
            else "applies_to_new_hire"
        )
        return TraineeStage.objects.filter(**{field_name: True})

    @property
    def progress_percent(self):
        applicable = self._applicable_stages()

        total_weight = applicable.aggregate(
            total=Sum("progress_weight_percent"),
        )["total"] or 1

        weight_before = applicable.filter(
            order__lt=self.current_stage.order,
        ).aggregate(total=Sum("progress_weight_percent"))["total"] or 0

        current_weight = (
            self.current_stage.progress_weight_percent
            if applicable.filter(pk=self.current_stage.pk).exists()
            else 0
        )

        stage_fraction = min(
            self.days_on_stage / max(self.current_stage.max_days, 1), 1,
        )

        raw = weight_before + current_weight * stage_fraction
        return round(raw / total_weight * 100)

    @property
    def auto_status(self):
        if self.current_stage.group == StageGroup.DONE:
            return "Готов"
        return self.current_stage.name

    # --- смена этапа ---

    def move_to_stage(
        self,
        new_stage,
        changed_by=None,
        note="",
        transition_date=None,
    ):
        """
        Единая точка смены этапа.

        Повторный перенос в текущий этап ничего не меняет.
        Дату перехода можно указать вручную для корректной истории.
        Обновление карточки и StageHistory выполняется одной транзакцией.
        """
        previous_stage = self.current_stage
        previous_stage_started_at = self.stage_started_at

        # Drag-and-drop может отправить запрос в текущую колонку.
        # Не сбрасываем дату и не создаём дубликат истории.
        if self.current_stage_id == new_stage.pk:
            return previous_stage

        transition_date = transition_date or timezone.localdate()
        today = timezone.localdate()

        if transition_date > today:
            raise ValidationError(
                {
                    "stage_started_at": (
                        "Дата начала нового этапа не может быть в будущем."
                    ),
                },
            )

        if transition_date < self.stage_started_at:
            raise ValidationError(
                {
                    "stage_started_at": (
                        "Дата начала нового этапа не может быть раньше "
                        "даты начала текущего этапа."
                    ),
                },
            )

        try:
            with transaction.atomic():
                self.current_stage = new_stage
                self.stage_started_at = transition_date

                # Проверяем применимость этапа к типу входа.
                # Внутреннему переходу недоступны Teachbase и ticket-sandbox.
                self.full_clean()

                StageHistory.objects.filter(
                    journey=self,
                    ended_at__isnull=True,
                ).update(ended_at=transition_date)

                self.save(
                    update_fields=[
                        "current_stage",
                        "stage_started_at",
                    ],
                )

                StageHistory.objects.create(
                    journey=self,
                    stage=new_stage,
                    started_at=transition_date,
                    changed_by=changed_by,
                    note=note.strip(),
                )

        except Exception:
            # Транзакция откатывает БД, но не значения внутри self.
            self.current_stage = previous_stage
            self.stage_started_at = previous_stage_started_at
            raise

        return previous_stage


class StageHistory(models.Model):
    journey = models.ForeignKey(
        TraineeJourney, on_delete=models.CASCADE, related_name="stage_history",
    )
    stage = models.ForeignKey(TraineeStage, on_delete=models.PROTECT)
    started_at = models.DateField()
    ended_at = models.DateField(null=True, blank=True)
    changed_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, related_name="+",
    )
    note = models.TextField(blank=True)

    class Meta:
        ordering = ["-started_at"]
        verbose_name = "История этапов"
        verbose_name_plural = "История этапов"

    def __str__(self):
        return f"{self.journey} — {self.stage} ({self.started_at})"


class WeeklyMetric(models.Model):
    journey = models.ForeignKey(
        TraineeJourney, on_delete=models.CASCADE, related_name="weekly_metrics",
    )
    week_number = models.PositiveIntegerField()
    week_start_date = models.DateField(null=True, blank=True)
    speed_hours = models.DecimalField(
        max_digits=5, decimal_places=1, null=True, blank=True,
    )
    quality_percent = models.PositiveIntegerField(null=True, blank=True)

    class Meta:
        unique_together = ("journey", "week_number")
        ordering = ["week_number"]
        verbose_name = "Недельная метрика"
        verbose_name_plural = "Недельные метрики"

    def __str__(self):
        return f"{self.journey} — неделя {self.week_number}"
