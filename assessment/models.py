from django.conf import settings
from django.db import models

from django.core.exceptions import ValidationError
from django.core.validators import (
    MaxValueValidator,
    MinValueValidator,
)

from .constants import (
    ExamAttemptStatus,
    QuestionDifficulty,
    QuestionStatus,
    QuestionType,
    SupportLevel,
)


class SupportProfile(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="support_profile",
        verbose_name="Сотрудник",
    )

    level = models.CharField(
        max_length=16,
        choices=SupportLevel.choices,
        verbose_name="Уровень поддержки",
    )

    is_active = models.BooleanField(
        default=True,
        verbose_name="Участвует в тестировании",
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Создан",
    )

    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name="Обновлён",
    )

    class Meta:
        ordering = (
            "user__last_name",
            "user__first_name",
            "user__username",
        )
        verbose_name = "Профиль сотрудника поддержки"
        verbose_name_plural = "Профили сотрудников поддержки"

    def __str__(self):
        return (
            f"{self.user.get_full_name() or self.user.username} — "
            f"{self.get_level_display()}"
        )


class Topic(models.Model):
    name = models.CharField(
        max_length=100,
        verbose_name="Название",
    )

    slug = models.SlugField(
        max_length=100,
        unique=True,
        verbose_name="Slug",
    )

    description = models.TextField(
        blank=True,
        verbose_name="Описание",
    )

    order = models.PositiveSmallIntegerField(
        default=0,
        verbose_name="Порядок",
    )

    is_active = models.BooleanField(
        default=True,
        verbose_name="Активна",
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Создана",
    )

    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name="Обновлена",
    )

    class Meta:
        ordering = (
            "order",
            "name",
        )
        verbose_name = "Тематика"
        verbose_name_plural = "Тематики"

    def __str__(self):
        return self.name


class Skill(models.Model):
    topic = models.ForeignKey(
        Topic,
        on_delete=models.PROTECT,
        related_name="skills",
        verbose_name="Тематика",
    )

    name = models.CharField(
        max_length=150,
        verbose_name="Название",
    )

    slug = models.SlugField(
        max_length=100,
        verbose_name="Slug",
    )

    description = models.TextField(
        blank=True,
        verbose_name="Что проверяем",
    )

    order = models.PositiveSmallIntegerField(
        default=0,
        verbose_name="Порядок",
    )

    is_active = models.BooleanField(
        default=True,
        verbose_name="Активен",
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Создан",
    )

    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name="Обновлён",
    )

    class Meta:
        ordering = (
            "topic__order",
            "order",
            "name",
        )
        constraints = (
            models.UniqueConstraint(
                fields=(
                    "topic",
                    "slug",
                ),
                name="assessment_unique_skill_slug_per_topic",
            ),
        )
        verbose_name = "Проверяемый навык"
        verbose_name_plural = "Проверяемые навыки"

    def __str__(self):
        return f"{self.topic.name} → {self.name}"


class QuestionFamily(models.Model):
    skill = models.ForeignKey(
        Skill,
        on_delete=models.PROTECT,
        related_name="question_families",
        verbose_name="Проверяемый навык",
    )

    name = models.CharField(
        max_length=150,
        verbose_name="Название",
    )

    slug = models.SlugField(
        max_length=100,
        verbose_name="Slug",
    )

    assessment_goal = models.TextField(
        verbose_name="Что должно показать семейство",
    )

    order = models.PositiveSmallIntegerField(
        default=0,
        verbose_name="Порядок",
    )

    is_active = models.BooleanField(
        default=True,
        verbose_name="Активно",
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Создано",
    )

    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name="Обновлено",
    )

    class Meta:
        ordering = (
            "skill__topic__order",
            "skill__order",
            "order",
            "name",
        )
        constraints = (
            models.UniqueConstraint(
                fields=(
                    "skill",
                    "slug",
                ),
                name="assessment_unique_family_slug_per_skill",
            ),
        )
        verbose_name = "Семейство вопросов"
        verbose_name_plural = "Семейства вопросов"

    def __str__(self):
        return f"{self.skill} → {self.name}"


