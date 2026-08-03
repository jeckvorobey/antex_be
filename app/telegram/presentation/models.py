# ruff: noqa: RUF002
"""Типы presentation-layer Telegram без зависимости от handlers."""

from __future__ import annotations

from dataclasses import dataclass

RICH_MESSAGE_MAX_LENGTH = 32_768
REGULAR_HTML_MAX_LENGTH = 4_096


@dataclass(frozen=True, slots=True)
class TelegramMessageSpec:
    """Семантически эквивалентные Rich и regular HTML варианты сообщения."""

    family: str
    rich_html: str
    fallback_html: str
    category: str = "system"

    def __post_init__(self) -> None:
        """Не допускает пустые или заведомо неотправляемые представления."""
        if not self.rich_html.strip() or not self.fallback_html.strip():
            msg = "TelegramMessageSpec требует Rich и fallback представления"
            raise ValueError(msg)
        if len(self.rich_html) > RICH_MESSAGE_MAX_LENGTH:
            msg = "Rich Message превышает ограничение Telegram"
            raise ValueError(msg)
        if len(self.fallback_html) > REGULAR_HTML_MAX_LENGTH:
            msg = "Regular HTML fallback превышает ограничение Telegram"
            raise ValueError(msg)
