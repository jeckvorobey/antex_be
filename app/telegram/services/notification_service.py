"""Сервис уведомлений (оператору и пользователю)."""

from __future__ import annotations

import logging

from aiogram.exceptions import TelegramForbiddenError

from app.core.config import settings
from app.telegram import messages
from app.telegram.keyboards import confirm_order

logger = logging.getLogger(__name__)


async def notify_operator(bot, order_id: int, user_id: int, amount_sell: int,
                          currency_sell: str, amount_buy: int, currency_buy: str, method: str) -> None:
    if not settings.operator_chat_id:
        return
    text = messages.new_order_operator(order_id, user_id, amount_sell, currency_sell, amount_buy, currency_buy, method)
    try:
        await bot.send_message(
            chat_id=settings.operator_chat_id,
            text=text,
            reply_markup=confirm_order(order_id),
        )
    except TelegramForbiddenError:
        logger.warning("Operator chat %s is not accessible", settings.operator_chat_id)


async def notify_user(bot, user_id: int, text: str) -> None:
    try:
        await bot.send_message(chat_id=user_id, text=text)
    except TelegramForbiddenError:
        logger.warning("User %s blocked the bot", user_id)
