from decimal import Decimal, ROUND_HALF_UP

from django.core.exceptions import ValidationError

from assessment.constants import QuestionType


HUNDRED = Decimal("100.00")


def _percentage(correct, total):
    if total <= 0:
        return Decimal("0.00")

    result = (
        Decimal(correct)
        / Decimal(total)
        * HUNDRED
    )

    return result.quantize(
        Decimal("0.01"),
        rounding=ROUND_HALF_UP,
    )


def _get_selected_keys(
    response_payload,
    *,
    available_keys,
):
    selected_keys = response_payload.get(
        "selected_keys"
    )

    if not isinstance(selected_keys, list):
        raise ValidationError(
            "Ответ должен содержать список selected_keys."
        )

    if not selected_keys:
        raise ValidationError(
            "Выбери хотя бы один вариант."
        )

    if len(selected_keys) != len(
        set(selected_keys)
    ):
        raise ValidationError(
            "Один вариант нельзя выбрать несколько раз."
        )

    unknown_keys = (
        set(selected_keys)
        - set(available_keys)
    )

    if unknown_keys:
        raise ValidationError(
            "Ответ содержит неизвестный вариант."
        )

    return selected_keys


def _grade_choice(snapshot, response_payload):
    available_keys = [
        option["key"]
        for option in snapshot.visible_payload.get(
            "options",
            []
        )
    ]

    selected_keys = _get_selected_keys(
        response_payload,
        available_keys=available_keys,
    )

    if (
        snapshot.question_type
        == QuestionType.SINGLE_CHOICE
        and len(selected_keys) != 1
    ):
        raise ValidationError(
            "Для этого вопроса можно выбрать "
            "только один ответ."
        )

    correct_keys = set(
        snapshot.grading_payload.get(
            "correct_keys",
            []
        )
    )

    if set(selected_keys) == correct_keys:
        return HUNDRED

    return Decimal("0.00")


def _grade_matching(snapshot, response_payload):
    submitted_matches = response_payload.get(
        "matches"
    )

    if not isinstance(submitted_matches, dict):
        raise ValidationError(
            "Ответ должен содержать объект matches."
        )

    left_keys = {
        item["key"]
        for item in snapshot.visible_payload.get(
            "left_items",
            []
        )
    }

    right_keys = {
        item["key"]
        for item in snapshot.visible_payload.get(
            "right_items",
            []
        )
    }

    if set(submitted_matches.keys()) != left_keys:
        raise ValidationError(
            "Необходимо сопоставить все элементы."
        )

    submitted_right_keys = list(
        submitted_matches.values()
    )

    if (
        set(submitted_right_keys)
        != right_keys
        or len(submitted_right_keys)
        != len(set(submitted_right_keys))
    ):
        raise ValidationError(
            "Каждый элемент справа должен быть "
            "использован ровно один раз."
        )

    correct_matches = (
        snapshot.grading_payload.get(
            "matches",
            {}
        )
    )

    correct_count = sum(
        submitted_matches[left_key]
        == correct_matches.get(left_key)
        for left_key in left_keys
    )

    return _percentage(
        correct_count,
        len(left_keys),
    )


def _grade_ordering(snapshot, response_payload):
    submitted_order = response_payload.get(
        "order"
    )

    if not isinstance(submitted_order, list):
        raise ValidationError(
            "Ответ должен содержать список order."
        )

    correct_order = (
        snapshot.grading_payload.get(
            "correct_order",
            []
        )
    )

    if (
        len(submitted_order) != len(correct_order)
        or set(submitted_order) != set(correct_order)
    ):
        raise ValidationError(
            "Необходимо расположить все элементы."
        )

    if len(submitted_order) != len(
        set(submitted_order)
    ):
        raise ValidationError(
            "Элементы последовательности "
            "не должны повторяться."
        )

    if len(correct_order) < 2:
        raise ValidationError(
            "Недостаточно элементов "
            "для проверки последовательности."
        )

    submitted_positions = {
        key: position
        for position, key in enumerate(
            submitted_order
        )
    }

    correct_pairs = 0
    total_pairs = 0

    for first_index in range(
        len(correct_order)
    ):
        for second_index in range(
            first_index + 1,
            len(correct_order),
        ):
            first_key = correct_order[
                first_index
            ]
            second_key = correct_order[
                second_index
            ]

            total_pairs += 1

            if (
                submitted_positions[first_key]
                < submitted_positions[second_key]
            ):
                correct_pairs += 1

    return _percentage(
        correct_pairs,
        total_pairs,
    )


def _grade_line_selection(
    snapshot,
    response_payload,
):
    available_keys = [
        line["key"]
        for line in snapshot.visible_payload.get(
            "lines",
            []
        )
    ]

    selected_keys = _get_selected_keys(
        response_payload,
        available_keys=available_keys,
    )

    correct_keys = set(
        snapshot.grading_payload.get(
            "correct_keys",
            []
        )
    )

    if set(selected_keys) == correct_keys:
        return HUNDRED

    return Decimal("0.00")


def grade_snapshot_answer(
    snapshot,
    response_payload,
):
    if not isinstance(response_payload, dict):
        raise ValidationError(
            "Некорректный формат ответа."
        )

    if snapshot.question_type in {
        QuestionType.SINGLE_CHOICE,
        QuestionType.MULTIPLE_CHOICE,
    }:
        return _grade_choice(
            snapshot,
            response_payload,
        )

    if (
        snapshot.question_type
        == QuestionType.MATCHING
    ):
        return _grade_matching(
            snapshot,
            response_payload,
        )

    if (
        snapshot.question_type
        == QuestionType.ORDERING
    ):
        return _grade_ordering(
            snapshot,
            response_payload,
        )

    if (
        snapshot.question_type
        == QuestionType.LINE_SELECTION
    ):
        return _grade_line_selection(
            snapshot,
            response_payload,
        )

    raise ValidationError(
        "Неизвестный тип вопроса."
    )
