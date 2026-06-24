"""Enums для AEX (внутренняя валюта)."""

from __future__ import annotations

from enum import StrEnum


class AexLedgerEntryType(StrEnum):
    """Типы проводок в журнале AEX."""

    CREDIT = "credit"
    DEBIT = "debit"
    HOLD = "hold"
    RELEASE = "release"


class AexOperationType(StrEnum):
    """Типы операций AEX (для обратной совместимости)."""

    REFERRAL_BONUS = "referral_bonus"
    ADMIN_CREDIT = "admin_credit"
    ADMIN_DEBIT = "admin_debit"
    SELL = "sell"
    SELL_REVERSAL = "sell_reversal"
