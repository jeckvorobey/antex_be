"""Адаптер отправки сообщений через aiogram."""

from __future__ import annotations

from aiogram.enums import ParseMode
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


class AiogramBroadcastSender:
    async def send_message(
        self,
        *,
        chat_id: int,
        text: str,
        button_text: str | None,
        button_url: str | None,
        allow_paid_broadcast: bool,
    ) -> None:
        from app.telegram import bot as telegram_bot

        bot = telegram_bot.bot
        if bot is None:
            bot, _ = await telegram_bot.init_bot()

        reply_markup = None
        if button_text and button_url:
            reply_markup = InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text=button_text, url=button_url)]]
            )

        await bot.send_message(
            chat_id=chat_id,
            text=text,
            parse_mode=ParseMode.HTML,
            reply_markup=reply_markup,
            allow_paid_broadcast=allow_paid_broadcast,
        )
