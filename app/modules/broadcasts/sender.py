"""Адаптер отправки сообщений через aiogram."""

from __future__ import annotations

from aiogram.enums import ParseMode
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo


class AiogramBroadcastSender:
    """Отправляет одно сообщение рассылки через общий Telegram bot lifecycle."""

    async def send_message(
        self,
        *,
        chat_id: int,
        text: str,
        button_text: str | None,
        button_url: str | None,
        button_type: str,
        allow_paid_broadcast: bool,
    ) -> None:
        """Отправляет сообщение и добавляет кнопку выбранного типа."""
        from app.telegram import bot as telegram_bot

        reply_markup = None
        if button_text and button_url:
            button = (
                InlineKeyboardButton(text=button_text, web_app=WebAppInfo(url=button_url))
                if button_type == "web_app"
                else InlineKeyboardButton(text=button_text, url=button_url)
            )
            reply_markup = InlineKeyboardMarkup(inline_keyboard=[[button]])

        async with telegram_bot.sender_bot() as bot:
            await bot.send_message(
                chat_id=chat_id,
                text=text,
                parse_mode=ParseMode.HTML,
                reply_markup=reply_markup,
                allow_paid_broadcast=allow_paid_broadcast,
            )
