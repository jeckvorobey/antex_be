from __future__ import annotations

import hashlib
import hmac
import time
from urllib.parse import urlencode

import pytest
from pydantic import ValidationError

from app.core import security
from app.core.config import Settings


def test_production_config_requires_jwt_secret() -> None:
    with pytest.raises(ValidationError, match="JWT_SECRET"):
        Settings(app_env="production", jwt_secret=None, _env_file=None)


def test_webhook_config_requires_bot_token_and_host() -> None:
    with pytest.raises(ValidationError, match="TELEGRAM_BOT_TOKEN"):
        Settings(
            telegram_mode="webhook",
            telegram_bot_token=None,
            telegram_webhook_host="https://example.com",
            _env_file=None,
        )

    with pytest.raises(ValidationError, match="TELEGRAM_WEBHOOK_HOST"):
        Settings(
            telegram_mode="webhook",
            telegram_bot_token="123:test",
            telegram_webhook_host=None,
            _env_file=None,
        )


def test_webhook_config_requires_secret_in_every_environment() -> None:
    with pytest.raises(ValidationError, match="TELEGRAM_WEBHOOK_SECRET"):
        Settings(
            telegram_mode="webhook",
            telegram_bot_token="123:test",
            telegram_webhook_host="https://example.com",
            telegram_webhook_secret=None,
            _env_file=None,
        )


def test_jwt_helpers_raise_clear_error_without_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(security.settings, "jwt_secret", None)

    with pytest.raises(RuntimeError, match="JWT_SECRET"):
        security.create_access_token({"sub": "1"})

    with pytest.raises(RuntimeError, match="JWT_SECRET"):
        security.decode_access_token("token")


def test_telegram_init_data_requires_current_auth_date(monkeypatch: pytest.MonkeyPatch) -> None:
    """Подписанные данные без времени и из будущего не принимаются."""
    bot_token = "123:test-token"
    monkeypatch.setattr(security.settings, "telegram_bot_token", bot_token)

    def sign(values: dict[str, str]) -> str:
        data_check_string = "\n".join(f"{key}={value}" for key, value in sorted(values.items()))
        secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
        signature = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
        return urlencode({**values, "hash": signature})

    assert security.validate_telegram_init_data(sign({"user": '{"id":1}'})) is None
    assert (
        security.validate_telegram_init_data(
            sign({"auth_date": str(int(time.time()) + 1), "user": '{"id":1}'})
        )
        is None
    )
