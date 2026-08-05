from django.conf import settings
from django.db import models

from .constants import SupportLevel


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
