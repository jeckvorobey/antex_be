"""Middleware логирования запросов бота."""

from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Update

logger = logging.getLogger(__name__)


class LoggingMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        update: Update | None = data.get("update") or data.get("event_update")
        user = data.get("event_from_user")
        if user:
            logger.debug("Update from user %s (%s)", user.id, user.username)
        return await handler(event, data)
