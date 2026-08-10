"""Единое представление параметров заявки для Telegram-карточек."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from html import escape
from typing import Any

from app.services.order_rate import build_order_rate_presentation
from app.telegram.i18n import get_translator, normalize_locale

Number = Decimal | int | float

_CURRENCY_LABELS = {
    "RUB": "🇷🇺 RUB",
    "USDT": "₮ USDT",
    "THB": "🇹🇭 THB",
    "GEL": "🇬🇪 GEL",
    "VND": "🇻🇳 VND",
}
_COUNTRY_KEYS = {
    "thailand": "order-country-thailand",
    "vietnam": "order-country-vietnam",
    "georgia": "order-country-georgia",
    "internal": "order-country-internal",
}
_METHOD_KEYS = {
    "cash": "orders-item-method-cash",
    "qrcode": "orders-item-method-qrcode",
    "bank_account": "orders-item-method-bank-account",
    "pay_services": "orders-item-method-pay-services",
}


@dataclass(frozen=True, slots=True)
class OrderMessageView:
    """Безопасный SSOT данных заявки, доступных Telegram presentation-layer."""

    public_number: str
    amount_sell: Number | None = None
    currency_sell: str | None = None
    amount_buy: Number | None = None
    currency_buy: str | None = None
    rate: Number | None = None
    rate_text: str | None = None
    method: str | None = None
    country: str | None = None
    city: str | None = None
    customer_username: str | None = None

    @classmethod
    def from_order(cls, order: Any) -> OrderMessageView:
        """Собрать карточку из заявки, не подставляя фиктивные значения."""
        country = getattr(order, "country", None)
        city = getattr(order, "city", None)
        user = getattr(order, "user", None)
        rate_presentation = build_order_rate_presentation(order)
        has_display_snapshot = all(
            getattr(order, field, None) is not None
            for field in ("displayRate", "displayCurrencySell", "displayCurrencyBuy")
        )
        return cls(
            public_number=str(getattr(order, "publicNumber", "")),
            amount_sell=getattr(order, "amountSell", None),
            currency_sell=getattr(order, "currencySell", None),
            amount_buy=getattr(order, "amountBuy", None),
            currency_buy=getattr(order, "currencyBuy", None),
            rate=getattr(order, "rate", None),
            rate_text=(
                rate_presentation.text
                if rate_presentation is not None and has_display_snapshot
                else None
            ),
            method=getattr(order, "methodGet", None),
            country=getattr(country, "value", country) if country is not None else None,
            city=getattr(city, "name", None),
            customer_username=getattr(user, "username", None),
        )

    @property
    def direction(self) -> str | None:
        """Вернуть направление только при наличии обеих валют."""
        if not self.currency_sell or not self.currency_buy:
            return None
        return f"{self.currency_sell.upper()} → {self.currency_buy.upper()}"


def format_order_number(value: Number, *, locale: str) -> str:
    """Форматировать число, используя разделитель тысяч выбранной локали."""
    decimal_value = Decimal(str(value))
    normalized = format(decimal_value, "f")
    if "." in normalized:
        normalized = normalized.rstrip("0").rstrip(".")
    if not normalized:
        normalized = "0"
    integer, separator, fraction = normalized.partition(".")
    grouped = f"{int(integer):,}"
    if normalize_locale(locale) == "ru":
        grouped = grouped.replace(",", " ")
    return f"{grouped}{separator}{fraction}" if fraction else grouped


def _currency_label(currency: str) -> str:
    normalized = currency.upper()
    return _CURRENCY_LABELS.get(normalized, normalized)


def _localized_value(value: str | None, mapping: dict[str, str], *, locale: str) -> str | None:
    if not value:
        return None
    key = mapping.get(value)
    return get_translator(locale)(key) if key else value


def _order_rows(
    view: OrderMessageView,
    *,
    locale: str,
    include_customer: bool,
) -> list[tuple[str, str]]:
    translate = get_translator(locale)
    rows: list[tuple[str, str]] = []
    if view.amount_sell is not None and view.currency_sell:
        rows.append(
            (
                translate("exchange-summary-sell"),
                f"{format_order_number(view.amount_sell, locale=locale)} "
                f"{_currency_label(view.currency_sell)}",
            )
        )
    if view.amount_buy is not None and view.currency_buy:
        rows.append(
            (
                translate("exchange-summary-buy"),
                f"{format_order_number(view.amount_buy, locale=locale)} "
                f"{_currency_label(view.currency_buy)}",
            )
        )
    if view.rate_text:
        rows.append((translate("exchange-summary-rate"), view.rate_text))
    elif view.rate is not None:
        rows.append(
            (translate("exchange-summary-rate"), format_order_number(view.rate, locale=locale))
        )
    method = _localized_value(view.method, _METHOD_KEYS, locale=locale)
    if method:
        rows.append((translate("exchange-summary-method"), method))
    country = _localized_value(view.country, _COUNTRY_KEYS, locale=locale)
    if country:
        rows.append((translate("exchange-summary-country"), country))
    if view.city:
        rows.append((translate("exchange-summary-city"), view.city))
    if include_customer and view.customer_username:
        rows.append((translate("manager-summary-user"), f"@{view.customer_username}"))
    return rows


def render_order_rich(
    view: OrderMessageView,
    *,
    locale: str,
    include_customer: bool = False,
) -> str:
    """Собрать мобильную двухколоночную Rich-таблицу заявки."""
    caption = escape(get_translator(locale)("order-details-caption"))
    rows = "".join(
        f"<tr><td>{escape(label)}</td><td><b>{escape(value)}</b></td></tr>"
        for label, value in _order_rows(view, locale=locale, include_customer=include_customer)
    )
    return f"<table bordered striped><caption>{caption}</caption>{rows}</table>"


def render_order_regular(
    view: OrderMessageView,
    *,
    locale: str,
    include_customer: bool = False,
) -> str:
    """Собрать функционально эквивалентную вертикальную HTML-сводку."""
    translate = get_translator(locale)
    lines = [f"<b>{escape(translate('order-details-caption'))}</b>"]
    lines.extend(
        f"{escape(label)}: <b>{escape(value)}</b>"
        for label, value in _order_rows(view, locale=locale, include_customer=include_customer)
    )
    return "\n".join(lines)
