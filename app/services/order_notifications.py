"""Telegram-уведомления по жизненному циклу заявки."""
# ruff: noqa: RUF001

from __future__ import annotations

import logging

from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.types import InlineKeyboardMarkup

from app.enums.country import Country
from app.enums.order import MethodGet, OrderStatus
from app.telegram import messages
from app.telegram.i18n import get_translator, get_user_translator
from app.telegram.keyboards import (
    manager_order_open_chat,
    order_created_actions,
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
            await bot.edit_message_text(
                text=text,
                chat_id=chat_id,
                message_id=old_message_id,
                reply_markup=reply_markup,
            )
            order.userNotificationMessageId = old_message_id
            return old_message_id
        except TelegramBadRequest:
            logger.info(
                "Failed to edit order message %s for chat %s, sending a new message",
                old_message_id,
                chat_id,
            )
        except TelegramForbiddenError:
            logger.warning("Cannot update order message for inaccessible chat %s", chat_id)
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
            reply_markup=order_created_actions(translate),
        )

    if manager is not None and getattr(manager, "telegram_id", None):
        translate = get_translator("ru")
        await bot.send_message(
            chat_id=manager.telegram_id,
            text=_build_manager_order_text(order, user),
            reply_markup=manager_order_open_chat(
                translate,
                order_id=order.id,
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
        reply_markup = user_order_write_manager(
            translate,
            chat_url=manager_chat_url,
            message_text=messages.user_chat_open_text(
                order_id=order.publicNumber,
                translator=None,
                locale="ru",
            ),
        )
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
    }
    factory = status_map.get(order.status)
    if factory is not None:
        return factory(order.publicNumber, translator=translate)
    if order.status == 3:
        city_name = _format_city_name(order)
        summary = messages.exchange_summary_middle(
            country=_format_country_name(getattr(order, "country", None)),
            rate=_format_rate(getattr(order, "rate", None)),
            amount=getattr(order, "amountSell", 0) or 0,
            from_currency=getattr(order, "currencySell", "—"),
            result=getattr(order, "amountBuy", 0) or 0,
            to_currency=getattr(order, "currencyBuy", "—"),
            method=_format_method(getattr(order, "methodGet", None)),
            city=city_name if city_name != "—" else None,
            translator=translate,
        )
        return "\n".join(
            [
                messages.order_completed(order.publicNumber, translator=translate),
                "",
                summary,
                "",
                messages.order_completed_bottom(translator=translate),
            ]
        )
    if order.status == 4:
        return messages.order_cancelled(order.publicNumber, translator=translate)
    return messages.order_created(order.publicNumber, translator=translate)


def build_manager_status_text(order) -> str:
    username = _format_username(getattr(order, "user", None))
    city_name = _format_city_name(order)

    if int(order.status) == int(OrderStatus.PROCESSING):
        middle = messages.manager_order_summary(
            country=_format_country_name(getattr(order, "country", None)),
            rate=_format_rate(getattr(order, "rate", None)),
            amount_sell=getattr(order, "amountSell", 0) or 0,
            from_currency=getattr(order, "currencySell", "—"),
            amount_buy=getattr(order, "amountBuy", 0) or 0,
            to_currency=getattr(order, "currencyBuy", "—"),
            method=_format_method(getattr(order, "methodGet", None)),
            username=username,
            city=city_name if city_name != "—" else None,
            translator=None,
            locale="ru",
        )
        return "\n".join(
            [
                f"🟢 Заявка #{order.publicNumber}",
                "",
                "⏳ Статус: В работе",
                "",
                middle,
                "",
                "💬 Ожидает завершения обмена",
            ]
        )

    if int(order.status) == int(OrderStatus.COMPLETED):
        middle = messages.exchange_summary_middle(
            country=_format_country_name(getattr(order, "country", None)),
            rate=_format_rate(getattr(order, "rate", None)),
            amount=getattr(order, "amountSell", 0) or 0,
            from_currency=getattr(order, "currencySell", "—"),
            result=getattr(order, "amountBuy", 0) or 0,
            to_currency=getattr(order, "currencyBuy", "—"),
            method=_format_method(getattr(order, "methodGet", None)),
            city=city_name if city_name != "—" else None,
            translator=None,
            locale="ru",
        )
        return "\n".join(
            [
                f"✅ Заявка #{order.publicNumber} завершена",
                "",
                middle,
                "",
                "🏁 Обмен успешно выполнен",
            ]
        )

    if int(order.status) == int(OrderStatus.CANCELLED):
        return "\n".join(
            [
                f"Заявка #{order.publicNumber}",
                "Статус: Отменена",
                f"Город: {city_name}",
                "Пара: "
                f"{getattr(order, 'currencySell', '—')} -> {getattr(order, 'currencyBuy', '—')}",
                f"Сумма: {getattr(order, 'amountSell', '—')} {getattr(order, 'currencySell', '—')}",
            ]
        )

    return _build_manager_order_text(order, getattr(order, "user", None))


def _build_manager_order_text(order, user) -> str:
    city_name = _format_city_name(order)
    country_name = _format_country_name(getattr(order, "country", None))
    username = _format_username(user)
    method = _format_method(getattr(order, "methodGet", None))
    middle = messages.manager_order_summary(
        country=country_name,
        rate=_format_rate(getattr(order, "rate", None)),
        amount_sell=getattr(order, "amountSell", 0) or 0,
        from_currency=getattr(order, "currencySell", "—"),
        amount_buy=getattr(order, "amountBuy", 0) or 0,
        to_currency=getattr(order, "currencyBuy", "—"),
        method=method,
        username=username,
        city=city_name if city_name != "—" else None,
        translator=None,
        locale="ru",
    )
    return "\n".join(
        [
            f"🆕 Новая заявка #{order.publicNumber}",
            "",
            middle,
            "",
            "⏳ Ожидает обработки менеджером",
        ]
    )


def _format_direction(order) -> str:
    return f"{getattr(order, 'currencySell', '—')} → {getattr(order, 'currencyBuy', '—')}"


def _format_city_name(order) -> str:
    city = getattr(order, "city", None)
    return getattr(city, "name", "—")


def _format_country_name(country) -> str:
    if isinstance(country, Country):
        return country.ru_name
    if hasattr(country, "ru_name"):
        return country.ru_name
    value = getattr(country, "value", None)
    if value == Country.THAILAND.value:
        return Country.THAILAND.ru_name
    if value == Country.VIETNAM.value:
        return Country.VIETNAM.ru_name
    if value == Country.GEORGIA.value:
        return Country.GEORGIA.ru_name
    return value or "—"


def _format_username(user) -> str:
    username = getattr(user, "username", None)
    return f"@{username}" if username else "—"


def _format_amount(amount: int | float | None, currency: str | None) -> str:
    if amount is None:
        return f"— {currency or ''}".strip()
    if isinstance(amount, float) and amount.is_integer():
        amount = int(amount)
    amount_text = f"{amount:,}".replace(",", " ")
    return f"{amount_text} {currency or '—'}"


def _format_rate(rate: float | None) -> str:
    if rate is None:
        return "—"
    return str(rate)


def _format_method(method: str | None) -> str:
    if method == MethodGet.CASH.value:
        return "Доставка наличных"
    if method == MethodGet.QRCODE.value:
        return "Наличные по QR"
    if method == MethodGet.BANK_ACCOUNT.value:
        return "Перевод на счёт в местном банке"
    if method == MethodGet.PAY_SERVICES.value:
        return "Оплата сервисов"
    return method or "—"


def _get_telegram_bot():
    from app.telegram import bot as telegram_bot

    return telegram_bot.bot
