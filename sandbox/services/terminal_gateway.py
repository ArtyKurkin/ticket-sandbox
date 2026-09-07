import logging
import os
import re

from django.conf import settings

terminal_logger = logging.getLogger("sandbox.terminal")

HOST_PORT_MODE = "host_port"
DOCKER_NETWORK_MODE = "docker_network"


def terminal_network_mode():
    return settings.TERMINAL_NETWORK_MODE


def terminal_uses_docker_network():
    return terminal_network_mode() == DOCKER_NETWORK_MODE


def terminal_gateway_enabled():
    return os.getenv(
        "TERMINAL_GATEWAY_ENABLED",
        "false",
    ).lower() in ("1", "true", "yes")


def build_terminal_base_path(attempt_id, port=None):
    if not terminal_gateway_enabled():
        return ""

    if terminal_uses_docker_network():
        return f"/terminal/{attempt_id}/"

    if port is None:
        raise ValueError(
            "Для режима host_port необходимо указать порт терминала"
        )

    return f"/terminal/{attempt_id}/{port}/"


def build_terminal_url(attempt_id, port=None):
    if terminal_gateway_enabled():
        return build_terminal_base_path(
            attempt_id=attempt_id,
            port=port,
        )

    if port is None:
        raise ValueError(
            "Для прямого подключения к терминалу необходимо указать порт"
        )

    external_host = os.getenv("EXTERNAL_HOST", "localhost")

    return f"http://{external_host}:{port}"


def parse_terminal_uri(original_uri):
    if terminal_uses_docker_network():
        match = re.match(
            r"^/terminal/(?P<attempt_id>\d+)(?:/|$)",
            original_uri,
        )

        if not match:
            return None, None

        return int(match.group("attempt_id")), None

    match = re.match(
        r"^/terminal/(?P<attempt_id>\d+)/(?P<port>2\d{4}|30000)/",
        original_uri,
    )

    if not match:
        return None, None

    return (
        int(match.group("attempt_id")),
        int(match.group("port")),
    )


def log_terminal_auth_denied(request, reason, attempt_id=None, port=None, **kwargs):
    user_id = request.user.id if request.user.is_authenticated else None
    original_uri = request.META.get("HTTP_X_ORIGINAL_URI", request.path)

    details = " ".join(
        f"{key}={value}"
        for key, value in kwargs.items()
    )

    terminal_logger.warning(
        "terminal_auth_denied reason=%s user_id=%s attempt_id=%s port=%s original_uri=%s %s",
        reason,
        user_id,
        attempt_id,
        port,
        original_uri,
        details,
    )
