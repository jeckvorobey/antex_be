"""Неизменяемые источники привлечения и snapshots атрибуции заявок."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    pass


class UserAcquisition(Base, TimestampMixin):
    __tablename__ = "UserAcquisitions"
    __table_args__ = (
        CheckConstraint(
            "source_type IN ('referral', 'campaign', 'direct', 'legacy')",
            name="ck_user_acquisition_source",
        ),
        Index("ix_user_acquisitions_campaign_acquired", "campaign_id", "acquired_at"),
        CheckConstraint(
            "(source_type = 'referral') = (referrer_user_id IS NOT NULL)",
            name="ck_user_acquisition_referrer",
        ),
        CheckConstraint(
            "(source_type = 'campaign') = (campaign_id IS NOT NULL)",
            name="ck_user_acquisition_campaign",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("Users.id", ondelete="CASCADE"), unique=True)
    source_type: Mapped[str] = mapped_column(String(16), nullable=False)
    referrer_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("Users.id", ondelete="RESTRICT")
    )
    campaign_id: Mapped[int | None] = mapped_column(
        ForeignKey("MarketingCampaigns.id", ondelete="RESTRICT")
    )
    acquired_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class MarketingTouch(Base):
    __tablename__ = "MarketingTouches"
    __table_args__ = (
        CheckConstraint("user_state IN ('new', 'returning')", name="ck_marketing_touch_user_state"),
        Index("ix_marketing_touches_user_touched", "user_id", "touched_at"),
        Index("ix_marketing_touches_campaign_touched", "campaign_id", "touched_at"),
        UniqueConstraint(
            "user_id", "campaign_id", "session_key", name="uq_marketing_touch_session"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("Users.id", ondelete="CASCADE"), nullable=False)
    campaign_id: Mapped[int] = mapped_column(
        ForeignKey("MarketingCampaigns.id", ondelete="RESTRICT"), nullable=False
    )
    touched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    user_state: Mapped[str] = mapped_column(String(16), nullable=False)
    session_key: Mapped[str | None] = mapped_column(String(128))
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSON)


class OrderAttribution(Base):
    __tablename__ = "OrderAttributions"
    __table_args__ = (
        CheckConstraint(
            "attribution_type IN ('acquisition', 'reengagement', 'none')",
            name="ck_order_attribution_type",
        ),
        CheckConstraint(
            "(attribution_type = 'none') = (campaign_id IS NULL)",
            name="ck_order_attribution_campaign",
        ),
        CheckConstraint(
            "(attribution_type = 'none') = (marketing_touch_id IS NULL)",
            name="ck_order_attribution_touch",
        ),
        CheckConstraint("lookback_days BETWEEN 1 AND 90", name="ck_order_attribution_lookback"),
        Index("ix_order_attributions_campaign_attributed", "campaign_id", "attributed_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("Orders.id", ondelete="CASCADE"), unique=True)
    campaign_id: Mapped[int | None] = mapped_column(
        ForeignKey("MarketingCampaigns.id", ondelete="RESTRICT")
    )
    marketing_touch_id: Mapped[int | None] = mapped_column(
        ForeignKey("MarketingTouches.id", ondelete="RESTRICT")
    )
    attribution_type: Mapped[str] = mapped_column(String(16), nullable=False)
    attributed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lookback_days: Mapped[int] = mapped_column(Integer, nullable=False)


class AttributionAuditEvent(Base, TimestampMixin):
    __tablename__ = "AttributionAuditEvents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("Users.id", ondelete="SET NULL"))
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    source_type: Mapped[str | None] = mapped_column(String(16))
    referrer_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("Users.id", ondelete="SET NULL")
    )
    campaign_id: Mapped[int | None] = mapped_column(
        ForeignKey("MarketingCampaigns.id", ondelete="SET NULL")
    )
    reason: Mapped[str | None] = mapped_column(String(128))


Index(
    "ix_attribution_audit_user_created",
    AttributionAuditEvent.user_id,
    AttributionAuditEvent.createdAt,
)
