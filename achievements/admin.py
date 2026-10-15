from django.contrib import admin
from .models import AchievementDefinition, AchievementTier, UserAchievement, AchievementEvent, AchievementSourceEvent
from .models import AchievementNotification, AchievementNotificationBoundary


class ReadOnlyAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(AchievementDefinition)
class DefinitionAdmin(ReadOnlyAdmin):
    list_display = ("code", "kind", "secret", "active", "rule_version")


admin.site.register(AchievementTier, ReadOnlyAdmin)
admin.site.register(UserAchievement, ReadOnlyAdmin)
admin.site.register(AchievementNotification, ReadOnlyAdmin)
admin.site.register(AchievementNotificationBoundary, ReadOnlyAdmin)


@admin.register(AchievementEvent)
class EventAdmin(ReadOnlyAdmin):
    list_display = ("id", "entitlement", "action", "source_type", "recorded_at")


@admin.register(AchievementSourceEvent)
class SourceAdmin(ReadOnlyAdmin):
    list_display = ("id", "provider", "external_id", "status", "attempts")
