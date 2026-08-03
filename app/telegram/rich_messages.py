"""Отправка структурированных Rich Messages через Telegram Bot API."""

from __future__ import annotations

from typing import Any

from aiogram.methods.base import TelegramMethod
from aiogram.types import Message


class SendRichMessage(TelegramMethod[Message]):
    """Метод Bot API, пока не представленный отдельной моделью aiogram."""

    __returning__ = Message
    __api_method__ = "sendRichMessage"

    chat_id: int | str
    rich_message: dict[str, Any]
    reply_markup: Any | None = None


async def answer_rich(
    message: Message,
    html: str,
    *,
    reply_markup: Any | None = None,
) -> Message:
    """Отправляет Rich Message с сохранением заданной клавиатуры."""
    return await message.bot(
        SendRichMessage(
            chat_id=message.chat.id,
            rich_message={"html": html},
            reply_markup=reply_markup,
        )
    )


class EditRichMessageText(TelegramMethod[Message | bool]):
    """Редактирует существующее сообщение, сохраняя Rich-разметку."""

    __returning__ = Message
    __api_method__ = "editMessageText"

    chat_id: int | str
    message_id: int
    rich_message: dict[str, Any]
    reply_markup: Any | None = None


async def edit_rich(
    message: Message,
    html: str,
    *,
    reply_markup: Any | None = None,
) -> Message | bool:
    """Редактирует Rich Message и его inline-клавиатуру без нового сообщения."""
    return await message.bot(
        EditRichMessageText(
            chat_id=message.chat.id,
            message_id=message.message_id,
            rich_message={"html": html},
            reply_markup=reply_markup,
        )
    )
