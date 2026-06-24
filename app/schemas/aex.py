"""Схемы AEX (внутренняя валюта)."""
# ruff: noqa: N815

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

# ── Wallet ───────────────────────────────────────────────────────────


class AexWalletOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    balance_available: str
    balance_reserved: str
    balance_total: str
    createdAt: datetime
    updatedAt: datetime


class AexAdminWalletOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    username: str | None = None
    first_name: str | None = None
    balance_available: str
    balance_reserved: str
    balance_total: str
    createdAt: datetime


# ── Ledger Entry ─────────────────────────────────────────────────────


class AexLedgerEntryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    wallet_id: int
    amount: str
    entry_type: str
    reference_type: str | None = None
    reference_id: str | None = None
    description: str | None = None
    createdAt: datetime


class AexOperationsResponse(BaseModel):
    items: list[AexLedgerEntryOut]
    total: int
    limit: int
    offset: int


# ── Rate ─────────────────────────────────────────────────────────────


class AexRateOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    global_rate: str
    createdAt: datetime
    updatedAt: datetime


class AexRateUpdate(BaseModel):
    global_rate: Decimal = Field(gt=0)


class AexPersonalRateOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    rate: str
    createdAt: datetime
    updatedAt: datetime


# ── Requests ─────────────────────────────────────────────────────────


class AexTransferRequest(BaseModel):
    amount: Decimal = Field(gt=0)


class AexAdminCreditRequest(BaseModel):
    user_id: int
    amount: Decimal = Field(gt=0)
    description: str | None = None


class AexAdminDebitRequest(BaseModel):
    user_id: int
    amount: Decimal = Field(gt=0)
    description: str | None = None


# ── Referral ─────────────────────────────────────────────────────────


class ReferralCodeOut(BaseModel):
    referral_code: str
    referral_link: str


class ReferralStatsOut(BaseModel):
    total_referrals: int
    total_earned: str


class ReferralBindRequest(BaseModel):
    referral_code: str


# ── Builders ─────────────────────────────────────────────────────────


def build_aex_wallet_out(wallet) -> AexWalletOut:
    return AexWalletOut(
        id=wallet.id,
        user_id=wallet.user_id,
        balance_available=str(wallet.balance_available),
        balance_reserved=str(wallet.balance_reserved),
        balance_total=str(wallet.balance_available + wallet.balance_reserved),
        createdAt=wallet.createdAt,
        updatedAt=wallet.updatedAt,
    )


def build_admin_wallet_out(wallet) -> AexAdminWalletOut:
    user = getattr(wallet, "user", None)
    return AexAdminWalletOut(
        id=wallet.id,
        user_id=wallet.user_id,
        username=user.username if user else None,
        first_name=user.first_name if user else None,
        balance_available=str(wallet.balance_available),
        balance_reserved=str(wallet.balance_reserved),
        balance_total=str(wallet.balance_available + wallet.balance_reserved),
        createdAt=wallet.createdAt,
    )


def build_aex_ledger_entry_out(entry) -> AexLedgerEntryOut:
    return AexLedgerEntryOut(
        id=entry.id,
        wallet_id=entry.wallet_id,
        amount=str(entry.amount),
        entry_type=entry.entry_type,
        reference_type=entry.reference_type,
        reference_id=entry.reference_id,
        description=entry.description,
        createdAt=entry.createdAt,
    )


def build_aex_rate_out(rate) -> AexRateOut:
    return AexRateOut(
        id=rate.id,
        global_rate=str(rate.global_rate),
        createdAt=rate.createdAt,
        updatedAt=rate.updatedAt,
    )


def build_aex_personal_rate_out(rate) -> AexPersonalRateOut:
    return AexPersonalRateOut(
        id=rate.id,
        user_id=rate.user_id,
        rate=str(rate.rate),
        createdAt=rate.createdAt,
        updatedAt=rate.updatedAt,
    )
