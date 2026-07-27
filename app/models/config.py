"""Модель конфигурации (id=1, всегда единственная запись)."""

from __future__ import annotations

from datetime import time
from decimal import Decimal

from sqlalchemy import JSON, Boolean, CheckConstraint, Integer, Numeric, Time
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class Config(Base, TimestampMixin):
    __tablename__ = "Configs"
    __table_args__ = (
        CheckConstraint(
            "marketing_attribution_window_days BETWEEN 1 AND 90",
            name="ck_config_marketing_attribution_window",
        ),
    )

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
    marketing_attribution_window_days: Mapped[int] = mapped_column(
        Integer,
        default=7,
        server_default="7",
        nullable=False,
    )
    manager_schedule_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    manager_working_days_utc: Mapped[list[int]] = mapped_column(
        JSON,
        default=lambda: [1, 2, 3, 4, 5, 6, 7],
        nullable=False,
    )
    manager_start_time_utc: Mapped[time] = mapped_column(
        Time,
        default=time(6, 0),
        nullable=False,
    )
    manager_end_time_utc: Mapped[time] = mapped_column(
        Time,
        default=time(18, 0),
        nullable=False,
    )
