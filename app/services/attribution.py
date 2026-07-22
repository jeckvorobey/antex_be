"""Оркестрация источников привлечения, касаний и order snapshots."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.attribution import (
    AttributionAuditEvent,
    MarketingTouch,
    OrderAttribution,
    UserAcquisition,
)
from app.models.marketing import MarketingCampaign
from app.models.order import Order

logger = logging.getLogger(__name__)


class AttributionService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_acquisition(self, user_id: int) -> UserAcquisition | None:
        return await self.session.scalar(
            select(UserAcquisition).where(UserAcquisition.user_id == user_id)
        )

    async def ensure_acquisition(
        self,
        user_id: int,
        *,
        source_type: str,
        referrer_user_id: int | None = None,
        campaign_id: int | None = None,
    ) -> UserAcquisition:
        existing = await self.get_acquisition(user_id)
        if existing is not None:
            return existing
        item = UserAcquisition(
            user_id=user_id,
            source_type=source_type,
            referrer_user_id=referrer_user_id,
            campaign_id=campaign_id,
        )
        try:
            async with self.session.begin_nested():
                self.session.add(item)
                await self.session.flush()
        except IntegrityError:
            existing = await self.get_acquisition(user_id)
            if existing is None:
                raise
            await self.audit(
                user_id, "acquisition_conflict", source_type=source_type, reason="unique_conflict"
            )
            return existing
        return item

    async def audit(self, user_id: int | None, event_type: str, **values: object) -> None:
        self.session.add(AttributionAuditEvent(user_id=user_id, event_type=event_type, **values))
        await self.session.flush()

    async def record_marketing_touch(
        self,
        user_id: int,
        code: str,
        *,
        is_new_user: bool,
        touched_at: datetime | None = None,
        session_key: str | None = None,
    ) -> MarketingTouch:
        if not session_key:
            raise ValueError("MARKETING_SESSION_KEY_REQUIRED")
        campaign = await self.session.scalar(
            select(MarketingCampaign).where(MarketingCampaign.code == code)
        )
        if campaign is None:
            await self.audit(user_id, "marketing_touch_rejected", reason="unknown_campaign")
            raise ValueError("MARKETING_CAMPAIGN_NOT_FOUND")
        if campaign.status != "active":
            await self.audit(
                user_id,
                "marketing_touch_rejected",
                campaign_id=campaign.id,
                reason="inactive_campaign",
            )
            raise ValueError("MARKETING_CAMPAIGN_INACTIVE")
        existing = await self.session.scalar(
            select(MarketingTouch).where(
                MarketingTouch.user_id == user_id,
                MarketingTouch.campaign_id == campaign.id,
                MarketingTouch.session_key == session_key,
            )
        )
        if existing is not None:
            return existing
        touch = MarketingTouch(
            user_id=user_id,
            campaign_id=campaign.id,
            user_state="new" if is_new_user else "returning",
            touched_at=touched_at or datetime.now(UTC),
            session_key=session_key,
            metadata_={"source": "telegram_init_data", "start_param": f"market_{code}"},
        )
        try:
            async with self.session.begin_nested():
                self.session.add(touch)
                await self.session.flush()
        except IntegrityError:
            existing = await self.session.scalar(
                select(MarketingTouch).where(
                    MarketingTouch.user_id == user_id,
                    MarketingTouch.campaign_id == campaign.id,
                    MarketingTouch.session_key == session_key,
                )
            )
            if existing is None:
                raise
            return existing
        return touch

    async def resolve_order_attribution(
        self, user_id: int, created_at: datetime, lookback_days: int
    ) -> OrderAttribution:
        lower_bound = created_at - timedelta(days=lookback_days)
        touch = await self.session.scalar(
            select(MarketingTouch)
            .where(
                MarketingTouch.user_id == user_id,
                MarketingTouch.touched_at <= created_at,
                MarketingTouch.touched_at >= lower_bound,
            )
            .order_by(MarketingTouch.touched_at.desc(), MarketingTouch.id.desc())
            .limit(1)
        )
        if touch is None:
            logger.info(
                "Order marketing attribution not found: user_id=%s created_at=%s lookback_days=%s",
                user_id,
                created_at.isoformat(),
                lookback_days,
            )
            return OrderAttribution(attribution_type="none", lookback_days=lookback_days)
        return OrderAttribution(
            campaign_id=touch.campaign_id,
            marketing_touch_id=touch.id,
            attribution_type="acquisition" if touch.user_state == "new" else "reengagement",
            attributed_at=touch.touched_at,
            lookback_days=lookback_days,
        )

    async def admin_summaries(self, user_ids: list[int]) -> dict[int, dict[str, object]]:
        """Загружает attribution card для страницы пользователей без N+1."""
        if not user_ids:
            return {}
        result: dict[int, dict[str, object]] = {
            user_id: {"source_status": "missing"} for user_id in user_ids
        }
        acquisitions = await self.session.execute(
            select(UserAcquisition, MarketingCampaign.name)
            .outerjoin(MarketingCampaign, MarketingCampaign.id == UserAcquisition.campaign_id)
            .where(UserAcquisition.user_id.in_(user_ids))
        )
        for acquisition, campaign_name in acquisitions.all():
            result[acquisition.user_id].update(
                source_type=acquisition.source_type,
                acquired_at=acquisition.acquired_at,
                primary_campaign_id=acquisition.campaign_id,
                primary_campaign_name=campaign_name,
                source_status="fixed",
            )

        ranked_touches = (
            select(
                MarketingTouch.user_id,
                MarketingTouch.campaign_id,
                MarketingTouch.touched_at,
                MarketingTouch.user_state,
                func.row_number()
                .over(
                    partition_by=MarketingTouch.user_id,
                    order_by=(MarketingTouch.touched_at.desc(), MarketingTouch.id.desc()),
                )
                .label("position"),
            )
            .where(MarketingTouch.user_id.in_(user_ids))
            .subquery()
        )
        touches = await self.session.execute(
            select(ranked_touches, MarketingCampaign.name)
            .join(MarketingCampaign, MarketingCampaign.id == ranked_touches.c.campaign_id)
            .where(ranked_touches.c.position == 1)
        )
        for row in touches.mappings().all():
            result[row["user_id"]].update(
                last_touch_at=row["touched_at"],
                last_touch_campaign_id=row["campaign_id"],
                last_touch_campaign_name=row["name"],
                last_touch_user_state=row["user_state"],
            )

        ranked_orders = (
            select(
                Order.UserId.label("user_id"),
                OrderAttribution.campaign_id,
                OrderAttribution.attribution_type,
                OrderAttribution.attributed_at,
                Order.createdAt.label("order_created_at"),
                func.row_number()
                .over(
                    partition_by=Order.UserId,
                    order_by=(Order.createdAt.desc(), Order.id.desc()),
                )
                .label("position"),
            )
            .join(OrderAttribution, OrderAttribution.order_id == Order.id)
            .where(Order.UserId.in_(user_ids))
            .subquery()
        )
        order_rows = await self.session.execute(
            select(ranked_orders, MarketingCampaign.name)
            .outerjoin(MarketingCampaign, MarketingCampaign.id == ranked_orders.c.campaign_id)
            .where(ranked_orders.c.position == 1)
        )
        for row in order_rows.mappings().all():
            result[row["user_id"]].update(
                last_order_campaign_id=row["campaign_id"],
                last_order_campaign_name=row["name"],
                last_order_attribution_type=row["attribution_type"],
                last_order_attributed_at=row["attributed_at"],
                last_order_created_at=row["order_created_at"],
            )
        return result