class ExamBlueprint(models.Model):
    name = models.CharField(
        max_length=150,
        verbose_name="Название",
    )

    slug = models.SlugField(
        max_length=120,
        unique=True,
        verbose_name="Slug",
    )

    level = models.CharField(
        max_length=16,
        choices=SupportLevel.choices,
        verbose_name="Уровень сотрудников",
    )

    pass_percentage = models.PositiveSmallIntegerField(
        default=85,
        validators=(
            MinValueValidator(1),
            MaxValueValidator(100),
        ),
        verbose_name="Проходной результат, %",
    )

    allow_back_navigation = models.BooleanField(
        default=False,
        verbose_name="Разрешить возврат к вопросам",
        help_text=(
            "Если выключено, после отправки ответа "
            "вернуться к вопросу нельзя."
        ),
    )

    shuffle_questions = models.BooleanField(
        default=True,
        verbose_name="Перемешивать вопросы",
    )

    shuffle_answer_options = models.BooleanField(
        default=True,
        verbose_name="Перемешивать варианты ответов",
    )

    is_active = models.BooleanField(
        default=True,
        verbose_name="Активен",
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Создан",
    )

    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name="Обновлён",
    )

    class Meta:
        ordering = (
            "level",
            "name",
        )
        verbose_name = "Шаблон теста"
        verbose_name_plural = "Шаблоны тестов"

    def __str__(self):
        return f"{self.name} — {self.get_level_display()}"

    @property
    def question_count(self):
        prefetched_quotas = getattr(
            self,
            "_prefetched_objects_cache",
            {},
        ).get("skill_quotas")

        if prefetched_quotas is not None:
            return sum(
                quota.question_count
                for quota in prefetched_quotas
            )

        result = self.skill_quotas.aggregate(
            total=models.Sum("question_count"),
        )

        return result["total"] or 0


class BlueprintSkillQuota(models.Model):
    blueprint = models.ForeignKey(
        ExamBlueprint,
        on_delete=models.CASCADE,
        related_name="skill_quotas",
        verbose_name="Шаблон теста",
    )

    skill = models.ForeignKey(
        Skill,
        on_delete=models.PROTECT,
        related_name="blueprint_quotas",
        verbose_name="Проверяемый навык",
    )

    question_count = models.PositiveSmallIntegerField(
        default=1,
        validators=(
            MinValueValidator(1),
            MaxValueValidator(20),
        ),
        verbose_name="Количество вопросов",
    )

    order = models.PositiveSmallIntegerField(
        default=0,
        verbose_name="Порядок",
    )

    class Meta:
        ordering = (
            "order",
            "skill__topic__order",
            "skill__order",
            "skill__name",
        )

        constraints = (
            models.UniqueConstraint(
                fields=(
                    "blueprint",
                    "skill",
                ),
                name=(
                    "assessment_unique_skill_"
                    "per_blueprint"
                ),
            ),
        )

        verbose_name = "Квота навыка"
        verbose_name_plural = "Квоты навыков"

    def __str__(self):
        return (
            f"{self.blueprint.name}: "
            f"{self.skill} — "
            f"{self.question_count}"
        )


class AssessmentCampaign(models.Model):
    name = models.CharField(
        max_length=180,
        verbose_name="Название",
    )

    slug = models.SlugField(
        max_length=150,
        unique=True,
        verbose_name="Slug",
    )

    blueprint = models.ForeignKey(
        ExamBlueprint,
        on_delete=models.PROTECT,
        related_name="campaigns",
        verbose_name="Шаблон теста",
    )

    description = models.TextField(
        blank=True,
        verbose_name="Описание",
    )

    opens_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Доступен с",
    )

    closes_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Доступен до",
    )

    is_active = models.BooleanField(
        default=False,
        verbose_name="Активна",
    )

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_assessment_campaigns",
        verbose_name="Создал",
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Создана",
    )

    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name="Обновлена",
    )

    class Meta:
        ordering = (
            "-created_at",
            "name",
        )

        verbose_name = "Кампания оценки"
        verbose_name_plural = "Кампании оценки"

    def __str__(self):
        return self.name

    def clean(self):
        super().clean()

        if (
            self.opens_at
            and self.closes_at
            and self.closes_at <= self.opens_at
        ):
            raise ValidationError(
                {
                    "closes_at": (
                        "Дата окончания должна быть "
                        "позже даты начала."
                    ),
                }
            )


