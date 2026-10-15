"""Server-owned navigation. Producing links never prepares tasks or changes progress."""
import re
from urllib.parse import urlsplit

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import URLValidator
from django.urls import reverse


UNCONFIGURED_TRAINING = "Ссылка на программу Teachbase не настроена. Обратитесь к наставнику."
INVALID_TRAINING = "Переход к программе Teachbase недоступен: проверьте настройку ссылки и разрешённого хоста."
NO_PERSONAL_DIARY = "Персональная страница дневника для стажёра пока недоступна. Прогресс показан в этой карточке."
NO_PERSONAL_RESULT = "Отдельная страница результата ИС для стажёра пока недоступна. Фактический результат показан в этой карточке."


def training_destination():
    """Only explicit operator configuration, HTTPS and an exact allowed hostname."""
    url = settings.ROADMAP_TEACHBASE_URL
    if not url:
        return None, UNCONFIGURED_TRAINING
    if not isinstance(url, str) or re.search(r"[\s\\\x00-\x1f\x7f]", url):
        return None, INVALID_TRAINING
    try:
        URLValidator(schemes=["https"])(url)
        parsed = urlsplit(url)
        allowed_hosts = {host.lower() for host in settings.ROADMAP_TEACHBASE_ALLOWED_HOSTS}
        if (parsed.scheme != "https" or not parsed.hostname
                or parsed.hostname.lower() not in allowed_hosts
                or parsed.username is not None or parsed.password is not None
                or parsed.port not in (None, 443)):
            return None, INVALID_TRAINING
    except (ValidationError, ValueError, TypeError, AttributeError):
        return None, INVALID_TRAINING
    return url, None


def external_action_hosts():
    """Bootstrap only the validated destination host, not a client supplied allowlist."""
    url, _ = training_destination()
    return [urlsplit(url).hostname.lower()] if url else []


def _action(code, label, url, *, enabled=True, kind="learning", external=False, reason=None):
    action = {
        "code": code, "label": label, "url": url, "enabled": enabled,
        "kind": kind, "external": external,
    }
    if reason:
        action["reason"] = reason
    return action


def attach_actions(stages, *, journey, viewer):
    if (journey is None or viewer is None or not viewer.is_authenticated
            or not (viewer.is_staff or viewer.pk == journey.user_id)):
        return
    for stage in stages:
        if stage["availability"] != "enabled" or not stage["applicable"]:
            continue
        unlocked = stage["state"] is not None and stage["state"] != "locked"
        if stage["id"] == "training":
            url, reason = training_destination()
            stage["actions"] = [_action(
                "open_training", "Перейти к обучению", url,
                enabled=bool(url) and unlocked, external=True,
                reason=reason or (None if unlocked else "Этот этап пока заблокирован."),
            )]
        elif stage["id"] == "sandbox":
            stage["actions"] = [_action(
                "open_sandbox", "Перейти к заданиям", reverse("sandbox:dashboard"),
                enabled=unlocked, reason=None if unlocked else "Этот этап пока заблокирован.",
            )]
        elif stage["id"] in {"with_review", "optional_review", "no_review", "probation"}:
            if viewer.is_staff:
                is_result = stage["id"] == "probation" and stage["evidence"]["outcome"] != "active"
                stage["actions"] = [_action(
                    "view_probation_result" if is_result else "view_adaptation",
                    "Посмотреть результат ИС" if is_result else "Открыть адаптацию",
                    reverse("traineediary:trainee_detail", args=[journey.pk]), kind="view",
                )]
            else:
                stage["action_notice"] = NO_PERSONAL_RESULT if stage["id"] == "probation" else NO_PERSONAL_DIARY
