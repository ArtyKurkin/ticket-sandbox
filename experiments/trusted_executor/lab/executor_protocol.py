"""Lab-only authenticated request protocol."""

import hashlib
import hmac
import json
import secrets
import time
from uuid import UUID

MAX_BODY = 512
MAX_AGE = 30


def validate_run_id(value):
    if type(value) is not str:
        raise ValueError("invalid_run_id")
    try:
        parsed = UUID(value)
    except (ValueError, AttributeError, TypeError):
        raise ValueError("invalid_run_id") from None
    if str(parsed) != value:
        raise ValueError("noncanonical_run_id")
    return value


def make_request(run_id, secret):
    validate_run_id(run_id)
    data = {
        "run_id": run_id,
        "timestamp": int(time.time()),
        "nonce": secrets.token_hex(16),
    }
    body = json.dumps(data, separators=(",", ":")).encode()
    signature = hmac.new(secret, body, hashlib.sha256).hexdigest()
    return body, signature


def verify_request(body, signature, secret, now=None):
    if type(body) is not bytes or len(body) > MAX_BODY:
        raise ValueError("invalid_body")

    if type(signature) is not str or len(signature) != 64:
        raise ValueError("invalid_signature")

    expected = hmac.new(secret, body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature):
        raise ValueError("invalid_signature")

    try:
        data = json.loads(body)
    except (ValueError, UnicodeDecodeError):
        raise ValueError("invalid_json") from None

    if type(data) is not dict or set(data) != {
        "run_id", "timestamp", "nonce"
    }:
        raise ValueError("invalid_schema")

    validate_run_id(data["run_id"])

    timestamp = data["timestamp"]
    if type(timestamp) is not int:
        raise ValueError("invalid_timestamp")

    current = int(time.time()) if now is None else now
    if abs(current - timestamp) > MAX_AGE:
        raise ValueError("expired_request")

    nonce = data["nonce"]
    if (
        type(nonce) is not str
        or len(nonce) != 32
        or any(c not in "0123456789abcdef" for c in nonce)
    ):
        raise ValueError("invalid_nonce")

    return data
