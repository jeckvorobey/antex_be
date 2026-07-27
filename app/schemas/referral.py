"""Схемы реферальной системы."""
# ruff: noqa: RUF002

from __future__ import annotations

from pydantic import BaseModel


class ReferralCodeOut(BaseModel):
    """Ответ с реферальным кодом пользователя."""

    referral_code: str
    referral_link: str


class ReferralStatsOut(BaseModel):
    """Статистика рефералов."""

    total_referrals: int
    total_earned: str  # Decimal как строка для JSON


class ReferralBindRequest(BaseModel):
    """Запрос на привязку реферала по коду."""

    referral_code: str
