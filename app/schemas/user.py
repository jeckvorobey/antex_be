"""Схемы пользователя."""
# ruff: noqa: N815

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, field_validator

from app.enums.user import get_role_title, is_assignable_user_role, normalize_user_role
from app.schemas.auth import build_trusted_contact
from app.schemas.city import CityOut


class UserOut(BaseModel):
    id: int
    telegram_id: int | None
    username: str | None
    phone: str | None
    first_name: str | None
    last_name: str | None
    language_code: str | None
    language_code_app: str
    photo_url: str | None
    is_bot: bool
    role: int
    role_name: str
    is_premium: bool
    city_id: int | None
    city: CityOut | None = None
    trusted_contact: str | None
    trusted_contact_source: str | None
    trusted_contact_ready: bool
    referral_code: str | None = None
    referral_rate: str = "0.002000"
    referral_rate_percent: str = "0.200000"
    aex_balance: str = "0"
    balance: str = "0"
    createdAt: datetime
    updatedAt: datetime


class UserUpdate(BaseModel):
    role: int | None = None
    city_id: int | None = None

    @field_validator("role")
    @classmethod
    def validate_role(cls, value: int | None) -> int | None:
        if value is None:
            return None
        if not is_assignable_user_role(value):
            raise ValueError("Only user and manager roles are allowed")
        return normalize_user_role(value)


def _format_referral_rate(rate: Decimal) -> str:
    return str(rate.quantize(Decimal("0.000001")))


def _format_referral_rate_percent(rate: Decimal) -> str:
    return str((rate * Decimal("100")).quantize(Decimal("0.000001")))


def _resolve_aex_balance(user) -> str:
    wallet = user.__dict__.get("aex_wallet")
    if wallet is None:
        return "0"
    return str(wallet.balance_available)


def build_user_out(user, *, referral_rate: Decimal | None = None) -> UserOut:
    from app.schemas.city import build_city_out

    trusted_contact = build_trusted_contact(user)
    effective_referral_rate = referral_rate
    if effective_referral_rate is None:
        personal_rate = user.__dict__.get("aex_personal_rate")
        effective_referral_rate = (
            personal_rate.rate if personal_rate is not None else Decimal("0.002")
        )
    aex_balance = _resolve_aex_balance(user)

    return UserOut(
        id=user.id,
        telegram_id=user.telegram_id,
        username=user.username,
        phone=user.phone,
        first_name=user.first_name,
        last_name=user.last_name,
        language_code=user.language_code,
        language_code_app=user.language_code_app or "ru",
        photo_url=user.photo_url,
        is_bot=user.is_bot,
        role=normalize_user_role(user.role),
        role_name=get_role_title(user.role),
        is_premium=user.is_premium,
        city_id=user.city_id,
        city=build_city_out(user.city) if user.city else None,
        trusted_contact=trusted_contact.contact,
        trusted_contact_source=trusted_contact.source,
        trusted_contact_ready=trusted_contact.ready,
        referral_code=getattr(user, "referral_code", None),
        referral_rate=_format_referral_rate(effective_referral_rate),
        referral_rate_percent=_format_referral_rate_percent(effective_referral_rate),
        aex_balance=aex_balance,
        balance=aex_balance,
        createdAt=user.createdAt,
        updatedAt=user.updatedAt,
    )
