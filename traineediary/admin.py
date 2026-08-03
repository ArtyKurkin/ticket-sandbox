from django.contrib import admin
from django.urls import reverse
from django.utils.html import format_html

from .models import (
    RiskLevel,
    StageHistory,
    TraineeJourney,
    TraineeStage,
    WeeklyMetric,
)


@admin.register(TraineeStage)
class TraineeStageAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "order",
        "group",
        "min_days",
        "max_days",
        "progress_weight_percent",
        "color",
        "applies_to_new_hire",
        "applies_to_internal_transfer",
        "is_active",
    )

    list_editable = (
        "order",
        "min_days",
        "max_days",
        "progress_weight_percent",
        "applies_to_new_hire",
        "applies_to_internal_transfer",
        "is_active",
    )

    list_filter = (
        "group",
        "is_active",
    )

    ordering = (
        "order",
    )

    prepopulated_fields = {
        "slug": (
            "name",
        ),
    }


class StageHistoryInline(admin.TabularInline):
    model = StageHistory
    extra = 0

    readonly_fields = (
        "stage",
        "started_at",
        "ended_at",
        "changed_by",
        "note",
    )

    can_delete = False
    show_change_link = True

    ordering = (
        "-started_at",
        "-id",
    )

    def has_add_permission(
        self,
        request,
        obj=None,
    ):
        return False

    def has_delete_permission(
        self,
        request,
        obj=None,
    ):
        return False


class WeeklyMetricInline(admin.TabularInline):
    model = WeeklyMetric
    extra = 0

    readonly_fields = (
        "week_number",
        "week_start_date",
        "speed_hours",
        "quality_percent",
        "mentor_comment",
        "next_week_goal",
    )

    can_delete = False
    show_change_link = True

    ordering = (
        "week_number",
    )

    def has_add_permission(
        self,
        request,
        obj=None,
    ):
        return False

    def has_delete_permission(
        self,
        request,
        obj=None,
    ):
        return False


@admin.register(TraineeJourney)
class TraineeJourneyAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "entry_type",
        "current_stage",
        "completion_status",
        "completed_at",
        "days_total_display",
        "days_left_display",
        "risk_level_display",
        "expected_stage_transition_date",
        "diary_link",
    )

    list_filter = (
        "entry_type",
        "current_stage",
        "current_stage__group",
        "completion_status",
        "manual_risk_override",
    )

    search_fields = (
        "user__username",
        "user__first_name",
        "user__last_name",
        "completion_comment",
    )

    readonly_fields = (
        "user",
        "entry_type",
        "probation_start_date",
        "current_stage",
        "stage_started_at",
        "fixed_quality_percent",
        "quality_fixed_at",
        "completion_status",
        "completed_at",
        "completion_comment",
        "completed_by",
        "diary_link",
    )

    fieldsets = (
        (
            "Сотрудник",
            {
                "fields": (
                    "user",
                    "entry_type",
                    "probation_start_date",
                    "diary_link",
                ),
            },
        ),
        (
            "Текущий этап",
            {
                "fields": (
                    "current_stage",
                    "stage_started_at",
                ),
            },
        ),
        (
            "Рабочие поля наставника",
            {
                "fields": (
                    "comment",
                    "manual_risk_override",
                ),
            },
        ),
        (
            "Зафиксированное качество",
            {
                "fields": (
                    "fixed_quality_percent",
                    "quality_fixed_at",
                ),
            },
        ),
        (
            "Завершение испытательного срока",
            {
                "fields": (
                    "completion_status",
                    "completed_at",
                    "completion_comment",
                    "completed_by",
                ),
            },
        ),
    )

    inlines = (
        StageHistoryInline,
        WeeklyMetricInline,
    )

    date_hierarchy = (
        "probation_start_date"
    )

    list_select_related = (
        "user",
        "current_stage",
    )

    def has_add_permission(
        self,
        request,
    ):
        # Карточки создаются только через
        # сценарии Дневника стажёра.
        return False

    def has_delete_permission(
        self,
        request,
        obj=None,
    ):
        # Удаление карточки уничтожает историю
        # этапов и недельные показатели.
        return False

    @admin.display(
        description="Дней всего",
    )
    def days_total_display(
        self,
        obj,
    ):
        return obj.days_total

    @admin.display(
        description="Осталось до конца ИС",
    )
    def days_left_display(
        self,
        obj,
    ):
        return (
            obj.days_left_until_probation_end
        )

    @admin.display(
        description="Риск",
    )
    def risk_level_display(
        self,
        obj,
    ):
        risk_level = obj.risk_level

        if not risk_level:
            return "—"

        return RiskLevel(
            risk_level,
        ).label

    @admin.display(
        description="Дневник",
    )
    def diary_link(
        self,
        obj,
    ):
        if not obj or not obj.pk:
            return "—"

        url = reverse(
            "traineediary:trainee_detail",
            args=[
                obj.pk,
            ],
        )

        return format_html(
            '<a href="{}">Открыть карточку</a>',
            url,
        )


@admin.register(StageHistory)
class StageHistoryAdmin(admin.ModelAdmin):
    list_display = (
        "journey",
        "stage",
        "started_at",
        "ended_at",
        "changed_by",
    )

    list_filter = (
        "stage",
        "stage__group",
    )

    search_fields = (
        "journey__user__username",
        "journey__user__first_name",
        "journey__user__last_name",
        "note",
    )

    readonly_fields = (
        "journey",
        "stage",
        "started_at",
        "ended_at",
        "changed_by",
        "note",
    )

    ordering = (
        "-started_at",
        "-id",
    )

    list_select_related = (
        "journey",
        "journey__user",
        "stage",
        "changed_by",
    )

    def has_add_permission(
        self,
        request,
    ):
        return False

    def has_delete_permission(
        self,
        request,
        obj=None,
    ):
        return False


@admin.register(WeeklyMetric)
class WeeklyMetricAdmin(admin.ModelAdmin):
    list_display = (
        "journey",
        "week_number",
        "week_start_date",
        "speed_hours",
        "quality_percent",
    )

    list_filter = (
        "week_number",
    )

    search_fields = (
        "journey__user__username",
        "journey__user__first_name",
        "journey__user__last_name",
        "mentor_comment",
        "next_week_goal",
    )

    readonly_fields = (
        "journey",
        "week_number",
        "week_start_date",
        "speed_hours",
        "quality_percent",
        "mentor_comment",
        "next_week_goal",
    )

    ordering = (
        "-week_start_date",
        "journey",
        "week_number",
    )

    list_select_related = (
        "journey",
        "journey__user",
    )

    def has_add_permission(
        self,
        request,
    ):
        return False

    def has_delete_permission(
        self,
        request,
        obj=None,
    ):
        return False