class ExamAssignment(models.Model):
    campaign = models.ForeignKey(
        AssessmentCampaign,
        on_delete=models.PROTECT,
        related_name="assignments",
        verbose_name="Кампания",
    )

    employee = models.ForeignKey(
        SupportProfile,
        on_delete=models.PROTECT,
        related_name="exam_assignments",
        verbose_name="Сотрудник",
    )

    attempt_limit = models.PositiveSmallIntegerField(
        default=1,
        validators=(
            MinValueValidator(1),
            MaxValueValidator(10),
        ),
        verbose_name="Доступно попыток",
    )

    is_active = models.BooleanField(
        default=True,
        verbose_name="Назначение активно",
    )

    assigned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_exam_assignments",
        verbose_name="Назначил",
    )

    assigned_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Назначено",
    )

    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name="Обновлено",
    )

    class Meta:
        ordering = (
            "-assigned_at",
        )

        constraints = (
            models.UniqueConstraint(
                fields=(
                    "campaign",
                    "employee",
                ),
                name=(
                    "assessment_unique_employee_"
                    "per_campaign"
                ),
            ),
        )

        verbose_name = "Назначение теста"
        verbose_name_plural = "Назначения тестов"

    def __str__(self):
        employee_name = (
            self.employee.user.get_full_name()
            or self.employee.user.username
        )

        return (
            f"{self.campaign.name} — "
            f"{employee_name}"
        )

    def clean(self):
        super().clean()

        if not self.campaign_id or not self.employee_id:
            return

        campaign_level = (
            self.campaign.blueprint.level
        )

        if self.employee.level != campaign_level:
            raise ValidationError(
                {
                    "employee": (
                        "Уровень сотрудника не совпадает "
                        "с уровнем шаблона теста."
                    ),
                }
            )

        if (
            self._state.adding
            and not self.employee.is_active
        ):
            raise ValidationError(
                {
                    "employee": (
                        "Нельзя назначить тест "
                        "неактивному сотруднику."
                    ),
                }
            )


class ExamAttempt(models.Model):
    assignment = models.ForeignKey(
        ExamAssignment,
        on_delete=models.PROTECT,
        related_name="attempts",
        verbose_name="Назначение",
    )

    attempt_number = models.PositiveSmallIntegerField(
        verbose_name="Номер попытки",
    )

    status = models.CharField(
        max_length=20,
        choices=ExamAttemptStatus.choices,
        default=ExamAttemptStatus.IN_PROGRESS,
        verbose_name="Статус",
    )

    selection_seed = models.CharField(
        max_length=64,
        verbose_name="Seed выбора вопросов",
    )

    campaign_name = models.CharField(
        max_length=180,
        verbose_name="Название кампании",
    )

    blueprint_name = models.CharField(
        max_length=150,
        verbose_name="Название шаблона",
    )

    level = models.CharField(
        max_length=16,
        choices=SupportLevel.choices,
        verbose_name="Уровень",
    )

    pass_percentage = models.PositiveSmallIntegerField(
        verbose_name="Проходной результат, %",
    )

    allow_back_navigation = models.BooleanField(
        verbose_name="Разрешён возврат к вопросам",
    )

    shuffle_questions = models.BooleanField(
        verbose_name="Вопросы перемешаны",
    )

    shuffle_answer_options = models.BooleanField(
        verbose_name="Варианты ответов перемешаны",
    )

    started_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Начата",
    )

    completed_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Завершена",
    )

    invalidated_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Аннулирована",
    )

    invalidated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="invalidated_exam_attempts",
        verbose_name="Аннулировал",
    )

    invalidation_reason = models.TextField(
        blank=True,
        verbose_name="Причина аннулирования",
    )

    class Meta:
        ordering = (
            "-started_at",
        )

        constraints = (
            models.UniqueConstraint(
                fields=(
                    "assignment",
                    "attempt_number",
                ),
                name=(
                    "assessment_unique_attempt_number_"
                    "per_assignment"
                ),
            ),
        )

        verbose_name = "Попытка теста"
        verbose_name_plural = "Попытки тестов"

    def __str__(self):
        employee = self.assignment.employee.user

        employee_name = (
            employee.get_full_name()
            or employee.username
        )

        return (
            f"{employee_name} — "
            f"{self.campaign_name} — "
            f"попытка {self.attempt_number}"
        )


