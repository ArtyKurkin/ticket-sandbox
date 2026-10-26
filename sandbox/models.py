from django.conf import settings
from django.db import models
from django.contrib.auth.models import User


class TraineeProfile(models.Model):
    class Level(models.TextChoices):
        CANDIDATE = "candidate", "Кандидат"
        L1 = "l1", "L1"
        L2 = "l2", "L2"
        ADMIN = "admin", "Системный администратор"

    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="trainee_profile",
        verbose_name="Пользователь"
    )

    level = models.CharField(
        max_length=32,
        choices=Level.choices,
        default=Level.CANDIDATE,
        verbose_name="Уровень"
    )

    class Meta:
        verbose_name = "Профиль стажера"
        verbose_name_plural = "Профили стажеров"

    def __str__(self):
        return f"{self.user} — {self.get_level_display()}"


class Queue(models.Model):
    name = models.CharField(
        max_length=100,
        verbose_name="Название"
    )

    slug = models.SlugField(
        unique=True,
        verbose_name="Slug"
    )

    description = models.TextField(
        blank=True,
        verbose_name="Описание"
    )

    order = models.PositiveIntegerField(
        default=1,
        verbose_name="Порядок"
    )

    is_active = models.BooleanField(
        default=True,
        verbose_name="Активна"
    )

    required_level = models.CharField(
        max_length=32,
        choices=TraineeProfile.Level.choices,
        default=TraineeProfile.Level.CANDIDATE,
        verbose_name="Минимальный уровень"
    )

    class Meta:
        ordering = ["order"]
        verbose_name = "Очередь"
        verbose_name_plural = "Очереди"

    def __str__(self):
        return self.name


class ImmutableCompletionQuerySet(models.QuerySet):
    def update(self, **kwargs):
        from django.core.exceptions import ValidationError
        raise ValidationError("Сохранённое завершение программы неизменяемо.")

    def bulk_update(self, objs, fields, batch_size=None):
        from django.core.exceptions import ValidationError
        raise ValidationError("Сохранённое завершение программы неизменяемо.")

    def bulk_create(self, objs, *args, **kwargs):
        from django.core.exceptions import ValidationError
        raise ValidationError("Завершения создаются только явным сервисом фиксации.")

    def delete(self):
        from django.core.exceptions import ValidationError
        raise ValidationError("Сохранённое завершение программы нельзя удалить.")


class SandboxProgramCompletion(models.Model):
    class Source(models.TextChoices):
        TECHNICAL_CHECK = "technical_check", "Техническая проверка"
        LEGACY_RESTORE = "legacy_restore", "Явное восстановление"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name="sandbox_program_completions",
    )
    # A stable program key survives queue/task deletion and slug/name changes.
    program_key = models.SlugField(default="l1")
    completed_at = models.DateTimeField()
    recorded_at = models.DateTimeField(auto_now_add=True)
    source = models.CharField(max_length=32, choices=Source.choices)
    composition_fingerprint = models.CharField(max_length=64)
    snapshot = models.JSONField()

    objects = ImmutableCompletionQuerySet.as_manager()

    class Meta:
        constraints = [models.UniqueConstraint(
            fields=["user", "program_key"], name="unique_sandbox_completion_user_program",
        )]
        verbose_name = "Техническое завершение программы Sandbox"
        verbose_name_plural = "Технические завершения программ Sandbox"

    def clean(self):
        from .services.completions import validate_completion_snapshot
        validate_completion_snapshot(self)

    def save(self, *args, **kwargs):
        from django.core.exceptions import ValidationError
        if not self._state.adding:
            raise ValidationError("Сохранённое завершение программы неизменяемо.")
        # Uniqueness is checked atomically by the DB, so get_or_create can
        # resolve a concurrent insert without a validation-before-insert race.
        self.full_clean(validate_unique=False, validate_constraints=False)
        kwargs["force_insert"] = True
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        from django.core.exceptions import ValidationError
        raise ValidationError("Сохранённое завершение программы нельзя удалить.")

    def __str__(self):
        return f"{self.user_id}: {self.program_key} ({self.completed_at})"


