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
