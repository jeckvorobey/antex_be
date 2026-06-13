"""Telegram bot message templates."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, cast

from app.services.exchange import ExchangePairSnapshot
from app.telegram.i18n import get_translator

Translate = Callable[[str], str]
_CURRENCY_LABELS = {
    "RUB": "🇷🇺 RUB",
    "USDT": "₮ USDT",
    "THB": "🇹🇭 THB",
    "GEL": "🇬🇪 GEL",
    "VND": "🇻🇳 VND",
}
_CURRENCY_RATE_EMOJIS = {
    "USDT": "₮",
}
_CURRENCY_BUTTON_LABELS = {
    "USDT": "₮ USDT",
}


def _resolve_translator(
    translator: Translate | None = None,
    locale: str | None = None,
) -> Translate:
    return translator or get_translator(locale)


def format_currency_label(currency: str) -> str:
    return _CURRENCY_LABELS.get(currency.upper(), currency.upper())


def format_currency_button_label(currency: str) -> str:
    return _CURRENCY_BUTTON_LABELS.get(currency.upper(), format_currency_label(currency))


def _format_currency_emoji(currency: str) -> str:
    if currency.upper() in _CURRENCY_RATE_EMOJIS:
        return _CURRENCY_RATE_EMOJIS[currency.upper()]
    label = format_currency_label(currency)
    return label.split(maxsplit=1)[0]


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


def exchange_start_welcome(
    first_name: str,
    *,
    translator: Translate | None = None,
    locale: str | None = None,
) -> str:
    return _resolve_translator(translator, locale)("exchange-start-welcome", name=first_name)


def choose_country_prompt(
    *,
    translator: Translate | None = None,
    locale: str | None = None,
) -> str:
    return _resolve_translator(translator, locale)("exchange-choose-country")


def choose_service_prompt(
    country: str,
    *,
    translator: Translate | None = None,
    locale: str | None = None,
) -> str:
    return _resolve_translator(translator, locale)("exchange-choose-service", country=country)


def choose_city_prompt(
    service: str,
    *,
    translator: Translate | None = None,
    locale: str | None = None,
) -> str:
    return _resolve_translator(translator, locale)("exchange-choose-city", service=service)


def exchange_step(
    current: int,
    total: int,
    *,
    translator: Translate | None = None,
    locale: str | None = None,
) -> str:
    return _resolve_translator(translator, locale)("exchange-step", current=current, total=total)


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
    return _resolve_translator(translator, locale)(
        "exchange-enter-amount",
        currency=format_currency_label(currency),
    )


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


def _format_number(value: int | float) -> str:
    if isinstance(value, int):
        return f"{value:,}"
    text = f"{value:,.2f}"
    return text.rstrip("0").rstrip(".")


def exchange_confirm_summary(
    *,
    country: str,
    rate: str,
    amount: int,
    from_currency: str,
    result: int | float,
    to_currency: str,
    method: str,
    city: str | None = None,
    current: int = 4,
    total: int = 4,
    translator: Translate | None = None,
    locale: str | None = None,
) -> str:
    translate = cast(Any, _resolve_translator(translator, locale))
    lines = [translate("exchange-confirm-summary-top", current=current, total=total), ""]
    lines.append(f"🌍 {translate('exchange-summary-country')}: {country}")
    if city:
        lines.append(f"🏙️ {translate('exchange-summary-city')}: {city}")
    lines.append(f"📈 {translate('exchange-summary-rate')}: {rate}")
    sell_label = format_currency_label(from_currency)
    buy_label = format_currency_label(to_currency)
    lines.append(f"💸 {translate('exchange-summary-sell')}: {_format_number(amount)} {sell_label}")
    lines.append(f"💰 {translate('exchange-summary-buy')}: {_format_number(result)} {buy_label}")
    lines.append(f"🧾 {translate('exchange-summary-method')}: {method}")
    lines.extend(["", translate("exchange-confirm-summary-bottom")])
    return "\n".join(lines)


def exchange_rate(sell_rate: float, buy_rate: float) -> str:
    return f"{sell_rate:.2f} / {buy_rate:.2f}"


def exchange_pair_rates(
    pairs: list[ExchangePairSnapshot],
    *,
    translator: Translate | None = None,
    locale: str | None = None,
) -> str:
    translate = cast(Any, _resolve_translator(translator, locale))
    if not pairs:
        return translate("exchange-rate-unavailable")

    def _format_pair(pair: ExchangePairSnapshot) -> str:
        return (
            f"{_format_currency_emoji(pair.currency_sell)} 1 {pair.currency_sell} "
            f"от {pair.rate_display} {pair.currency_buy} "
            f"{_format_currency_emoji(pair.currency_buy)}"
        )

    return "\n".join(_format_pair(pair) for pair in pairs)


def order_created(
    order_id: int | str,
    *,
    translator: Translate | None = None,
    locale: str | None = None,
) -> str:
    return _resolve_translator(translator, locale)("order-created", id=order_id)


def order_creation_failed(
    *,
    code: str | None = None,
    translator: Translate | None = None,
    locale: str | None = None,
) -> str:
    translate = cast(Any, _resolve_translator(translator, locale))
    if code == "ORDER_ALREADY_EXISTS":
        return translate("order-creation-limit-reached")
    return translate("order-creation-failed")


def order_confirmed(
    order_id: int | str,
    *,
    translator: Translate | None = None,
    locale: str | None = None,
) -> str:
    return _resolve_translator(translator, locale)("order-confirmed", id=order_id)


def order_completed(
    order_id: int | str,
    *,
    translator: Translate | None = None,
    locale: str | None = None,
) -> str:
    return _resolve_translator(translator, locale)("order-completed", id=order_id)


def order_cancelled(
    order_id: int | str,
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
    order_id: int | str,
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
        currency_sell=format_currency_label(currency_sell),
        amount_buy=f"{amount_buy:,}",
        currency_buy=format_currency_label(currency_buy),
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
