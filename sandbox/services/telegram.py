import logging
import os

import requests

logger = logging.getLogger("sandbox.telegram")


def send_telegram(text: str) -> bool:
    """
    Отправляет сообщение в Telegram.

    Если TELEGRAM_BOT_TOKEN или TELEGRAM_CHAT_ID не заданы,
    уведомления считаются выключенными.

    Важно: Telegram не должен ломать основной пользовательский сценарий.
    Поэтому любые ошибки отправки логируются, но наружу не пробрасываются.
    """
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()

    if not token or not chat_id:
        return False

    try:
        response = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={
                "chat_id": chat_id,
                "text": text,
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
            },
            timeout=5,
        )
        response.raise_for_status()
    except requests.RequestException as error:
        logger.warning(
            "Не удалось отправить Telegram-уведомление: %s",
            error,
        )
        return False

    return True
