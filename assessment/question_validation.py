from django.core.exceptions import ValidationError

from .constants import QuestionType


def validate_answer_configuration(
    *,
    answer_type,
    options,
):
    prepared_options = []

    for option in options:
        text = " ".join(
            str(option.get("text", "")).split()
        )

        if not text:
            continue

        prepared_options.append(
            {
                "text": text,
                "is_correct": bool(
                    option.get("is_correct")
                ),
            }
        )

    if len(prepared_options) < 2:
        raise ValidationError(
            "Добавь минимум два варианта ответа."
        )

    normalized_texts = [
        option["text"].casefold()
        for option in prepared_options
    ]

    if len(normalized_texts) != len(
        set(normalized_texts)
    ):
        raise ValidationError(
            "Варианты ответа не должны повторяться."
        )

    correct_count = sum(
        option["is_correct"]
        for option in prepared_options
    )

    if answer_type == QuestionType.SINGLE_CHOICE:
        if correct_count != 1:
            raise ValidationError(
                "Для одиночного выбора должен быть "
                "ровно один правильный ответ."
            )

        return

    if answer_type == QuestionType.MULTIPLE_CHOICE:
        if correct_count < 2:
            raise ValidationError(
                "Для множественного выбора отметь "
                "минимум два правильных ответа."
            )

        if correct_count == len(prepared_options):
            raise ValidationError(
                "Для множественного выбора должен быть "
                "минимум один неправильный вариант."
            )

        return

    raise ValidationError(
        "Неизвестный тип вопроса."
    )


def _normalize_text(value):
    return " ".join(
        str(value or "").split()
    )


def validate_matching_configuration(*, pairs):
    prepared_pairs = []

    for pair in pairs:
        left_text = _normalize_text(
            pair.get("left_text")
        )
        right_text = _normalize_text(
            pair.get("right_text")
        )

        if not left_text and not right_text:
            continue

        prepared_pairs.append(
            {
                "left_text": left_text,
                "right_text": right_text,
            }
        )

    if len(prepared_pairs) < 2:
        raise ValidationError(
            "Добавь минимум две пары "
            "для сопоставления."
        )

    left_values = [
        pair["left_text"].casefold()
        for pair in prepared_pairs
    ]

    right_values = [
        pair["right_text"].casefold()
        for pair in prepared_pairs
    ]

    if len(left_values) != len(set(left_values)):
        raise ValidationError(
            "Левые части пар не должны повторяться."
        )

    if len(right_values) != len(set(right_values)):
        raise ValidationError(
            "Правые части пар не должны повторяться."
        )


def validate_ordering_configuration(*, items):
    prepared_items = [
        _normalize_text(item.get("text"))
        for item in items
    ]

    prepared_items = [
        text
        for text in prepared_items
        if text
    ]

    if len(prepared_items) < 3:
        raise ValidationError(
            "Добавь минимум три элемента "
            "последовательности."
        )

    normalized_items = [
        text.casefold()
        for text in prepared_items
    ]

    if len(normalized_items) != len(
        set(normalized_items)
    ):
        raise ValidationError(
            "Элементы последовательности "
            "не должны повторяться."
        )


def validate_line_selection_configuration(*, lines):
    prepared_lines = []

    for line in lines:
        text = _normalize_text(
            line.get("text")
        )

        if not text:
            continue

        prepared_lines.append(
            {
                "text": text,
                "is_correct": bool(
                    line.get("is_correct")
                ),
            }
        )

    if len(prepared_lines) < 2:
        raise ValidationError(
            "Добавь минимум две строки."
        )

    normalized_lines = [
        line["text"].casefold()
        for line in prepared_lines
    ]

    if len(normalized_lines) != len(
        set(normalized_lines)
    ):
        raise ValidationError(
            "Строки не должны повторяться."
        )

    correct_count = sum(
        line["is_correct"]
        for line in prepared_lines
    )

    if correct_count == 0:
        raise ValidationError(
            "Отметь минимум одну строку, "
            "которую должен выбрать сотрудник."
        )

    if correct_count == len(prepared_lines):
        raise ValidationError(
            "Минимум одна строка должна быть "
            "неправильной."
        )
