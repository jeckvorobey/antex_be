# ruff: noqa: RUF002
"""Единая доставка Rich Messages с функционально равным HTML fallback."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from aiogram.exceptions import TelegramBadRequest, TelegramNotFound
from aiogram.types import InputRichMessage

from app.telegram.presentation.models import TelegramMessageSpec


class DeliveryKind(StrEnum):
    """Поддерживаемые способы доставки presentation message."""

    SEND = "send"
    EDIT = "edit"


@dataclass(frozen=True, slots=True)
class DeliveryOutcome:
    """Результат доставки без раскрытия текста или секретов в логах."""

    delivered: bool
    used_fallback: bool
    message: Any | None = None
    error: Exception | None = None


def _rich_is_unsupported(error: Exception) -> bool:
    """Определяет подтверждённую несовместимость Rich transport, а не любую ошибку."""
    if isinstance(error, AttributeError):
        return True
    if not isinstance(error, (TelegramBadRequest, TelegramNotFound)):
        return False
    message = str(error).lower()
    return any(marker in message for marker in ("method is not available", "rich", "not found"))


async def deliver(
    bot: Any,
    *,
    chat_id: int,
    spec: TelegramMessageSpec,
    kind: DeliveryKind,
    reply_markup: Any | None = None,
    message_id: int | None = None,
) -> DeliveryOutcome:
    """Доставляет Rich вариант и делает одну fallback-попытку только при несовместимости."""
    rich_message = InputRichMessage(html=spec.rich_html)
    try:
        if kind is DeliveryKind.SEND:
            message = await bot.send_rich_message(
                chat_id=chat_id,
                rich_message=rich_message,
                reply_markup=reply_markup,
            )
        else:
            if message_id is None:
                raise ValueError("Для редактирования нужен message_id")
            message = await bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                rich_message=rich_message,
                reply_markup=reply_markup,
            )
        return DeliveryOutcome(delivered=True, used_fallback=False, message=message)
    except Exception as error:
        if not _rich_is_unsupported(error):
            return DeliveryOutcome(delivered=False, used_fallback=False, error=error)

    try:
        if kind is DeliveryKind.SEND:
            message = await bot.send_message(
                chat_id=chat_id,
                text=spec.fallback_html,
                reply_markup=reply_markup,
            )
        else:
            if message_id is None:
                raise ValueError("Для редактирования нужен message_id")
            message = await bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=spec.fallback_html,
                reply_markup=reply_markup,
            )
        return DeliveryOutcome(delivered=True, used_fallback=True, message=message)
    except Exception as error:
        return DeliveryOutcome(delivered=False, used_fallback=True, error=error)


async def send_to_actor(
    actor: Any,
    *,
    spec: TelegramMessageSpec,
    reply_markup: Any | None = None,
) -> Any:
    """Отправляет presentation message через bot или совместимый actor fake в тестах."""
    bot = getattr(actor, "bot", None)
    chat = getattr(actor, "chat", None)
    chat_id = getattr(chat, "id", None)
    if bot is None or chat_id is None or not callable(getattr(bot, "send_rich_message", None)):
        return await actor.answer(spec.fallback_html, reply_markup=reply_markup)

    outcome = await deliver(
        bot,
        chat_id=chat_id,
        spec=spec,
        kind=DeliveryKind.SEND,
        reply_markup=reply_markup,
    )
    if outcome.delivered:
        return outcome.message
    assert outcome.error is not None
    raise outcome.error


async def edit_actor_message(
    message: Any,
    *,
    spec: TelegramMessageSpec,
    reply_markup: Any | None = None,
) -> Any:
    """Редактирует карточку через Rich transport или regular HTML fallback."""
    bot = getattr(message, "bot", None)
    chat = getattr(message, "chat", None)
    chat_id = getattr(chat, "id", None)
    message_id = getattr(message, "message_id", None)
    if (
        bot is None
        or chat_id is None
        or message_id is None
        or not callable(getattr(bot, "edit_message_text", None))
    ):
        return await message.edit_text(spec.fallback_html, reply_markup=reply_markup)

    outcome = await deliver(
        bot,
        chat_id=chat_id,
        spec=spec,
        kind=DeliveryKind.EDIT,
        reply_markup=reply_markup,
        message_id=message_id,
    )
    if outcome.delivered:
        return outcome.message
    error = outcome.error
    if isinstance(error, TelegramBadRequest) and "message is not modified" in str(error).lower():
        return None
    assert error is not None
    raise error
