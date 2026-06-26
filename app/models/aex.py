"""Модели AEX (внутренняя валюта) и реферальной системы."""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.user import User


class AexWallet(Base, TimestampMixin):
    """Кошелёк AEX пользователя."""

    __tablename__ = "AexWallets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("Users.id"),
        unique=True,
        nullable=False,
    )
    balance_available: Mapped[Decimal] = mapped_column(
        Numeric(precision=18, scale=8),
        default=Decimal("0"),
        server_default="0",
        nullable=False,
    )
    balance_reserved: Mapped[Decimal] = mapped_column(
        Numeric(precision=18, scale=8),
        default=Decimal("0"),
        server_default="0",
        nullable=False,
    )

    user: Mapped[User] = relationship("User", back_populates="aex_wallet")
    ledger_entries: Mapped[list[AexLedgerEntry]] = relationship(
        "AexLedgerEntry",
        back_populates="wallet",
    )


class AexLedgerEntry(Base, TimestampMixin):
    """Запись в журнале операций AEX."""

    __tablename__ = "AexLedgerEntries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    wallet_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("AexWallets.id"),
        nullable=False,
    )
    amount: Mapped[Decimal] = mapped_column(
        Numeric(precision=18, scale=8),
        nullable=False,
    )
    entry_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
    )
    reference_type: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )
    reference_id: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )
    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    wallet: Mapped[AexWallet] = relationship(
        "AexWallet",
        back_populates="ledger_entries",
    )


class AexRate(Base, TimestampMixin):
    """Глобальная ставка начисления AEX."""

    __tablename__ = "AexRates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    global_rate: Mapped[Decimal] = mapped_column(
        Numeric(precision=10, scale=6),
        default=Decimal("0.002"),
        server_default="0.002",
        nullable=False,
    )


class AexPersonalRate(Base, TimestampMixin):
    """Персональная ставка начисления AEX для пользователя."""

    __tablename__ = "AexPersonalRates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("Users.id"),
        unique=True,
        nullable=False,
    )
    rate: Mapped[Decimal] = mapped_column(
        Numeric(precision=10, scale=6),
        nullable=False,
    )

    user: Mapped[User] = relationship("User", back_populates="aex_personal_rate")


class AexPartnerRate(Base, TimestampMixin):
    """Партнёрская ставка начисления AEX для пользователя."""

    __tablename__ = "AexPartnerRates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("Users.id"),
        unique=True,
        nullable=False,
    )
    rate: Mapped[Decimal] = mapped_column(
        Numeric(precision=10, scale=6),
        nullable=False,
    )

    user: Mapped[User] = relationship("User", back_populates="aex_partner_rate")
