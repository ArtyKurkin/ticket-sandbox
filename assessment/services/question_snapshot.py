import hashlib
import random

from django.core.exceptions import ValidationError

from assessment.constants import QuestionType
from assessment.question_validation import (
    validate_answer_configuration,
    validate_line_selection_configuration,
    validate_matching_configuration,
    validate_ordering_configuration,
)


def _build_question_random(seed, question_id):
    value = (
        f"{seed}:question:{question_id}"
    ).encode("utf-8")

    digest = hashlib.sha256(value).digest()

    return random.Random(
        int.from_bytes(
            digest,
            byteorder="big",
        )
    )


def _build_common_snapshot_data(question):
    family = question.family
    skill = family.skill
    topic = skill.topic

    return {
        "source_question": question,
        "topic_name": topic.name,
        "topic_slug": topic.slug,
        "skill_name": skill.name,
        "skill_slug": skill.slug,
        "family_name": family.name,
        "family_slug": family.slug,
        "question_title": question.title,
        "question_slug": question.slug,
        "question_type": question.answer_type,
        "difficulty": question.difficulty,
        "scenario": question.scenario,
        "diagnostic_data": question.diagnostic_data,
        "prompt": question.prompt,
        "time_limit_seconds": (
            question.time_limit_seconds
        ),
        "explanation": question.explanation,
    }


def _build_choice_payload(
    question,
    *,
    rng,
    shuffle,
):
    options = list(
        question.answer_options.order_by(
            "order",
            "id",
        )
    )

    validation_options = [
        {
            "text": option.text,
            "is_correct": option.is_correct,
        }
        for option in options
    ]

    validate_answer_configuration(
        answer_type=question.answer_type,
        options=validation_options,
    )

    if shuffle:
        rng.shuffle(options)

    visible_options = []
    correct_keys = []

    for index, option in enumerate(
        options,
        start=1,
    ):
        key = f"option-{index}"

        visible_options.append(
            {
                "key": key,
                "text": option.text,
            }
        )

        if option.is_correct:
            correct_keys.append(key)

    return {
        "visible_payload": {
            "options": visible_options,
        },
        "grading_payload": {
            "correct_keys": correct_keys,
        },
    }


def _build_matching_payload(
    question,
    *,
    rng,
):
    pairs = list(
        question.matching_pairs.order_by(
            "order",
            "id",
        )
    )

    validate_matching_configuration(
        pairs=[
            {
                "left_text": pair.left_text,
                "right_text": pair.right_text,
            }
            for pair in pairs
        ],
    )

    left_items = []
    right_items = []
    matches = {}

    for index, pair in enumerate(
        pairs,
        start=1,
    ):
        left_key = f"left-{index}"
        right_key = f"right-{index}"

        left_items.append(
            {
                "key": left_key,
                "text": pair.left_text,
            }
        )

        right_items.append(
            {
                "key": right_key,
                "text": pair.right_text,
            }
        )

        matches[left_key] = right_key

    rng.shuffle(right_items)

    return {
        "visible_payload": {
            "left_items": left_items,
            "right_items": right_items,
        },
        "grading_payload": {
            "matches": matches,
        },
    }


def _build_ordering_payload(
    question,
    *,
    rng,
):
    items = list(
        question.ordering_items.order_by(
            "order",
            "id",
        )
    )

    validate_ordering_configuration(
        items=[
            {
                "text": item.text,
            }
            for item in items
        ],
    )

    visible_items = []
    correct_order = []

    for index, item in enumerate(
        items,
        start=1,
    ):
        key = f"item-{index}"

        visible_items.append(
            {
                "key": key,
                "text": item.text,
            }
        )

        correct_order.append(key)

    rng.shuffle(visible_items)

    return {
        "visible_payload": {
            "items": visible_items,
        },
        "grading_payload": {
            "correct_order": correct_order,
        },
    }


def _build_line_selection_payload(question):
    lines = list(
        question.selectable_lines.order_by(
            "order",
            "id",
        )
    )

    validate_line_selection_configuration(
        lines=[
            {
                "text": line.text,
                "is_correct": line.is_correct,
            }
            for line in lines
        ],
    )

    visible_lines = []
    correct_keys = []

    for index, line in enumerate(
        lines,
        start=1,
    ):
        key = f"line-{index}"

        visible_lines.append(
            {
                "key": key,
                "text": line.text,
            }
        )

        if line.is_correct:
            correct_keys.append(key)

    return {
        "visible_payload": {
            "lines": visible_lines,
        },
        "grading_payload": {
            "correct_keys": correct_keys,
        },
    }


def build_question_snapshot_data(
    question,
    *,
    seed,
    shuffle_answer_options,
):
    rng = _build_question_random(
        seed,
        question.pk,
    )

    result = _build_common_snapshot_data(
        question
    )

    if question.answer_type in {
        QuestionType.SINGLE_CHOICE,
        QuestionType.MULTIPLE_CHOICE,
    }:
        result.update(
            _build_choice_payload(
                question,
                rng=rng,
                shuffle=shuffle_answer_options,
            )
        )

        return result

    if question.answer_type == QuestionType.MATCHING:
        result.update(
            _build_matching_payload(
                question,
                rng=rng,
            )
        )

        return result

    if question.answer_type == QuestionType.ORDERING:
        result.update(
            _build_ordering_payload(
                question,
                rng=rng,
            )
        )

        return result

    if (
        question.answer_type
        == QuestionType.LINE_SELECTION
    ):
        result.update(
            _build_line_selection_payload(
                question
            )
        )

        return result

    raise ValidationError(
        "Неизвестный тип вопроса."
    )
