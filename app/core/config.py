"""Конфигурация приложения."""

from __future__ import annotations

from typing import Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Глобальные настройки из переменных окружения."""

    # Общие
    app_host: str = "localhost"
    app_port: int = 8000
    app_env: str = "dev"
    app_url: str | None = None
    app_name: str = "AntEx"

    # CORS
    backend_cors_origins: list[str] | str = []
    cors_allow_credentials: bool = True
    cors_allow_methods: list[str] | str = "*"
    cors_allow_headers: list[str] | str = "*"

    # Логирование
    log_dir: str = "/app/logs"
    log_level: str = "INFO"
    log_file_max_bytes: int = 10 * 1024 * 1024
    log_file_backup_count: int = 5
    max_json_request_bytes: int = 1024 * 1024

    # БД
    database_url: str = ""

    # Redis
    redis_url: str = "redis://localhost:6379/0"
    proxy: str | None = None
    manager_realtime_keepalive_seconds: int = 15

    # Telegram
    telegram_bot_token: str | None = None
    telegram_bot_username: str | None = None
    telegram_mode: Literal["polling", "webhook"] = "polling"
    telegram_webhook_host: str | None = None
    telegram_webhook_secret: str | None = None
    telegram_init_data_ttl_seconds: int = 86400
    admin_id: int | None = None
    dev_user_id: int | None = None

    @property
    def telegram_webhook_url(self) -> str | None:
        if self.telegram_webhook_host:
            return f"{self.telegram_webhook_host}/telegram/webhook"
        return None

    @model_validator(mode="after")
    def validate_runtime_config(self) -> Settings:
        if not 5 <= self.manager_realtime_keepalive_seconds < 45:
            raise ValueError("MANAGER_REALTIME_KEEPALIVE_SECONDS must be between 5 and 44")
        if self.app_env == "production" and not self._has_value(self.jwt_secret):
            raise ValueError("JWT_SECRET is required when APP_ENV=production")

        if self.telegram_mode == "webhook":
            if not self._has_value(self.telegram_bot_token):
                raise ValueError("TELEGRAM_BOT_TOKEN is required when TELEGRAM_MODE=webhook")
            if not self._has_value(self.telegram_webhook_host):
                raise ValueError("TELEGRAM_WEBHOOK_HOST is required when TELEGRAM_MODE=webhook")

        if self.telegram_mode == "webhook" and not self._has_value(self.telegram_webhook_secret):
            raise ValueError("TELEGRAM_WEBHOOK_SECRET is required when TELEGRAM_MODE=webhook")

        return self

    @staticmethod
    def _has_value(value: str | None) -> bool:
        return value is not None and value.strip() != ""

    # Mini App
    frontend_webapp_url: str | None = None

    # JWT
    jwt_secret: str | None = None
    jwt_algorithm: str = "HS256"
    jwt_ttl_seconds: int = 86400
    admin_access_ttl_seconds: int = 900
    admin_refresh_ttl_seconds: int = 604800
    admin_bootstrap_password: str | None = None
    admin_login_rate_limit: int = 5
    admin_login_global_rate_limit: int = 100
    admin_login_rate_window_seconds: int = 60

    # Operator
    operator_chat_id: int | None = None

    # Exchange / Rate
    rate_cache_ttl_seconds: int = 86400
    currencybeacon_api_key: str | None = None

    # Review channel
    review_channel_id: int | None = None

    # Timezone
    timezone: str = "UTC"

    # i18n
    app_locale_default: str = "ru"
    app_locale_supported: str = "ru,en"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
        extra="ignore",
    )


settings = Settings()