class ExamQuestionSnapshot(models.Model):
    attempt = models.ForeignKey(
        ExamAttempt,
        on_delete=models.CASCADE,
        related_name="question_snapshots",
        verbose_name="Попытка",
    )

    source_question = models.ForeignKey(
        "Question",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="exam_snapshots",
        verbose_name="Исходный вопрос",
    )

    position = models.PositiveSmallIntegerField(
        verbose_name="Позиция в тесте",
    )

    topic_name = models.CharField(
        max_length=100,
        verbose_name="Тематика",
    )

    topic_slug = models.SlugField(
        max_length=100,
    )

    skill_name = models.CharField(
        max_length=150,
        verbose_name="Навык",
    )

    skill_slug = models.SlugField(
        max_length=100,
    )

    family_name = models.CharField(
        max_length=150,
        verbose_name="Семейство",
    )

    family_slug = models.SlugField(
        max_length=100,
    )

    question_title = models.CharField(
        max_length=180,
        verbose_name="Внутреннее название вопроса",
    )

    question_slug = models.SlugField(
        max_length=120,
    )

    question_type = models.CharField(
        max_length=32,
        choices=QuestionType.choices,
        verbose_name="Тип вопроса",
    )

    difficulty = models.CharField(
        max_length=16,
        choices=QuestionDifficulty.choices,
        verbose_name="Сложность",
    )

    scenario = models.TextField(
        blank=True,
        verbose_name="Ситуация",
    )

    diagnostic_data = models.TextField(
        blank=True,
        verbose_name="Логи и данные",
    )

    prompt = models.TextField(
        verbose_name="Вопрос",
    )

    time_limit_seconds = models.PositiveSmallIntegerField(
        verbose_name="Время на ответ",
    )

    explanation = models.TextField(
        blank=True,
        verbose_name="Объяснение для наставника",
    )

    visible_payload = models.JSONField(
        default=dict,
        verbose_name="Данные для показа сотруднику",
    )

    grading_payload = models.JSONField(
        default=dict,
        verbose_name="Данные для проверки ответа",
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Создан",
    )

    class Meta:
        ordering = (
            "position",
        )

        constraints = (
            models.UniqueConstraint(
                fields=(
                    "attempt",
                    "position",
                ),
                name=(
                    "assessment_unique_question_position_"
                    "per_attempt"
                ),
            ),
        )

        verbose_name = "Снимок вопроса"
        verbose_name_plural = "Снимки вопросов"

    def __str__(self):
        return (
            f"Вопрос {self.position}: "
            f"{self.question_title}"
        )


