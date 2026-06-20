"""Middleware логирования запросов бота."""

from __future__ import annotations

import logging
import time
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

logger = logging.getLogger(__name__)


class LoggingMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user = data.get("event_from_user")
        event_name = type(event).__name__
        if isinstance(event, Message):
            event_name = f"Message text={event.text!r}"
        elif isinstance(event, CallbackQuery):
            event_name = f"CallbackQuery data={event.data!r}"

        user_id = getattr(user, "id", None)
        username = getattr(user, "username", None)

        if user:
            logger.info(
                "Telegram update received: event=%s, user_id=%s, username=%s",
                event_name,
                user_id,
                username,
            )
        else:
            logger.info("Telegram update received: event=%s, user_id=unknown", event_name)

        started_at = time.perf_counter()
        try:
            return await handler(event, data)
        finally:
            duration_ms = (time.perf_counter() - started_at) * 1000
            logger.info(
                "Telegram update handled: event=%s, user_id=%s, duration_ms=%.2f",
                event_name,
                user_id or "unknown",
                duration_ms,
            )
