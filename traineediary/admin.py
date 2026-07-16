from django.contrib import admin

from .models import StageHistory, TraineeJourney, TraineeStage, WeeklyMetric


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
    list_filter = ("group", "is_active")
    ordering = ("order",)
    prepopulated_fields = {"slug": ("name",)}


class StageHistoryInline(admin.TabularInline):
    model = StageHistory
    extra = 0
    readonly_fields = ("stage", "started_at", "ended_at", "changed_by", "note")
    can_delete = False
    ordering = ("-started_at",)


class WeeklyMetricInline(admin.TabularInline):
    model = WeeklyMetric
    extra = 1
    ordering = ("week_number",)


@admin.register(TraineeJourney)
class TraineeJourneyAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "entry_type",
        "current_stage",
        "days_total_display",
        "days_left_display",
        "risk_level_display",
        "expected_stage_transition_date",
    )
    list_filter = ("entry_type", "current_stage", "current_stage__group")
    search_fields = ("user__username", "user__first_name", "user__last_name")
    raw_id_fields = ("user",)
    inlines = (StageHistoryInline, WeeklyMetricInline)

    @admin.display(description="Дней всего")
    def days_total_display(self, obj):
        return obj.days_total

    @admin.display(description="Осталось до конца ИС")
    def days_left_display(self, obj):
        return obj.days_left_until_probation_end

    @admin.display(description="Риск")
    def risk_level_display(self, obj):
        return obj.get_risk_level_display() if obj.risk_level else "—"


admin.site.register(StageHistory)
admin.site.register(WeeklyMetric)
