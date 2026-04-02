"""Низкоуровневая доставка Telegram-уведомлений."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError

from app.telegram import bot as telegram_bot

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class NotificationMessage:
    chat_id: int | None
    text: str


async def _send_message(message: NotificationMessage) -> None:
    if not message.chat_id:
        logger.warning("Notification skipped: no chat_id")
        return
    if telegram_bot.bot is None:
        logger.warning("Notification skipped: bot is not initialized")
        return

    try:
        await telegram_bot.bot.send_message(chat_id=message.chat_id, text=message.text)
    except TelegramForbiddenError:
        logger.warning("Chat %s is not accessible", message.chat_id)
    except TelegramBadRequest:
        logger.exception("Telegram rejected notification for chat %s", message.chat_id)


async def send_order_created_to_user(message: NotificationMessage) -> None:
    await _send_message(message)


async def send_order_created_to_manager(message: NotificationMessage) -> None:
    await _send_message(message)
