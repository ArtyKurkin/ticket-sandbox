from django.contrib import admin

from .models import SupportProfile


@admin.register(SupportProfile)
class SupportProfileAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "level",
        "is_active",
        "updated_at",
    )

    list_editable = (
        "level",
        "is_active",
    )

    list_filter = (
        "level",
        "is_active",
    )

    search_fields = (
        "user__username",
        "user__first_name",
        "user__last_name",
        "user__email",
    )

    list_select_related = (
        "user",
    )

    ordering = (
        "user__last_name",
        "user__first_name",
        "user__username",
    )
