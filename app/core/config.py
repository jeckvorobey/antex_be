"""Конфигурация приложения."""

from __future__ import annotations

from typing import Literal

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
    log_dir: str = "./logs"
    log_level: str = "INFO"

    # БД
    database_url: str = ""

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # Telegram
    telegram_bot_token: str | None = None
    telegram_bot_username: str | None = None
    telegram_mode: Literal["polling", "webhook"] = "polling"
    telegram_webhook_host: str | None = None
    telegram_webhook_path: str = "/telegram/webhook"
    telegram_webhook_secret: str | None = None
    telegram_init_data_ttl_seconds: int = 86400
    admin_id: int | None = None

    @property
    def telegram_webhook_url(self) -> str | None:
        if self.telegram_webhook_host:
            return f"{self.telegram_webhook_host}{self.telegram_webhook_path}"
        return None

    # Mini App
    frontend_webapp_url: str | None = None

    # JWT
    jwt_secret: str | None = None
    jwt_algorithm: str = "HS256"
    jwt_ttl_seconds: int = 86400
    admin_access_ttl_seconds: int = 900
    admin_refresh_ttl_seconds: int = 604800

    # Operator
    operator_chat_id: int | None = None

    # Exchange / Rate
    reducing_factor: float = 0.6
    default_allowance: float = 0.02
    rate_cache_ttl_seconds: int = 1800

    # CoinGecko
    coingecko_api_key: str | None = None

    # Review channel
    review_channel_id: int | None = None

    # Timezone
    timezone: str = "Asia/Bangkok"

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
