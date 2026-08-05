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
