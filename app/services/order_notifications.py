"""Telegram-уведомления по жизненному циклу заявки."""

from __future__ import annotations

import logging
import re
from dataclasses import replace
from enum import StrEnum

from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramNotFound
from aiogram.types import InlineKeyboardMarkup, InputRichMessage

from app.enums.country import Country
from app.enums.order import MethodGet, OrderStatus
from app.telegram import messages
from app.telegram.i18n import get_translator, get_user_translator, normalize_locale
from app.telegram.keyboards import (
    manager_order_open_chat,
    order_created_actions,
    review_link,
    user_order_write_manager,
)
from app.telegram.order_cards import OrderMessageView

logger = logging.getLogger(__name__)

REVIEW_URL = "https://t.me/+Rw2BRymXRnk1ZGUy"
_TELEGRAM_USERNAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]{4,31}$")


class DeliveryOutcome(StrEnum):
    """Результат доставки, который нужен manager callback-ам."""

    RICH = "rich"
    FALLBACK = "fallback"
    FAILED = "failed"


async def _send_rich_or_html(
    *,
    bot,
    chat_id: int,
    rich_html: str,
    fallback_html: str,
    reply_markup: InlineKeyboardMarkup,
    existing_message_id: int | None = None,
) -> tuple[DeliveryOutcome, int | None]:
    """Отправить Rich Message и один раз перейти на обычный HTML при отказе Bot API."""
    if existing_message_id is not None:
        try:
            await bot.edit_message_text(
                chat_id=chat_id,
                message_id=existing_message_id,
                rich_message=InputRichMessage(html=rich_html),
                reply_markup=reply_markup,
            )
            return DeliveryOutcome.RICH, existing_message_id
        except (TelegramBadRequest, TelegramNotFound):
            logger.info(
                "Rich order edit was rejected; using regular HTML fallback chat_id=%s",
                chat_id,
            )
        except TelegramForbiddenError:
            logger.warning("Order message edit skipped: chat is inaccessible chat_id=%s", chat_id)
            return DeliveryOutcome.FAILED, None
        except Exception:
            logger.exception("Rich order message edit failed chat_id=%s", chat_id)
            return DeliveryOutcome.FAILED, None

        try:
            await bot.edit_message_text(
                chat_id=chat_id,
                message_id=existing_message_id,
                text=fallback_html,
                reply_markup=reply_markup,
            )
            return DeliveryOutcome.FALLBACK, existing_message_id
        except (TelegramBadRequest, TelegramNotFound):
            logger.info(
                "Order status message is no longer editable; sending one replacement chat_id=%s",
                chat_id,
            )
        except TelegramForbiddenError:
            logger.warning("Order HTML edit skipped: chat is inaccessible chat_id=%s", chat_id)
            return DeliveryOutcome.FAILED, None
        except Exception:
            logger.exception("Order HTML fallback edit failed chat_id=%s", chat_id)
            return DeliveryOutcome.FAILED, None

        try:
            sent = await bot.send_message(
                chat_id=chat_id,
                text=fallback_html,
                reply_markup=reply_markup,
            )
            return DeliveryOutcome.FALLBACK, sent.message_id
        except TelegramForbiddenError:
            logger.warning("Order replacement skipped: chat is inaccessible chat_id=%s", chat_id)
        except Exception:
            logger.exception("Order replacement failed chat_id=%s", chat_id)
        return DeliveryOutcome.FAILED, None

    try:
        sent = await bot.send_rich_message(
            chat_id=chat_id,
            rich_message=InputRichMessage(html=rich_html),
            reply_markup=reply_markup,
        )
        return DeliveryOutcome.RICH, sent.message_id
    except (TelegramBadRequest, TelegramNotFound):
        logger.info(
            "Rich order message was rejected; using regular HTML fallback chat_id=%s",
            chat_id,
        )
    except TelegramForbiddenError:
        logger.warning("Order message skipped: chat is inaccessible chat_id=%s", chat_id)
        return DeliveryOutcome.FAILED, None
    except Exception:
        logger.exception("Rich order message failed chat_id=%s", chat_id)
        return DeliveryOutcome.FAILED, None

    try:
        sent = await bot.send_message(
            chat_id=chat_id,
            text=fallback_html,
            reply_markup=reply_markup,
        )
        return DeliveryOutcome.FALLBACK, sent.message_id
    except TelegramForbiddenError:
        logger.warning("Order HTML fallback skipped: chat is inaccessible chat_id=%s", chat_id)
    except Exception:
        logger.exception("Order HTML fallback failed chat_id=%s", chat_id)
    return DeliveryOutcome.FAILED, None


