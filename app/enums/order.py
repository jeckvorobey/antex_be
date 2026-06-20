"""Enums для заявок."""

from __future__ import annotations

from enum import IntEnum, StrEnum


class OrderStatus(IntEnum):
    CREATED = 1
    PROCESSING = 2
    COMPLETED = 3
    CANCELLED = 4


class MethodGet(StrEnum):
    CASH = "cash"
    QRCODE = "qrcode"
    BANK_ACCOUNT = "bank_account"
    PAY_SERVICES = "pay_services"


class CurrencyType(str):
    RUB = "RUB"
    USDT = "USDT"
    THB = "THB"
