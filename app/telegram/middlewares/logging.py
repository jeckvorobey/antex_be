"""Middleware логирования запросов бота."""

from __future__ import annotations

import logging
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

        if user:
            logger.info(
                "Telegram update received: event=%s, user_id=%s, username=%s",
                event_name,
                user.id,
                user.username,
            )
        else:
            logger.info("Telegram update received: event=%s, user_id=unknown", event_name)
        return await handler(event, data)
