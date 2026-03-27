"""Telegram bot message templates."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from app.telegram.i18n import get_translator

Translate = Callable[[str], str]


def _resolve_translator(
    translator: Translate | None = None,
    locale: str | None = None,
) -> Translate:
    return translator or get_translator(locale)


def welcome(
    first_name: str,
    *,
    translator: Translate | None = None,
    locale: str | None = None,
) -> str:
    return _resolve_translator(translator, locale)("welcome", name=first_name)


def bot_disabled(*, translator: Translate | None = None, locale: str | None = None) -> str:
    return _resolve_translator(translator, locale)("bot-disabled")


def bot_turned_on(*, translator: Translate | None = None, locale: str | None = None) -> str:
    return _resolve_translator(translator, locale)("bot-turned-on")


def bot_turned_off(*, translator: Translate | None = None, locale: str | None = None) -> str:
    return _resolve_translator(translator, locale)("bot-turned-off")


def home_title(*, translator: Translate | None = None, locale: str | None = None) -> str:
    return _resolve_translator(translator, locale)("home-title")


def exchange_step(
    current: int,
    total: int,
    *,
    translator: Translate | None = None,
    locale: str | None = None,
) -> str:
    return _resolve_translator(translator, locale)("exchange-step", current=current, total=total)


def exchange_rate(
    rubthb: float,
    usdtthb: float | None = None,
    updated_at: str | None = None,
    *,
    translator: Translate | None = None,
    locale: str | None = None,
) -> str:
    translate = _resolve_translator(translator, locale)
    return translate(
        "menu-rate-info",
        rub_rate=f"{rubthb:.4f}",
        usdt_rate=f"{(usdtthb or 0.0):.4f}",
        updated_at=updated_at or datetime.utcnow().strftime("%H:%M"),
    )


def choose_currency_prompt(
    *,
    translator: Translate | None = None,
    locale: str | None = None,
) -> str:
    return _resolve_translator(translator, locale)("exchange-choose-currency")


def enter_amount_prompt(
    currency: str,
    *,
    translator: Translate | None = None,
    locale: str | None = None,
) -> str:
    return _resolve_translator(translator, locale)("exchange-enter-amount", currency=currency)


def invalid_amount(*, translator: Translate | None = None, locale: str | None = None) -> str:
    return _resolve_translator(translator, locale)("exchange-amount-invalid")


def choose_method_prompt(
    currency: str,
    *,
    translator: Translate | None = None,
    locale: str | None = None,
) -> str:
    return _resolve_translator(translator, locale)("exchange-choose-method", currency=currency)


def exchange_rate_unavailable(
    *,
    translator: Translate | None = None,
    locale: str | None = None,
) -> str:
    return _resolve_translator(translator, locale)("exchange-rate-unavailable")


def exchange_confirm_summary(
    *,
    amount: int,
    from_currency: str,
    result: int,
    to_currency: str,
    method: str,
    current: int = 4,
    total: int = 4,
    translator: Translate | None = None,
    locale: str | None = None,
) -> str:
    return _resolve_translator(translator, locale)(
        "exchange-confirm-summary",
        amount=f"{amount:,}",
        from_currency=from_currency,
        result=f"{result:,}",
        to_currency=to_currency,
        method=method,
        current=current,
        total=total,
    )


def order_created(
    order_id: int,
    amount_sell: int,
    currency_sell: str,
    amount_buy: int,
    currency_buy: str,
    *,
    translator: Translate | None = None,
    locale: str | None = None,
) -> str:
    del amount_sell, currency_sell, amount_buy, currency_buy
    return _resolve_translator(translator, locale)("order-created", id=order_id)


def order_confirmed(
    order_id: int,
    *,
    translator: Translate | None = None,
    locale: str | None = None,
) -> str:
    return _resolve_translator(translator, locale)("order-confirmed", id=order_id)


def order_completed(
    order_id: int,
    *,
    translator: Translate | None = None,
    locale: str | None = None,
) -> str:
    return _resolve_translator(translator, locale)("order-completed", id=order_id)


def order_cancelled(
    order_id: int,
    *,
    translator: Translate | None = None,
    locale: str | None = None,
) -> str:
    return _resolve_translator(translator, locale)("order-cancelled", id=order_id)


def orders_empty(*, translator: Translate | None = None, locale: str | None = None) -> str:
    return _resolve_translator(translator, locale)("orders-empty")


def orders_header(*, translator: Translate | None = None, locale: str | None = None) -> str:
    return _resolve_translator(translator, locale)("orders-header")


def orders_item(
    *,
    order_id: int,
    amount_sell: int,
    currency_sell: str,
    amount_buy: int,
    currency_buy: str,
    translator: Translate | None = None,
    locale: str | None = None,
) -> str:
    return _resolve_translator(translator, locale)(
        "orders-item",
        id=order_id,
        amount_sell=f"{amount_sell:,}",
        currency_sell=currency_sell,
        amount_buy=f"{amount_buy:,}",
        currency_buy=currency_buy,
    )


def new_order_operator(
    order_id: int,
    user_id: int,
    amount_sell: int,
    currency_sell: str,
    amount_buy: int,
    currency_buy: str,
    method: str,
) -> str:
    return (
        f"🆕 <b>Новая заявка #{order_id}</b>\n\n"
        f"👤 Пользователь: <code>{user_id}</code>\n"
        f"💸 Отдаёт: <b>{amount_sell:,} {currency_sell}</b>\n"
        f"💰 Получает: <b>{amount_buy:,} {currency_buy}</b>\n"
        f"📦 Способ: <b>{method}</b>"
    )
