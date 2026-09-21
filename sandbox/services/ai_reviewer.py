import json
import os

import requests


class AIReviewerError(Exception):
    """Ошибка обращения к AI reviewer."""


REQUIRED_CHECKS = {
    "greeting",
    "problem_description",
    "solution",
    "completeness",
    "direct_answer",
    "client_language",
    "structure_and_grammar",
}

ALLOWED_SEVERITIES = {
    "ok",
    "minor",
    "critical",
}


def review_trainee_answer(task, client_answer):
    agent_id = os.getenv("TWC_AI_AGENT_ID", "").strip()
    token = os.getenv("TWC_AI_TOKEN", "").strip()

    if not agent_id:
        raise AIReviewerError("TWC_AI_AGENT_ID is not configured")

    if not token:
        raise AIReviewerError("TWC_AI_TOKEN is not configured")

    if not task.ai_review_context:
        raise AIReviewerError(
            f"AI review context is not configured for task {task.slug}"
        )

    if not client_answer.strip():
        raise AIReviewerError("Client answer is empty")

    url = (
        "https://agent.timeweb.cloud/api/v1/cloud-ai/agents/"
        f"{agent_id}/v1/chat/completions"
    )

    payload = {
        "messages": [
            {
                "role": "user",
                "content": build_review_input(
                    task=task,
                    client_answer=client_answer,
                ),
            }
        ],
        "stream": False,
    }

    try:
        response = requests.post(
            url,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=30,
        )
        response.raise_for_status()
    except requests.RequestException as error:
        raise AIReviewerError(
            f"AI reviewer request failed: {error}"
        ) from error

    try:
        api_response = response.json()
        content = api_response["choices"][0]["message"]["content"]
        review = json.loads(content)
    except (ValueError, KeyError, IndexError, TypeError) as error:
        raise AIReviewerError(
            "AI reviewer returned an invalid response"
        ) from error

    validate_review_response(review)

    return review


def build_review_input(task, client_answer):
    context = task.ai_review_context

    required_client_facts = context.get(
        "required_client_facts",
        [],
    )

    if required_client_facts:
        required_facts_text = "\n".join(
            f"- {fact}"
            for fact in required_client_facts
        )
    else:
        required_facts_text = "Нет."

    return (
        "Условие задания:\n"
        f"Имя клиента: {task.client_name}\n"
        f"Тема обращения: {task.ticket_title}\n\n"
        "Сообщение клиента:\n"
        f"{task.description}\n\n"
        "Известные факты:\n"
        f"Причина проблемы: {context.get('root_cause', '')}\n"
        f"Выполненное решение: {context.get('resolution', '')}\n"
        f"Итоговое состояние: {context.get('result', '')}\n"
        "Обязательные факты для клиента:\n"
        f"{required_facts_text}\n\n"
        "Ответ стажёра:\n"
        f"{client_answer}"
    )


def validate_review_response(review):
    if not isinstance(review, dict):
        raise AIReviewerError("AI reviewer returned an invalid response structure")

    checks = review.get("checks")
    recommendations = review.get("recommendations")

    if not isinstance(checks, dict):
        raise AIReviewerError("AI reviewer returned an invalid response structure")

    if set(checks) != REQUIRED_CHECKS:
        raise AIReviewerError("AI reviewer returned an invalid response structure")

    for check_name, check in checks.items():
        if not isinstance(check, dict):
            raise AIReviewerError(
                "AI reviewer returned an invalid response structure"
            )

        if not isinstance(check.get("passed"), bool):
            raise AIReviewerError(
                "AI reviewer returned an invalid response structure"
            )

        if check.get("severity") not in ALLOWED_SEVERITIES:
            raise AIReviewerError(
                "AI reviewer returned an invalid response structure"
            )

        if not isinstance(check.get("comment"), str):
            raise AIReviewerError(
                "AI reviewer returned an invalid response structure"
            )

        if check_name == "completeness":
            missing_facts = check.get("missing_facts")

            if not isinstance(missing_facts, list) or not all(
                isinstance(fact, str)
                for fact in missing_facts
            ):
                raise AIReviewerError(
                    "AI reviewer returned an invalid response structure"
                )

    if not isinstance(recommendations, list) or not all(
        isinstance(recommendation, str)
        for recommendation in recommendations
    ):
        raise AIReviewerError(
            "AI reviewer returned an invalid response structure"
        )
