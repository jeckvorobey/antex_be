"""JWT и валидация Telegram initData."""

from __future__ import annotations

import hashlib
import hmac
import time
from typing import Any
from urllib.parse import parse_qs

import jwt

from app.core.config import settings


def create_access_token(data: dict[str, Any], ttl: int | None = None) -> str:
    expire = time.time() + (ttl or settings.jwt_ttl_seconds)
    return jwt.encode({**data, "exp": expire}, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict[str, Any]:
    return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])


def validate_telegram_init_data(init_data: str) -> dict[str, Any] | None:
    """Валидация Telegram Mini App initData (HMAC-SHA256)."""
    if not settings.telegram_bot_token:
        return None

    parsed = parse_qs(init_data)
    received_hash = parsed.get("hash", [None])[0]
    if not received_hash:
        return None

    data_check_items = []
    for key, values in sorted(parsed.items()):
        if key != "hash":
            data_check_items.append(f"{key}={values[0]}")
    data_check_string = "\n".join(data_check_items)

    secret_key = hmac.new(
        b"WebAppData", settings.telegram_bot_token.encode(), hashlib.sha256
    ).digest()
    computed_hash = hmac.new(
        secret_key, data_check_string.encode(), hashlib.sha256
    ).hexdigest()

    if not hmac.compare_digest(computed_hash, received_hash):
        return None

    auth_date = parsed.get("auth_date", [None])[0]
    if auth_date and (time.time() - int(auth_date)) > settings.telegram_init_data_ttl_seconds:
        return None

    return {k: v[0] for k, v in parsed.items()}
