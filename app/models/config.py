"""Модель конфигурации (id=1, всегда единственная запись)."""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import Boolean, Integer, Numeric
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class Config(Base, TimestampMixin):
    __tablename__ = "Configs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    referral_percent: Mapped[Decimal] = mapped_column(
        Numeric(10, 4),
        default=Decimal("0.2"),
        nullable=False,
    )
    referral_min_withdraw: Mapped[Decimal] = mapped_column(
        Numeric(18, 6),
        default=Decimal("100"),
        nullable=False,
    )
    referral_max_withdraw: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    aex_rate: Mapped[Decimal] = mapped_column(
        Numeric(18, 6),
        default=Decimal("1"),
        nullable=False,
    )
    aex_withdraw_limit: Mapped[Decimal] = mapped_column(
        Numeric(18, 6),
        default=Decimal("100"),
        nullable=False,
    )
