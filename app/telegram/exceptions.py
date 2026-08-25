"""Исключения transport-level обработки Telegram updates."""

from __future__ import annotations


class TelegramCaptureRetryError(RuntimeError):
    """Требует не подтверждать update после временной ошибки manager chat capture."""
