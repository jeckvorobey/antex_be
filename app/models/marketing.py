"""Модели маркетинговых кампаний, атрибуции и дневных метрик."""
# ruff: noqa: RUF002

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.user import User


class MarketingCampaign(Base, TimestampMixin):
    """Рекламная кампания с неизменяемыми code и provider."""

    __tablename__ = "MarketingCampaigns"
    __table_args__ = (
        CheckConstraint("budget IS NULL OR budget >= 0", name="ck_marketing_campaign_budget"),
        Index("ix_marketing_campaigns_provider_status", "provider", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(10), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    source: Mapped[str | None] = mapped_column(String(128), nullable=True)
    medium: Mapped[str | None] = mapped_column(String(128), nullable=True)
    external_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    objective: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="draft")
    budget: Mapped[Decimal | None] = mapped_column(Numeric(18, 8), nullable=True)
    currency: Mapped[str | None] = mapped_column(String(8), nullable=True)
    starts_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    ends_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    attributions: Mapped[list[MarketingAttribution]] = relationship(
        back_populates="campaign",
        cascade="all, delete-orphan",
    )
    daily_metrics: Mapped[list[MarketingDailyMetric]] = relationship(
        back_populates="campaign",
        cascade="all, delete-orphan",
    )


class MarketingAttribution(Base):
    """Неизменяемая first-touch связь пользователя с кампанией."""

    __tablename__ = "MarketingAttributions"
    __table_args__ = (
        Index(
            "ix_marketing_attributions_campaign_attributed",
            "campaign_id",
            "attributed_at",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("Users.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    campaign_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("MarketingCampaigns.id", ondelete="RESTRICT"),
        nullable=False,
    )
    attributed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    user: Mapped[User] = relationship()
    campaign: Mapped[MarketingCampaign] = relationship(back_populates="attributions")


class MarketingDailyMetric(Base, TimestampMixin):
    """Ручные показатели рекламной платформы за календарный день."""

    __tablename__ = "MarketingDailyMetrics"
    __table_args__ = (
        UniqueConstraint(
            "campaign_id",
            "metric_date",
            name="uq_marketing_daily_campaign_date",
        ),
        CheckConstraint("impressions >= 0", name="ck_marketing_daily_impressions"),
        CheckConstraint("starts >= 0", name="ck_marketing_daily_starts"),
        CheckConstraint("spend >= 0", name="ck_marketing_daily_spend"),
        CheckConstraint(
            "platform_cpm IS NULL OR platform_cpm >= 0",
            name="ck_marketing_daily_platform_cpm",
        ),
        Index("ix_marketing_daily_metric_date", "metric_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    campaign_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("MarketingCampaigns.id", ondelete="CASCADE"),
        nullable=False,
    )
    metric_date: Mapped[date] = mapped_column(Date, nullable=False)
    impressions: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    starts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    spend: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=False, default=0)
    platform_cpm: Mapped[Decimal | None] = mapped_column(Numeric(18, 8), nullable=True)

    campaign: Mapped[MarketingCampaign] = relationship(back_populates="daily_metrics")