def build_manager_contact_url(manager) -> str | None:
    """Вернуть ссылку, способную передать клиенту предварительно заполненный draft."""
    username = getattr(manager, "username", None)
    if not isinstance(username, str) or not _TELEGRAM_USERNAME_RE.fullmatch(username):
        return None
    return f"https://t.me/{username}"


async def send_customer_handoff(order, manager) -> DeliveryOutcome:
    """Отправить клиенту первичную инструкцию для единственного менеджера."""
    bot = _get_telegram_bot()
    user = getattr(order, "user", None)
    manager_url = build_manager_contact_url(manager)
    if bot is None or user is None or not getattr(user, "telegram_id", None) or not manager_url:
        logger.warning(
            "Customer handoff skipped order_id=%s public_number=%s reason=%s",
            getattr(order, "id", None),
            getattr(order, "publicNumber", None),
            "manager_username_missing" if manager_url is None else "chat_or_bot_unavailable",
        )
        return DeliveryOutcome.FAILED

    translate = get_user_translator(user)
    locale = normalize_locale(getattr(user, "language_code", None))
    view = OrderMessageView.from_order(order)
    draft = messages.customer_manager_draft(order.publicNumber, translator=translate)
    markup = user_order_write_manager(translate, chat_url=manager_url, message_text=draft)
    delivery, message_id = await _send_rich_or_html(
        bot=bot,
        chat_id=user.telegram_id,
        rich_html=messages.order_handoff_rich(view, translator=translate, locale=locale),
        fallback_html=messages.order_handoff_html(view, translator=translate, locale=locale),
        reply_markup=markup,
        existing_message_id=getattr(order, "userNotificationMessageId", None),
    )
    if message_id is not None:
        order.userNotificationMessageId = message_id
    return delivery


async def send_customer_reminder(order, manager) -> DeliveryOutcome:
    """Отправить новое напоминание по активной заявке через существующего бота."""
    bot = _get_telegram_bot()
    user = getattr(order, "user", None)
    manager_url = build_manager_contact_url(manager)
    if bot is None or user is None or not getattr(user, "telegram_id", None) or not manager_url:
        logger.warning(
            "Customer reminder skipped order_id=%s public_number=%s reason=%s",
            getattr(order, "id", None),
            getattr(order, "publicNumber", None),
            "manager_username_missing" if manager_url is None else "chat_or_bot_unavailable",
        )
        return DeliveryOutcome.FAILED

    translate = get_user_translator(user)
    locale = normalize_locale(getattr(user, "language_code", None))
    view = OrderMessageView.from_order(order)
    markup = user_order_write_manager(
        translate,
        chat_url=manager_url,
        message_text=messages.customer_manager_draft(order.publicNumber, translator=translate),
    )
    delivery, _ = await _send_rich_or_html(
        bot=bot,
        chat_id=user.telegram_id,
        rich_html=messages.order_reminder_rich(view, translator=translate, locale=locale),
        fallback_html=messages.order_reminder_html(view, translator=translate, locale=locale),
        reply_markup=markup,
    )
    return delivery


async def edit_manager_order_card(
    *,
    message,
    order,
    reply_markup: InlineKeyboardMarkup | None,
    customer_notified: bool = True,
) -> DeliveryOutcome:
    """Отредактировать карточку менеджера через Rich Message и резервный HTML."""
    view = OrderMessageView.from_order(order)
    status = OrderStatus(int(order.status))
    try:
        await message.edit_text(
            rich_message=InputRichMessage(
                html=messages.manager_order_card_rich(
                    view,
                    status=status,
                    customer_notified=customer_notified,
                    locale="ru",
                )
            ),
            reply_markup=reply_markup,
        )
        return DeliveryOutcome.RICH
    except (TelegramBadRequest, TelegramNotFound):
        logger.info(
            "Rich manager card edit was rejected; using regular HTML fallback order_id=%s",
            getattr(order, "id", None),
        )
    except Exception:
        logger.exception("Rich manager card edit failed order_id=%s", getattr(order, "id", None))
        return DeliveryOutcome.FAILED

    try:
        await message.edit_text(
            text=messages.manager_order_card_html(
                view,
                status=status,
                customer_notified=customer_notified,
                locale="ru",
            ),
            reply_markup=reply_markup,
        )
        return DeliveryOutcome.FALLBACK
    except Exception:
        logger.exception("Manager HTML card edit failed order_id=%s", getattr(order, "id", None))
        return DeliveryOutcome.FAILED


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


