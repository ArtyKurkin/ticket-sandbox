from django.contrib import admin
from django.forms.models import BaseInlineFormSet

from .constants import (
    QuestionStatus,
    QuestionType,
)
from .question_validation import (
    validate_answer_configuration,
    validate_line_selection_configuration,
    validate_matching_configuration,
    validate_ordering_configuration,
)

from .models import (
    AnswerOption,
    BlueprintSkillQuota,
    ExamBlueprint,
    MatchingPair,
    OrderingItem,
    Question,
    QuestionFamily,
    SelectableLine,
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

        if self.instance.answer_type not in {
            QuestionType.SINGLE_CHOICE,
            QuestionType.MULTIPLE_CHOICE,
        }:
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


class MatchingPairInlineFormSet(BaseInlineFormSet):
    def clean(self):
        super().clean()

        if any(self.errors):
            return

        if self.instance.status != QuestionStatus.ACTIVE:
            return

        if self.instance.answer_type != QuestionType.MATCHING:
            return

        pairs = []

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

            pairs.append(
                {
                    "left_text": cleaned_data.get(
                        "left_text"
                    ),
                    "right_text": cleaned_data.get(
                        "right_text"
                    ),
                }
            )

        validate_matching_configuration(
            pairs=pairs,
        )


class MatchingPairInline(admin.TabularInline):
    model = MatchingPair
    formset = MatchingPairInlineFormSet
    extra = 4

    fields = (
        "left_text",
        "right_text",
        "order",
    )

    ordering = (
        "order",
        "id",
    )


class OrderingItemInlineFormSet(BaseInlineFormSet):
    def clean(self):
        super().clean()

        if any(self.errors):
            return

        if self.instance.status != QuestionStatus.ACTIVE:
            return

        if self.instance.answer_type != QuestionType.ORDERING:
            return

        items = []

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

            items.append(
                {
                    "text": cleaned_data.get("text"),
                }
            )

        validate_ordering_configuration(
            items=items,
        )


class OrderingItemInline(admin.TabularInline):
    model = OrderingItem
    formset = OrderingItemInlineFormSet
    extra = 5

    fields = (
        "text",
        "order",
    )

    ordering = (
        "order",
        "id",
    )


class SelectableLineInlineFormSet(BaseInlineFormSet):
    def clean(self):
        super().clean()

        if any(self.errors):
            return

        if self.instance.status != QuestionStatus.ACTIVE:
            return

        if (
            self.instance.answer_type
            != QuestionType.LINE_SELECTION
        ):
            return

        lines = []

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

            lines.append(
                {
                    "text": cleaned_data.get("text"),
                    "is_correct": cleaned_data.get(
                        "is_correct",
                        False,
                    ),
                }
            )

        validate_line_selection_configuration(
            lines=lines,
        )


class SelectableLineInline(admin.TabularInline):
    model = SelectableLine
    formset = SelectableLineInlineFormSet
    extra = 6

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
        MatchingPairInline,
        OrderingItemInline,
        SelectableLineInline,
    )

    @admin.display(
        description="Тематика",
        ordering="family__skill__topic__name",
    )
    def topic_display(self, obj):
        return obj.family.skill.topic


class BlueprintSkillQuotaInline(admin.TabularInline):
    model = BlueprintSkillQuota
    extra = 0

    fields = (
        "skill",
        "question_count",
        "order",
    )

    ordering = (
        "order",
        "skill__topic__order",
        "skill__order",
        "skill__name",
    )

    autocomplete_fields = (
        "skill",
    )


@admin.register(ExamBlueprint)
class ExamBlueprintAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "level",
        "question_count_display",
        "pass_percentage",
        "allow_back_navigation",
        "is_active",
        "updated_at",
    )

    list_editable = (
        "pass_percentage",
        "is_active",
    )

    list_filter = (
        "level",
        "is_active",
        "allow_back_navigation",
    )

    search_fields = (
        "name",
        "slug",
    )

    prepopulated_fields = {
        "slug": (
            "name",
        ),
    }

    readonly_fields = (
        "created_at",
        "updated_at",
    )

    fieldsets = (
        (
            "Основные настройки",
            {
                "fields": (
                    "name",
                    "slug",
                    "level",
                    "pass_percentage",
                    "is_active",
                ),
            },
        ),
        (
            "Прохождение",
            {
                "fields": (
                    "allow_back_navigation",
                    "shuffle_questions",
                    "shuffle_answer_options",
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
        BlueprintSkillQuotaInline,
    )

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .prefetch_related("skill_quotas")
        )

    @admin.display(
        description="Вопросов",
    )
    def question_count_display(self, obj):
        return obj.question_count
