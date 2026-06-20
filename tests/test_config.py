from __future__ import annotations

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


def test_production_webhook_config_requires_secret() -> None:
    with pytest.raises(ValidationError, match="TELEGRAM_WEBHOOK_SECRET"):
        Settings(
            app_env="production",
            jwt_secret="jwt-secret",
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