class Task(models.Model):
    class Priority(models.TextChoices):
        LOW = "low", "Низкий"
        MEDIUM = "medium", "Средний"
        HIGH = "high", "Высокий"
        CRITICAL = "critical", "Критический"

    queue = models.ForeignKey(
        Queue,
        on_delete=models.PROTECT,
        related_name="tasks",
        verbose_name="Очередь"
    )

    title = models.CharField(
        max_length=255,
        verbose_name="Название"
    )

    slug = models.SlugField(
        verbose_name="Slug"
    )

    order = models.PositiveIntegerField(
        default=1,
        verbose_name="Порядок"
    )

    description = models.TextField(
        verbose_name="Описание"
    )

    ticket_title = models.CharField(
        max_length=255,
        blank=True,
        default="Обращение в службу поддержки",
        verbose_name="Тема тикета"
    )

    client_name = models.CharField(
        max_length=255,
        blank=True,
        default="Учебный клиент",
        verbose_name="Имя клиента"
    )

    client_email = models.EmailField(
        blank=True,
        default="client@example.ru",
        verbose_name="Email клиента"
    )

    priority = models.CharField(
        max_length=20,
        choices=Priority.choices,
        default=Priority.MEDIUM,
        verbose_name="Приоритет"
    )

    requires_manual_review = models.BooleanField(
        default=False,
        verbose_name="Требует ручной проверки наставника"
    )

    ai_review_context = models.JSONField(
        default=dict,
        blank=True,
        verbose_name="Контекст для AI-проверки",
    )

    is_active = models.BooleanField(
        default=True,
        verbose_name="Активно"
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    class Meta:
        ordering = ["queue__order", "order"]
        verbose_name = "Задание"
        verbose_name_plural = "Задания"
        constraints = [
            models.UniqueConstraint(
                fields=["queue", "slug"],
                name="unique_task_slug_per_queue"
            ),
            models.UniqueConstraint(
                fields=["queue", "order"],
                name="unique_task_order_per_queue"
            ),
        ]

    def __str__(self):
        return self.title


class AttemptQuerySet(models.QuerySet):
    def update(self, **kwargs):
        from .services.ledger import database_write, unsupported_updates
        with database_write():
            unsupported_updates(self, kwargs)
            return super().update(**kwargs)


class TaskAttempt(models.Model):
    objects = AttemptQuerySet.as_manager()

    def save(self, *args, **kwargs):
        from .services import ledger
        from django.db import transaction, connection
        if kwargs.get('update_fields') is not None and not kwargs['update_fields']:
            return super().save(*args, **kwargs)
        with transaction.atomic():
            existing = type(self).objects.filter(pk=self.pk).first() if self.pk else None
            manifest = None
            enabled = ledger.SandboxLedgerBoundary.objects.filter(pk=1).exists()
            if enabled and existing is None:
                manifest = ledger.ensure_manifest(self.user_id, self.task)
            if enabled and existing is not None and connection.vendor != 'postgresql' and not ledger._writing.get():
                selected = kwargs.get('update_fields') or ledger.PROTECTED
                fields = {f.attname for f in self._meta.fields if f.name in selected or f.attname in selected}
                if any(getattr(existing, field) != getattr(self, field) for field in ledger.PROTECTED.intersection(fields)):
                    ledger.gap(self.pk, 'unsupported_update', 'orm')
            with ledger.database_write():
                result = super().save(*args, **kwargs)
            if enabled and existing is None:
                ledger.created_attempt(self, manifest)
            return result

    class MentorDecision(models.TextChoices):
        NOT_REVIEWED = "not_reviewed", "Не проверено"
        APPROVED = "approved", "Принято"
        NEEDS_REVISION = "needs_revision", "Нужна доработка"

    class Status(models.TextChoices):
        NEW = "new", "Новый"
        IN_PROGRESS = "in_progress", "В работе"
        ON_REVIEW = "on_review", "На проверке"
        FAILED = "failed", "Доработать"
        PASSED = "passed", "Пройдено"

    class CheckStatus(models.TextChoices):
        IDLE = "idle", "Не запускалась"
        RUNNING = "running", "Выполняется"
        PASSED = "passed", "Пройдена"
        FAILED = "failed", "Не пройдена"
        ERROR = "error", "Ошибка"

    class EnvironmentStatus(models.TextChoices):
        IDLE = "idle", "Не запущено"
        STARTING = "starting", "Запускается"
        READY = "ready", "Готово"
        RESTARTING = "restarting", "Перезапускается"
        ERROR = "error", "Ошибка"

    class StuckReason(models.TextChoices):
        NONE = "", "Не зависала"
        ENVIRONMENT = "environment", "Окружение"
        CHECK = "check", "Автопроверка"

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        verbose_name="Стажер"
    )

    task = models.ForeignKey(
        Task,
        on_delete=models.CASCADE,
        verbose_name="Задание"
    )

    attempt_number = models.PositiveIntegerField(
        default=1,
        verbose_name="Номер попытки",
    )

    is_current = models.BooleanField(
        default=True,
        verbose_name="Текущая попытка",
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Создана",
    )

    status = models.CharField(
        max_length=32,
        choices=Status.choices,
        default=Status.NEW,
        verbose_name="Статус"
    )

    attempts_count = models.PositiveIntegerField(
        default=0,
        verbose_name="Количество проверок"
    )

    restart_count = models.PositiveIntegerField(
        default=0,
        verbose_name="Количество перезапусков"
    )

    started_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Начато"
    )

    finished_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Завершено"
    )

    technical_passed_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Техническая часть пройдена"
    )

    check_status = models.CharField(
        max_length=20,
        choices=CheckStatus.choices,
        default=CheckStatus.IDLE,
    )

    check_started_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    check_finished_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    environment_status = models.CharField(
        max_length=20,
        choices=EnvironmentStatus.choices,
        default=EnvironmentStatus.IDLE,
    )

    environment_started_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    environment_finished_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    stuck_reason = models.CharField(
        max_length=32,
        choices=StuckReason.choices,
        default=StuckReason.NONE,
        blank=True,
        verbose_name="Причина зависания",
    )

    last_check_output = models.TextField(
        blank=True,
        verbose_name="Лог проверки"
    )

    trainee_report = models.TextField(
        blank=True,
        verbose_name="Отчет стажера"
    )

    client_answer = models.TextField(
        blank=True,
        verbose_name="Ответ клиенту"
    )

    container_id = models.CharField(
        max_length=255,
        blank=True,
        verbose_name="ID контейнера"
    )

    # Host-only diagnostic mapping, pinned on an explicitly opted-in start/reset.
    # Never read by technical evidence or academic transitions.
    http_observation_runtime = models.JSONField(default=dict, editable=False)

    container_name = models.CharField(
        max_length=255,
        blank=True,
        verbose_name="Имя контейнера"
    )

    shell_command = models.TextField(
        blank=True,
        verbose_name="Команда подключения"
    )

    terminal_container_name = models.CharField(
        max_length=255,
        blank=True,
        verbose_name="Имя контейнера терминала"
    )

    terminal_url = models.CharField(
        max_length=255,
        blank=True,
        verbose_name="URL терминала"
    )

    terminal_port = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name="Порт терминала"
    )

    mentor_feedback = models.TextField(
        blank=True,
        verbose_name="Комментарий наставника",
    )

    mentor_decision = models.CharField(
        max_length=32,
        choices=MentorDecision.choices,
        default=MentorDecision.NOT_REVIEWED,
        verbose_name="Решение наставника",
    )

    mentor_reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reviewed_attempts",
        verbose_name="Проверил наставник",
    )

    mentor_reviewed_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Дата проверки наставником",
    )

    mentor_feedback_seen_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Комментарий наставника прочитан",
    )

    @property
    def is_technically_completed(self):
        return self.technical_passed

    @property
    def technical_passed(self):
        from .services.technical_evidence import get_technical_evidence

        return get_technical_evidence(self).is_completed

    @property
    def technical_locked(self):
        """
        Техническая часть уже считается закрытой.

        Обычные start/restart действия не должны возвращать такую попытку
        обратно в работу и не должны пересоздавать Docker-окружение.
        """
        return self.is_technically_completed

    @property
    def can_start_environment(self):
        return not self.technical_locked and not self.container_name

    @property
    def can_restart_environment(self):
        return not self.technical_locked

    @property
    def can_access_terminal(self):
        """
        Терминал доступен во время технической работы и после успешной
        автопроверки, пока стажер готовит ответ наставнику.

        После отправки ответа на ручную проверку доступ закрывается,
        даже если Docker-окружение по какой-то причине еще не удалено.
        """
        if not self.is_current:
            return False

        if self.environment_status != self.EnvironmentStatus.READY:
            return False

        if not (
            self.container_name
            and self.terminal_container_name
            and self.terminal_url
        ):
            return False

        # Workflow locks are independent of whether a legacy technical pass
        # can be proved. An answer on review/passed must never reopen a terminal.
        if self.status in (self.Status.ON_REVIEW, self.Status.PASSED):
            return False

        if not self.technical_locked:
            return True

        return (
            self.technical_passed
            and self.task.requires_manual_review
            and self.is_credit_attempt
            and self.status == self.Status.IN_PROGRESS
        )

    @property
    def can_rerun(self):
        return (
            self.is_current
            and self.technical_locked
            and self.status == self.Status.PASSED
        )

    @property
    def can_go_next(self):
        if self.is_extra_attempt:
            from .services.technical_evidence import credit_task_completed

            return credit_task_completed(user=self.user, task=self.task)
        return self.is_technically_completed

    @property
    def waiting_for_mentor_review(self):
        return (
            self.technical_passed
            and self.task.requires_manual_review
            and self.status == self.Status.ON_REVIEW
            and self.mentor_decision == self.MentorDecision.NOT_REVIEWED
        )

    @property
    def needs_text_revision(self):
        return (
            self.technical_passed
            and self.mentor_decision == self.MentorDecision.NEEDS_REVISION
        )

    @property
    def can_edit_client_answer(self):
        """A returned credit answer stays editable after starting a practice attempt."""
        return (
            self.task.requires_manual_review
            and self.is_credit_attempt
            and self.technical_passed
            and self.status not in (self.Status.ON_REVIEW, self.Status.PASSED)
            and (
                self.is_current
                or self.mentor_decision == self.MentorDecision.NEEDS_REVISION
            )
        )

    @property
    def mentor_approved(self):
        return self.mentor_decision == self.MentorDecision.APPROVED

    @property
    def is_available(self):
        """
        Проверяет, доступно ли задание стажеру.
        """

        if self.task.order == 1:
            return True

        from .services.technical_evidence import (
            get_technical_evidence,
            with_technical_evidence,
        )

        previous_attempts = with_technical_evidence(
            TaskAttempt.objects.filter(
                user=self.user,
                task__queue=self.task.queue,
                task__order=self.task.order - 1,
                attempt_number=1,
            )
        )
        return any(
            get_technical_evidence(attempt).is_completed
            for attempt in previous_attempts
        )

    @property
    def mentor_feedback_read_state(self):
        if (
            self.mentor_decision == self.MentorDecision.NOT_REVIEWED
            or not self.mentor_feedback
        ):
            return "none"
        if self.mentor_feedback_seen_at is None:
            return "unread"
        if self.mentor_reviewed_at is None:
            return "unknown"
        return (
            "unread"
            if self.mentor_feedback_seen_at < self.mentor_reviewed_at
            else "read"
        )

    @property
    def has_unread_mentor_feedback(self):
        return self.mentor_feedback_read_state == "unread"

    @property
    def is_extra_attempt(self):
        return self.attempt_number > 1

    @property
    def is_credit_attempt(self):
        return self.attempt_number == 1

    class Meta:
        ordering = [
            "user__username",
            "task__queue__order",
            "task__order",
            "-attempt_number",
        ]

        constraints = [
            models.UniqueConstraint(
                fields=["user", "task", "attempt_number"],
                name="unique_attempt_number_per_user_task",
            ),
            models.UniqueConstraint(
                fields=["user", "task"],
                condition=models.Q(is_current=True),
                name="unique_current_attempt_per_user_task",
            ),
        ]

        verbose_name = "Попытка прохождения"
        verbose_name_plural = "Попытки прохождения"

    def __str__(self):
        return f"{self.user} — {self.task}"


