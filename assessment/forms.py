from django import forms
from django.db.models import Q
from django.core.exceptions import ValidationError
from django.forms import (
    BaseInlineFormSet,
    inlineformset_factory,
)

from assessment.constants import (
    QuestionStatus,
    QuestionType,
)
from assessment.models import (
    AnswerOption,
    MatchingPair,
    OrderingItem,
    Question,
    QuestionDiagnosticBlock,
    QuestionFamily,
    SelectableLine,
    Skill,
)
from assessment.question_validation import (
    validate_answer_configuration,
    validate_line_selection_configuration,
    validate_matching_configuration,
    validate_ordering_configuration,
)


class SkillChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        return (
            f"{obj.topic.name} → "
            f"{obj.name}"
        )


class QuestionFamilyChoiceField(
    forms.ModelChoiceField
):
    def label_from_instance(self, obj):
        return (
            f"{obj.skill.topic.name} → "
            f"{obj.skill.name} → "
            f"{obj.name}"
        )


class QuestionEditorForm(forms.ModelForm):
    family = QuestionFamilyChoiceField(
        queryset=QuestionFamily.objects.none(),
        label="Семейство вопросов",
    )

    class Meta:
        model = Question

        fields = (
            "family",
            "title",
            "level",
            "difficulty",
            "scenario",
            "prompt",
            "answer_type",
            "time_limit_seconds",
            "explanation",
            "status",
        )

        widgets = {
            "scenario": forms.Textarea(
                attrs={
                    "rows": 4,
                    "placeholder": (
                        "Опиши ситуацию, которую "
                        "видит сотрудник."
                    ),
                }
            ),
            "prompt": forms.Textarea(
                attrs={
                    "rows": 4,
                    "placeholder": (
                        "Что сотрудник должен "
                        "определить или выбрать?"
                    ),
                }
            ),
            "explanation": forms.Textarea(
                attrs={
                    "rows": 4,
                    "placeholder": (
                        "Почему этот ответ правильный? "
                        "Сотруднику пока не показывается."
                    ),
                }
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(
            *args,
            **kwargs,
        )

        families = (
            QuestionFamily.objects
            .filter(
                is_active=True,
                skill__is_active=True,
                skill__topic__is_active=True,
            )
            .select_related(
                "skill",
                "skill__topic",
            )
            .order_by(
                "skill__topic__order",
                "skill__order",
                "order",
                "name",
            )
        )

        # Если редактируем старый вопрос,
        # его текущее семейство должно остаться
        # доступным даже после отключения.
        if (
            self.instance
            and self.instance.pk
            and self.instance.family_id
        ):
            families = (
                QuestionFamily.objects
                .filter(
                    Q(
                        is_active=True,
                        skill__is_active=True,
                        skill__topic__is_active=True,
                    )
                    | Q(
                        pk=self.instance.family_id
                    )
                )
                .select_related(
                    "skill",
                    "skill__topic",
                )
                .distinct()
                .order_by(
                    "skill__topic__order",
                    "skill__order",
                    "order",
                    "name",
                )
            )

        self.fields["family"].queryset = (
            families
        )
        self.fields[
            "family"
        ].empty_label = "Выбери семейство"


class AnswerOptionFormSet(
    BaseInlineFormSet
):
    def clean(self):
        super().clean()

        if any(self.errors):
            return

        if (
            self.instance.status
            != QuestionStatus.ACTIVE
        ):
            return

        if self.instance.answer_type not in {
            QuestionType.SINGLE_CHOICE,
            QuestionType.MULTIPLE_CHOICE,
        }:
            return

        options = []

        for form in self.forms:
            data = form.cleaned_data

            if (
                not data
                or data.get("DELETE")
            ):
                continue

            options.append(
                {
                    "text": data.get(
                        "text",
                        "",
                    ),
                    "is_correct": data.get(
                        "is_correct",
                        False,
                    ),
                }
            )

        try:
            validate_answer_configuration(
                answer_type=(
                    self.instance.answer_type
                ),
                options=options,
            )
        except ValidationError as error:
            raise ValidationError(
                error.messages
            )


class MatchingPairFormSet(
    BaseInlineFormSet
):
    def clean(self):
        super().clean()

        if any(self.errors):
            return

        if (
            self.instance.status
            != QuestionStatus.ACTIVE
            or self.instance.answer_type
            != QuestionType.MATCHING
        ):
            return

        pairs = []

        for form in self.forms:
            data = form.cleaned_data

            if (
                not data
                or data.get("DELETE")
            ):
                continue

            pairs.append(
                {
                    "left_text": data.get(
                        "left_text",
                        "",
                    ),
                    "right_text": data.get(
                        "right_text",
                        "",
                    ),
                }
            )

        try:
            validate_matching_configuration(
                pairs=pairs,
            )
        except ValidationError as error:
            raise ValidationError(
                error.messages
            )


class OrderingItemFormSet(
    BaseInlineFormSet
):
    def clean(self):
        super().clean()

        if any(self.errors):
            return

        if (
            self.instance.status
            != QuestionStatus.ACTIVE
            or self.instance.answer_type
            != QuestionType.ORDERING
        ):
            return

        items = []

        for form in self.forms:
            data = form.cleaned_data

            if (
                not data
                or data.get("DELETE")
            ):
                continue

            items.append(
                {
                    "text": data.get(
                        "text",
                        "",
                    ),
                }
            )

        try:
            validate_ordering_configuration(
                items=items,
            )
        except ValidationError as error:
            raise ValidationError(
                error.messages
            )


class SelectableLineFormSet(
    BaseInlineFormSet
):
    def clean(self):
        super().clean()

        if any(self.errors):
            return

        if (
            self.instance.status
            != QuestionStatus.ACTIVE
            or self.instance.answer_type
            != QuestionType.LINE_SELECTION
        ):
            return

        lines = []

        for form in self.forms:
            data = form.cleaned_data

            if (
                not data
                or data.get("DELETE")
            ):
                continue

            lines.append(
                {
                    "text": data.get(
                        "text",
                        "",
                    ),
                    "is_correct": data.get(
                        "is_correct",
                        False,
                    ),
                }
            )

        try:
            validate_line_selection_configuration(
                lines=lines,
            )
        except ValidationError as error:
            raise ValidationError(
                error.messages
            )


class AnswerOptionEditorForm(forms.ModelForm):
    class Meta:
        model = AnswerOption

        fields = (
            "text",
            "is_correct",
            "order",
        )

        widgets = {
            "text": forms.TextInput(
                attrs={
                    "placeholder": "Вариант ответа",
                }
            ),
            "order": forms.HiddenInput(),
        }


class QuestionDiagnosticBlockEditorForm(
    forms.ModelForm
):
    class Meta:
        model = QuestionDiagnosticBlock

        fields = (
            "block_type",
            "content",
            "order",
        )

        widgets = {
            "block_type": forms.HiddenInput(),
            "content": forms.Textarea(
                attrs={
                    "rows": 4,
                    "placeholder": (
                        "Добавь текст или "
                        "диагностические данные"
                    ),
                }
            ),
            "order": forms.HiddenInput(),
        }


class MatchingPairEditorForm(forms.ModelForm):
    class Meta:
        model = MatchingPair

        fields = (
            "left_text",
            "right_text",
            "order",
        )

        widgets = {
            "left_text": forms.TextInput(
                attrs={
                    "placeholder": "Элемент слева",
                }
            ),
            "right_text": forms.TextInput(
                attrs={
                    "placeholder": "Соответствие справа",
                }
            ),
            "order": forms.HiddenInput(),
        }


class OrderingItemEditorForm(forms.ModelForm):
    class Meta:
        model = OrderingItem

        fields = (
            "text",
            "order",
        )

        widgets = {
            "text": forms.TextInput(
                attrs={
                    "placeholder": (
                        "Шаг последовательности"
                    ),
                }
            ),
            "order": forms.HiddenInput(),
        }


class SelectableLineEditorForm(forms.ModelForm):
    class Meta:
        model = SelectableLine

        fields = (
            "text",
            "is_correct",
            "order",
        )

        widgets = {
            "text": forms.TextInput(
                attrs={
                    "placeholder": (
                        "Строка лога или конфигурации"
                    ),
                    "class": (
                        "assessment-line-editor-input"
                    ),
                }
            ),
            "order": forms.HiddenInput(),
        }


class BaseQuestionDiagnosticBlockFormSet(
    forms.BaseInlineFormSet
):
    def clean(self):
        super().clean()

        if any(self.errors):
            return

        for form in self.forms:
            if not hasattr(
                form,
                "cleaned_data",
            ):
                continue

            if form.cleaned_data.get(
                "DELETE"
            ):
                continue

            content = (
                form.cleaned_data.get(
                    "content",
                    ""
                ).strip()
            )

            block_type = (
                form.cleaned_data.get(
                    "block_type"
                )
            )

            # Полностью пустая extra-форма
            # нас не интересует.
            if not content and not block_type:
                continue

            if not content:
                form.add_error(
                    "content",
                    "Блок не может быть пустым.",
                )


AnswerOptionEditorFormSet = (
    inlineformset_factory(
        Question,
        AnswerOption,
        form=AnswerOptionEditorForm,
        formset=AnswerOptionFormSet,
        fields=(
            "text",
            "is_correct",
            "order",
        ),
        extra=0,
        can_delete=True,
    )
)


MatchingPairEditorFormSet = (
    inlineformset_factory(
        Question,
        MatchingPair,
        form=MatchingPairEditorForm,
        formset=MatchingPairFormSet,
        fields=(
            "left_text",
            "right_text",
            "order",
        ),
        extra=0,
        can_delete=True,
    )
)


QuestionDiagnosticBlockEditorFormSet = (
    forms.inlineformset_factory(
        Question,
        QuestionDiagnosticBlock,
        form=QuestionDiagnosticBlockEditorForm,
        formset=(
            BaseQuestionDiagnosticBlockFormSet
        ),
        fields=(
            "block_type",
            "content",
            "order",
        ),
        extra=0,
        can_delete=True,
    )
)


OrderingItemEditorFormSet = (
    inlineformset_factory(
        Question,
        OrderingItem,
        form=OrderingItemEditorForm,
        formset=OrderingItemFormSet,
        fields=(
            "text",
            "order",
        ),
        extra=0,
        can_delete=True,
    )
)


SelectableLineEditorFormSet = (
    inlineformset_factory(
        Question,
        SelectableLine,
        form=SelectableLineEditorForm,
        formset=SelectableLineFormSet,
        fields=(
            "text",
            "is_correct",
            "order",
        ),
        extra=0,
        can_delete=True,
    )
)


class QuestionFamilyEditorForm(forms.ModelForm):
    skill = SkillChoiceField(
        queryset=Skill.objects.none(),
        label="Навык",
    )

    class Meta:
        model = QuestionFamily

        fields = (
            "skill",
            "name",
            "assessment_goal",
            "is_active",
        )

        widgets = {
            "name": forms.TextInput(
                attrs={
                    "placeholder": (
                        "Например: высокий load из-за I/O"
                    ),
                }
            ),
            "assessment_goal": forms.Textarea(
                attrs={
                    "rows": 4,
                    "placeholder": (
                        "Что именно должен уметь "
                        "определить сотрудник?"
                    ),
                }
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(
            *args,
            **kwargs,
        )

        self.fields["skill"].queryset = (
            Skill.objects
            .filter(
                is_active=True,
                topic__is_active=True,
            )
            .select_related("topic")
            .order_by(
                "topic__order",
                "order",
                "name",
            )
        )
