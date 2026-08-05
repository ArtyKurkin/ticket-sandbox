from django.contrib import admin

from .models import (
    QuestionFamily,
    Skill,
    SupportProfile,
    Topic,
)


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


class SkillInline(admin.TabularInline):
    model = Skill
    extra = 0
    show_change_link = True

    fields = (
        "name",
        "slug",
        "order",
        "is_active",
    )

    ordering = (
        "order",
        "name",
    )

    prepopulated_fields = {
        "slug": (
            "name",
        ),
    }


@admin.register(Topic)
class TopicAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "slug",
        "order",
        "is_active",
        "updated_at",
    )

    list_editable = (
        "order",
        "is_active",
    )

    list_filter = (
        "is_active",
    )

    search_fields = (
        "name",
        "slug",
        "description",
    )

    prepopulated_fields = {
        "slug": (
            "name",
        ),
    }

    ordering = (
        "order",
        "name",
    )

    inlines = (
        SkillInline,
    )


class QuestionFamilyInline(admin.TabularInline):
    model = QuestionFamily
    extra = 0
    show_change_link = True

    fields = (
        "name",
        "slug",
        "order",
        "is_active",
    )

    ordering = (
        "order",
        "name",
    )

    prepopulated_fields = {
        "slug": (
            "name",
        ),
    }


@admin.register(Skill)
class SkillAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "topic",
        "order",
        "is_active",
        "updated_at",
    )

    list_editable = (
        "order",
        "is_active",
    )

    list_filter = (
        "topic",
        "is_active",
    )

    search_fields = (
        "name",
        "slug",
        "description",
        "topic__name",
    )

    list_select_related = (
        "topic",
    )

    prepopulated_fields = {
        "slug": (
            "name",
        ),
    }

    ordering = (
        "topic__order",
        "order",
        "name",
    )

    inlines = (
        QuestionFamilyInline,
    )


@admin.register(QuestionFamily)
class QuestionFamilyAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "skill",
        "topic_display",
        "order",
        "is_active",
        "updated_at",
    )

    list_editable = (
        "order",
        "is_active",
    )

    list_filter = (
        "skill__topic",
        "skill",
        "is_active",
    )

    search_fields = (
        "name",
        "slug",
        "assessment_goal",
        "skill__name",
        "skill__topic__name",
    )

    list_select_related = (
        "skill",
        "skill__topic",
    )

    prepopulated_fields = {
        "slug": (
            "name",
        ),
    }

    ordering = (
        "skill__topic__order",
        "skill__order",
        "order",
        "name",
    )

    @admin.display(
        description="Тематика",
        ordering="skill__topic__name",
    )
    def topic_display(self, obj):
        return obj.skill.topic