class AIReview(models.Model):

    class Status(models.TextChoices):
        PENDING = "pending", "Ожидает"
        RUNNING = "running", "Выполняется"
        COMPLETED = "completed", "Завершена"
        ERROR = "error", "Ошибка"

    class MentorDecision(models.TextChoices):
        APPROVED = "approved", "Принято"
        NEEDS_REVISION = "needs_revision", "Нужна доработка"

    attempt = models.ForeignKey(
        TaskAttempt,
        on_delete=models.CASCADE,
        related_name="ai_reviews",
        verbose_name="Попытка",
    )

    client_answer = models.TextField(
        verbose_name="Проверенный ответ клиенту",
    )

    task_context = models.JSONField(
        default=dict,
        blank=True,
        verbose_name="Контекст задания на момент проверки",
    )

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
        verbose_name="Статус",
    )

    checks = models.JSONField(
        default=dict,
        blank=True,
        verbose_name="Результаты проверки",
    )

    recommendations = models.JSONField(
        default=list,
        blank=True,
        verbose_name="Рекомендации",
    )

    raw_response = models.JSONField(
        default=dict,
        blank=True,
        verbose_name="Полный ответ AI",
    )

    model = models.CharField(
        max_length=255,
        blank=True,
        verbose_name="Модель",
    )

    prompt_version = models.CharField(
        max_length=32,
        default="v1",
        verbose_name="Версия промпта",
    )

    input_tokens = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name="Входные токены",
    )

    output_tokens = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name="Выходные токены",
    )

    error_message = models.TextField(
        blank=True,
        verbose_name="Ошибка AI",
    )

    mentor_decision = models.CharField(
        max_length=20,
        choices=MentorDecision.choices,
        blank=True,
        default="",
        verbose_name="Решение наставника",
    )

    mentor_reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reviewed_ai_reviews",
        verbose_name="Проверил наставник",
    )

    mentor_reviewed_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Проверено наставником",
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Создана",
    )

    started_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Начата",
    )

    finished_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Завершена",
    )

    def __str__(self):
        return f"AI review #{self.pk} for attempt #{self.attempt_id}"


class CheckRun(models.Model):
    class Result(models.TextChoices):
        PASSED = "passed", "Пройдена"
        FAILED = "failed", "Не пройдена"

    attempt = models.ForeignKey(
        TaskAttempt,
        on_delete=models.CASCADE,
        related_name="check_runs",
        verbose_name="Попытка",
    )

    result = models.CharField(
        max_length=20,
        choices=Result.choices,
        verbose_name="Результат",
    )

    output = models.TextField(
        blank=True,
        verbose_name="Вывод проверки",
    )

    exit_code = models.IntegerField(
        verbose_name="Код выхода",
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Дата проверки",
    )

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Запуск проверки"
        verbose_name_plural = "Запуски проверок"

    def __str__(self):
        return f"{self.attempt} — {self.get_result_display()}"

# Registered in the same Django app; isolated module keeps operational models readable.
from .ledger_models import (SandboxLedgerBoundary, SandboxProgramManifest, SandboxAttemptCoverage, SandboxEvidenceGap,
    TechnicalCheckExecution, TechnicalCheckExecutionEvent, SandboxEnvironmentEvent, SandboxAnswerSubmission, SandboxAnswerReviewEvent)

from .observation_models import HTTPObservationRun
