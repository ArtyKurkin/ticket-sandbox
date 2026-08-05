from django.conf import settings
from django.db import models

from django.core.validators import (
    MaxValueValidator,
    MinValueValidator,
)

from .constants import (
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
