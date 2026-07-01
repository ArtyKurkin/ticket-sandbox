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


class TaskAttempt(models.Model):

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
        return (
            self.technical_passed_at is not None
            or self.status == self.Status.PASSED
        )

    @property
    def technical_passed(self):
        return self.technical_passed_at is not None

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
    def can_go_next(self):
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
    def mentor_approved(self):
        return self.mentor_decision == self.MentorDecision.APPROVED

    @property
    def is_available(self):
        """
        Проверяет, доступно ли задание стажеру.
        """

        if self.task.order == 1:
            return True

        previous_attempt = (
            TaskAttempt.objects
            .filter(
                user=self.user,
                task__queue=self.task.queue,
                task__order=self.task.order - 1,
            )
            .filter(
                models.Q(status=TaskAttempt.Status.PASSED)
                | models.Q(technical_passed_at__isnull=False)
            )
            .exists()
        )

        return previous_attempt

    @property
    def has_unread_mentor_feedback(self):
        if self.mentor_decision == self.MentorDecision.NOT_REVIEWED:
            return False

        if not self.mentor_feedback:
            return False

        if not self.mentor_feedback_seen_at:
            return True

        if not self.mentor_reviewed_at:
            return True

        return self.mentor_feedback_seen_at < self.mentor_reviewed_at

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
