from django import forms
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
    SelectableLine,
)
from assessment.question_validation import (
    validate_answer_configuration,
    validate_line_selection_configuration,
    validate_matching_configuration,
    validate_ordering_configuration,
)


class QuestionEditorForm(forms.ModelForm):
    class Meta:
        model = Question

        fields = (
            "family",
            "title",
            "level",
            "difficulty",
            "scenario",
            "diagnostic_data",
            "prompt",
            "answer_type",
            "time_limit_seconds",
            "explanation",
            "status",
            "order",
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
            "diagnostic_data": forms.Textarea(
                attrs={
                    "rows": 10,
                    "class": "assessment-editor-code",
                    "placeholder": (
                        "Логи, конфиг, вывод команд..."
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
        extra=4,
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
        extra=4,
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
        extra=4,
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
        extra=6,
        can_delete=True,
    )
)
