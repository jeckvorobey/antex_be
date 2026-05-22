"""Telegram-уведомления по жизненному циклу заявки."""
# ruff: noqa: RUF001

from __future__ import annotations

import logging

from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.types import InlineKeyboardMarkup

from app.telegram import messages
from app.telegram.i18n import get_translator, get_user_translator
from app.telegram.keyboards import (
    manager_order_open_chat,
    review_link,
    user_order_write_manager,
)

logger = logging.getLogger(__name__)

REVIEW_URL = "https://t.me/+Rw2BRymXRnk1ZGUy"

async def send_or_replace_user_status_message(
    *,
    bot,
    chat_id: int,
    order,
    text: str,
    reply_markup: InlineKeyboardMarkup | None,
) -> int | None:
    old_message_id = getattr(order, "userNotificationMessageId", None)
    if old_message_id:
        try:
            await bot.delete_message(chat_id=chat_id, message_id=old_message_id)
        except TelegramBadRequest:
            logger.info(
                "Previous order message %s for chat %s is already gone",
                old_message_id,
                chat_id,
            )
        except TelegramForbiddenError:
            logger.warning("Cannot delete order message for inaccessible chat %s", chat_id)
            return None

    sent = await bot.send_message(chat_id=chat_id, text=text, reply_markup=reply_markup)
    order.userNotificationMessageId = sent.message_id
    return sent.message_id


async def notify_order_created(order, user, manager) -> None:
    bot = _get_telegram_bot()
    if bot is None:
        logger.warning("Notification skipped: bot is not initialized")
        return

    if getattr(user, "telegram_id", None):
        translate = get_user_translator(user)
        await send_or_replace_user_status_message(
            bot=bot,
            chat_id=user.telegram_id,
            order=order,
            text=messages.order_created(order.publicNumber, translator=translate),
            reply_markup=None,
        )

    if manager is not None and getattr(manager, "telegram_id", None):
        translate = get_translator("ru")
        chat_url = build_chat_url_for_user(user)
        if not chat_url:
            logger.warning(
                "Manager notification skipped: user chat URL is unavailable for order %s",
                order.id,
            )
            return
        await bot.send_message(
            chat_id=manager.telegram_id,
            text=_build_manager_order_text(order, user),
            reply_markup=manager_order_open_chat(
                translate,
                order_id=order.id,
                chat_url=chat_url,
            ),
        )


async def notify_order_status_changed(order, *, manager_chat_url: str | None = None) -> None:
    bot = _get_telegram_bot()
    if bot is None:
        logger.warning("Status notification skipped: bot is not initialized")
        return

    user = getattr(order, "user", None)
    if user is None or not getattr(user, "telegram_id", None):
        logger.warning(
            "Status notification skipped: user chat is unavailable for order %s",
            order.id,
        )
        return

    translate = get_user_translator(user)
    reply_markup = None
    if order.status == 2 and manager_chat_url:
        reply_markup = user_order_write_manager(translate, chat_url=manager_chat_url)
    if order.status == 3:
        reply_markup = review_link(translate, REVIEW_URL)

    await send_or_replace_user_status_message(
        bot=bot,
        chat_id=user.telegram_id,
        order=order,
        text=_build_user_status_text(order, translate=translate),
        reply_markup=reply_markup,
    )


def build_chat_url_for_user(user) -> str | None:
    username = getattr(user, "username", None)
    telegram_id = getattr(user, "telegram_id", None)
    if username:
        return f"https://t.me/{username}"
    if telegram_id:
        return f"tg://user?id={telegram_id}"
    return None


def build_manager_chat_url(order) -> str | None:
    user = getattr(order, "user", None)
    if user is None:
        return None
    return build_chat_url_for_user(user)


def _build_user_status_text(order, *, translate) -> str:
    if order.status == 1:
        return messages.order_created(order.publicNumber, translator=translate)

    status_map = {
        2: messages.order_confirmed,
        3: messages.order_completed,
        4: messages.order_cancelled,
    }
    factory = status_map.get(order.status, messages.order_created)
    return factory(order.publicNumber, translator=translate)


def _build_manager_order_text(order, user) -> str:
    city_name = order.city.name if getattr(order, "city", None) else "—"
    username = f"@{user.username}" if getattr(user, "username", None) else "—"
    contact = order.contactTelegram or user.phone or "—"
    method = order.methodGet
    return "\n".join(
        [
            f"🆕 <b>Новая заявка #{order.publicNumber}</b>",
            "",
            f"Статус: <b>{_status_label(order.status)}</b>",
            f"Город: <b>{city_name}</b>",
            f"Страна: <b>{order.country.value}</b>",
            f"Пользователь: {username}",
            f"Telegram ID: <code>{user.telegram_id or '—'}</code>",
            f"Контакт: <b>{contact}</b>",
            f"Отдаёт: <b>{order.amountSell:,} {order.currencySell}</b>",
            f"Получает: <b>{order.amountBuy or '—'} {order.currencyBuy}</b>",
            f"Курс: <b>{order.rate or '—'}</b>",
            f"Способ: <b>{method}</b>",
        ]
    )


def _status_label(status: int) -> str:
    return {
        1: "Новая",
        2: "В работе",
        3: "Завершена",
        4: "Отменена",
    }.get(status, f"Статус {status}")


def _get_telegram_bot():
    from app.telegram import bot as telegram_bot

    return telegram_bot.bot