async def notify_order_created(
    order,
    user,
    manager,
    *,
    notify_user: bool = True,
) -> DeliveryOutcome:
    bot = _get_telegram_bot()
    if bot is None:
        logger.warning(
            "Order notification skipped: bot is not initialized order_id=%s public_number=%s",
            getattr(order, "id", None),
            getattr(order, "publicNumber", None),
        )
        return DeliveryOutcome.FAILED

    if notify_user and getattr(user, "telegram_id", None):
        logger.info(
            "Sending order notification to user: order_id=%s public_number=%s "
            "user_id=%s telegram_id=%s",
            getattr(order, "id", None),
            getattr(order, "publicNumber", None),
            getattr(user, "id", None),
            getattr(user, "telegram_id", None),
        )
        translate = get_user_translator(user)
        availability = getattr(order, "manager_availability", None)
        await send_or_replace_user_status_message(
            bot=bot,
            chat_id=user.telegram_id,
            order=order,
            text=messages.order_created(
                order.publicNumber,
                translator=translate,
                managers_offline=getattr(availability, "status", None) == "offline",
            ),
            reply_markup=order_created_actions(translate),
        )
        logger.info(
            "Order notification sent to user: order_id=%s public_number=%s telegram_id=%s",
            getattr(order, "id", None),
            getattr(order, "publicNumber", None),
            getattr(user, "telegram_id", None),
        )
    elif notify_user:
        logger.warning(
            "Order user notification skipped: user chat is unavailable order_id=%s "
            "public_number=%s user_id=%s",
            getattr(order, "id", None),
            getattr(order, "publicNumber", None),
            getattr(user, "id", None),
        )

    if manager is not None and getattr(manager, "telegram_id", None):
        translate = get_translator("ru")
        logger.info(
            "Sending order notification to manager: order_id=%s public_number=%s "
            "manager_user_id=%s manager_telegram_id=%s",
            getattr(order, "id", None),
            getattr(order, "publicNumber", None),
            getattr(manager, "id", None),
            getattr(manager, "telegram_id", None),
        )
        view = OrderMessageView.from_order(order)
        if view.customer_username is None:
            view = replace(view, customer_username=getattr(user, "username", None))
        delivery, _ = await _send_rich_or_html(
            bot=bot,
            chat_id=manager.telegram_id,
            rich_html=messages.manager_order_card_rich(
                view,
                status=OrderStatus.CREATED,
                locale="ru",
            ),
            fallback_html=messages.manager_order_card_html(
                view,
                status=OrderStatus.CREATED,
                locale="ru",
            ),
            reply_markup=manager_order_open_chat(translate, order_id=order.id),
        )
        if delivery == DeliveryOutcome.FAILED:
            logger.warning(
                "Order notification delivery to manager failed: order_id=%s "
                "public_number=%s manager_user_id=%s manager_telegram_id=%s",
                getattr(order, "id", None),
                getattr(order, "publicNumber", None),
                getattr(manager, "id", None),
                getattr(manager, "telegram_id", None),
            )
            return delivery
        logger.info(
            "Order notification sent to manager: order_id=%s public_number=%s "
            "manager_user_id=%s manager_telegram_id=%s",
            getattr(order, "id", None),
            getattr(order, "publicNumber", None),
            getattr(manager, "id", None),
            getattr(manager, "telegram_id", None),
        )
        return delivery
    else:
        logger.warning(
            "Order manager notification skipped: manager chat is unavailable order_id=%s "
            "public_number=%s manager_user_id=%s",
            getattr(order, "id", None),
            getattr(order, "publicNumber", None),
            getattr(manager, "id", None),
        )
        return DeliveryOutcome.FAILED


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
            message_text=messages.customer_manager_draft(order.publicNumber, translator=translate),
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
    if isinstance(username, str) and _TELEGRAM_USERNAME_RE.fullmatch(username):
        return f"https://t.me/{username}"
    if isinstance(telegram_id, int) and not isinstance(telegram_id, bool) and telegram_id > 0:
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
    """Вернуть regular HTML представление manager-карточки для совместимости."""
    return messages.manager_order_card_html(
        OrderMessageView.from_order(order),
        status=OrderStatus(int(order.status)),
        locale="ru",
    )


def _build_manager_order_text(order, user) -> str:
    """Вернуть fallback новой заявки для старых внутренних вызовов."""
    view = OrderMessageView.from_order(order)
    if view.customer_username is None:
        view = replace(view, customer_username=getattr(user, "username", None))
    return messages.manager_order_card_html(
        view,
        status=OrderStatus.CREATED,
        locale="ru",
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
