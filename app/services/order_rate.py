"""Стабильное представление курса, сохранённого вместе с заявкой."""
# ruff: noqa: RUF002

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.services.exchange import format_rate_value


@dataclass(frozen=True, slots=True)
class OrderRatePresentation:
    value: float
    value_display: str
    currency_sell: str
    currency_buy: str
    text: str


def build_order_rate_presentation(order: Any) -> OrderRatePresentation | None:
    """Использует снимок заявки, а для legacy-строк — прямые поля заявки."""
    value = getattr(order, "displayRate", None)
    if value is None:
        value = getattr(order, "rate", None)
    currency_sell = getattr(order, "displayCurrencySell", None) or getattr(
        order, "currencySell", None
    )
    currency_buy = getattr(order, "displayCurrencyBuy", None) or getattr(order, "currencyBuy", None)
    if value is None or not currency_sell or not currency_buy:
        return None

    numeric_value = float(value)
    value_display = format_rate_value(numeric_value)
    normalized_sell = str(currency_sell).upper()
    normalized_buy = str(currency_buy).upper()
    return OrderRatePresentation(
        value=numeric_value,
        value_display=value_display,
        currency_sell=normalized_sell,
        currency_buy=normalized_buy,
        text=f"1 {normalized_sell} = {value_display} {normalized_buy}",
    )
