from django.contrib import admin
from django.forms.models import BaseInlineFormSet

from .constants import QuestionStatus
from .question_validation import (
    validate_answer_configuration,
)

from .models import (
    AnswerOption,
    Question,
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


class AnswerOptionInlineFormSet(BaseInlineFormSet):
    def clean(self):
        super().clean()

        if any(self.errors):
            return

        if self.instance.status != QuestionStatus.ACTIVE:
            return

        options = []

        for form in self.forms:
            cleaned_data = getattr(
                form,
                "cleaned_data",
                None,
            )

            if not cleaned_data:
                continue

            if cleaned_data.get("DELETE"):
                continue

            text = cleaned_data.get("text")

            if not text:
                continue

            options.append(
                {
                    "text": text,
                    "is_correct": cleaned_data.get(
                        "is_correct",
                        False,
                    ),
                }
            )

        validate_answer_configuration(
            answer_type=self.instance.answer_type,
            options=options,
        )


class AnswerOptionInline(admin.TabularInline):
    model = AnswerOption
    formset = AnswerOptionInlineFormSet
    extra = 4

    fields = (
        "text",
        "is_correct",
        "order",
    )

    ordering = (
        "order",
        "id",
    )


@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "family",
        "topic_display",
        "level",
        "difficulty",
        "answer_type",
        "time_limit_seconds",
        "status",
        "updated_at",
    )

    list_filter = (
        "status",
        "level",
        "difficulty",
        "answer_type",
        "family__skill__topic",
        "family__skill",
    )

    search_fields = (
        "title",
        "slug",
        "scenario",
        "diagnostic_data",
        "prompt",
        "explanation",
        "family__name",
        "family__skill__name",
        "family__skill__topic__name",
    )

    list_select_related = (
        "family",
        "family__skill",
        "family__skill__topic",
    )

    prepopulated_fields = {
        "slug": (
            "title",
        ),
    }

    readonly_fields = (
        "created_at",
        "updated_at",
    )

    ordering = (
        "family__skill__topic__order",
        "family__skill__order",
        "family__order",
        "order",
        "title",
    )

    fieldsets = (
        (
            "Классификация",
            {
                "fields": (
                    "family",
                    "title",
                    "slug",
                    "level",
                    "difficulty",
                    "status",
                    "order",
                ),
            },
        ),
        (
            "Содержание вопроса",
            {
                "fields": (
                    "scenario",
                    "diagnostic_data",
                    "prompt",
                ),
            },
        ),
        (
            "Настройки ответа",
            {
                "fields": (
                    "answer_type",
                    "time_limit_seconds",
                    "explanation",
                ),
            },
        ),
        (
            "Служебная информация",
            {
                "fields": (
                    "created_at",
                    "updated_at",
                ),
                "classes": (
                    "collapse",
                ),
            },
        ),
    )

    inlines = (
        AnswerOptionInline,
    )

    @admin.display(
        description="Тематика",
        ordering="family__skill__topic__name",
    )
    def topic_display(self, obj):
        return obj.family.skill.topic
