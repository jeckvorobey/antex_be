"""Enums для заявок."""

from __future__ import annotations

from enum import IntEnum


class OrderStatus(IntEnum):
    NEW = 1
    CONFIRMED = 2
    PROCESSING = 3
    COMPLETED = 4
    CANCELLED = 5


class MethodGet(str):
    CASH = "cash"
    QR = "qr"
    RS = "rs"


class CurrencyType(str):
    RUB = "RUB"
    USDT = "USDT"
    THB = "THB"
