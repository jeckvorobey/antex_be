"""Утилиты AntEx."""

from __future__ import annotations


def sum_orders(orders: list, field: str = "amountSell") -> int:
    return sum(getattr(o, field, 0) for o in orders)


def format_currency(amount: int | float, currency: str) -> str:
    if isinstance(amount, float):
        return f"{amount:,.4f} {currency}"
    return f"{amount:,} {currency}"