class Question(models.Model):
    family = models.ForeignKey(
        QuestionFamily,
        on_delete=models.PROTECT,
        related_name="questions",
        verbose_name="Семейство вопросов",
    )

    title = models.CharField(
        max_length=180,
        verbose_name="Внутреннее название",
        help_text=(
            "Название видно наставнику, "
            "но не показывается сотруднику."
        ),
    )

    slug = models.SlugField(
        max_length=120,
        verbose_name="Slug",
    )

    level = models.CharField(
        max_length=16,
        choices=SupportLevel.choices,
        verbose_name="Уровень",
    )

    difficulty = models.CharField(
        max_length=16,
        choices=QuestionDifficulty.choices,
        default=QuestionDifficulty.HARD,
        verbose_name="Сложность",
    )

    scenario = models.TextField(
        blank=True,
        verbose_name="Ситуация и вводные",
        help_text=(
            "Описание проблемы или обращения, "
            "которое увидит сотрудник."
        ),
    )

    diagnostic_data = models.TextField(
        blank=True,
        verbose_name="Логи и вывод команд",
        help_text=(
            "Необязательный блок с логами, "
            "конфигурацией или выводом команд."
        ),
    )

    prompt = models.TextField(
        verbose_name="Вопрос",
    )

    answer_type = models.CharField(
        max_length=32,
        choices=QuestionType.choices,
        default=QuestionType.SINGLE_CHOICE,
        verbose_name="Тип ответа",
    )

    time_limit_seconds = models.PositiveSmallIntegerField(
        default=90,
        validators=(
            MinValueValidator(30),
            MaxValueValidator(300),
        ),
        verbose_name="Время на ответ, секунд",
    )

    explanation = models.TextField(
        blank=True,
        verbose_name="Объяснение для наставника",
        help_text=(
            "Почему ответ правильный и какое "
            "знание проверяет вопрос."
        ),
    )

    status = models.CharField(
        max_length=16,
        choices=QuestionStatus.choices,
        default=QuestionStatus.DRAFT,
        verbose_name="Статус",
    )

    order = models.PositiveSmallIntegerField(
        default=0,
        verbose_name="Порядок",
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Создан",
    )

    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name="Обновлён",
    )

    class Meta:
        ordering = (
            "family__skill__topic__order",
            "family__skill__order",
            "family__order",
            "order",
            "title",
        )

        constraints = (
            models.UniqueConstraint(
                fields=(
                    "family",
                    "slug",
                ),
                name=(
                    "assessment_unique_question_slug_"
                    "per_family"
                ),
            ),
        )

        verbose_name = "Вопрос"
        verbose_name_plural = "Вопросы"

    def __str__(self):
        return f"{self.family} → {self.title}"


class AnswerOption(models.Model):
    question = models.ForeignKey(
        Question,
        on_delete=models.CASCADE,
        related_name="answer_options",
        verbose_name="Вопрос",
    )

    text = models.TextField(
        verbose_name="Вариант ответа",
    )

    is_correct = models.BooleanField(
        default=False,
        verbose_name="Правильный ответ",
    )

    order = models.PositiveSmallIntegerField(
        default=0,
        verbose_name="Порядок",
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Создан",
    )

    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name="Обновлён",
    )

    class Meta:
        ordering = (
            "order",
            "id",
        )

        verbose_name = "Вариант ответа"
        verbose_name_plural = "Варианты ответов"

    def __str__(self):
        return self.text


class MatchingPair(models.Model):
    question = models.ForeignKey(
        Question,
        on_delete=models.CASCADE,
        related_name="matching_pairs",
        verbose_name="Вопрос",
    )

    left_text = models.TextField(
        verbose_name="Левая часть",
    )

    right_text = models.TextField(
        verbose_name="Правильная правая часть",
    )

    order = models.PositiveSmallIntegerField(
        default=0,
        verbose_name="Порядок",
    )

    class Meta:
        ordering = (
            "order",
            "id",
        )
        verbose_name = "Пара для сопоставления"
        verbose_name_plural = "Пары для сопоставления"

    def __str__(self):
        return f"{self.left_text} → {self.right_text}"


class OrderingItem(models.Model):
    question = models.ForeignKey(
        Question,
        on_delete=models.CASCADE,
        related_name="ordering_items",
        verbose_name="Вопрос",
    )

    text = models.TextField(
        verbose_name="Элемент последовательности",
    )

    order = models.PositiveSmallIntegerField(
        default=0,
        verbose_name="Правильная позиция",
        help_text=(
            "Чем меньше значение, тем раньше "
            "должен находиться элемент."
        ),
    )

    class Meta:
        ordering = (
            "order",
            "id",
        )
        verbose_name = "Элемент последовательности"
        verbose_name_plural = "Элементы последовательности"

    def __str__(self):
        return self.text


class SelectableLine(models.Model):
    question = models.ForeignKey(
        Question,
        on_delete=models.CASCADE,
        related_name="selectable_lines",
        verbose_name="Вопрос",
    )

    text = models.TextField(
        verbose_name="Строка",
    )

    is_correct = models.BooleanField(
        default=False,
        verbose_name="Нужно выбрать",
    )

    order = models.PositiveSmallIntegerField(
        default=0,
        verbose_name="Номер строки",
    )

    class Meta:
        ordering = (
            "order",
            "id",
        )
        verbose_name = "Строка лога или конфигурации"
        verbose_name_plural = "Строки лога или конфигурации"

    def __str__(self):
        return self.text
