"""Запросы Admin API маркетингового домена."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.enums.order import OrderStatus
from app.models.marketing import MarketingAttribution, MarketingCampaign, MarketingDailyMetric
from app.models.order import Order


class MarketingAdminRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_campaign(self, campaign_id: int) -> MarketingCampaign | None:
        return await self.session.get(MarketingCampaign, campaign_id)

    async def list_campaigns(
        self,
        *,
        search: str | None,
        provider: str | None,
        status: str | None,
        limit: int,
        offset: int,
    ) -> tuple[list[MarketingCampaign], int]:
        conditions = []
        if search:
            pattern = f"%{search}%"
            conditions.append(
                or_(MarketingCampaign.name.ilike(pattern), MarketingCampaign.code.ilike(pattern))
            )
        if provider:
            conditions.append(MarketingCampaign.provider == provider)
        if status:
            conditions.append(MarketingCampaign.status == status)

        total = int(
            (
                await self.session.execute(
                    select(func.count(MarketingCampaign.id)).where(*conditions)
                )
            ).scalar_one()
        )
        result = await self.session.execute(
            select(MarketingCampaign)
            .where(*conditions)
            .order_by(MarketingCampaign.createdAt.desc(), MarketingCampaign.id.desc())
            .offset(offset)
            .limit(limit)
        )
        return list(result.scalars().all()), total

    async def upsert_daily_metric(
        self,
        campaign_id: int,
        metric_date: date,
        values: dict[str, Any],
    ) -> MarketingDailyMetric:
        result = await self.session.execute(
            select(MarketingDailyMetric).where(
                MarketingDailyMetric.campaign_id == campaign_id,
                MarketingDailyMetric.metric_date == metric_date,
            )
        )
        metric = result.scalar_one_or_none()
        if metric is None:
            metric = MarketingDailyMetric(
                campaign_id=campaign_id,
                metric_date=metric_date,
                **values,
            )
            self.session.add(metric)
        else:
            for field, value in values.items():
                setattr(metric, field, value)
        await self.session.flush()
        await self.session.refresh(metric)
        return metric

    async def campaign_aggregates(self, campaign_ids: list[int]) -> dict[int, dict[str, int]]:
        if not campaign_ids:
            return {}
        result = await self.session.execute(
            select(
                MarketingCampaign.id.label("campaign_id"),
                func.count(func.distinct(MarketingAttribution.user_id)).label("attributed_users"),
                func.count(Order.id).label("applications"),
            )
            .select_from(MarketingCampaign)
            .outerjoin(
                MarketingAttribution,
                MarketingAttribution.campaign_id == MarketingCampaign.id,
            )
            .outerjoin(
                Order,
                and_(
                    Order.UserId == MarketingAttribution.user_id,
                    Order.createdAt >= MarketingAttribution.attributed_at,
                    Order.destroyTime.is_(None),
                ),
            )
            .where(MarketingCampaign.id.in_(campaign_ids))
            .group_by(MarketingCampaign.id)
        )
        return {
            int(row["campaign_id"]): {
                "attributed_users": int(row["attributed_users"] or 0),
                "applications": int(row["applications"] or 0),
            }
            for row in result.mappings().all()
        }

    async def application_rows(
        self,
        *,
        date_from: datetime,
        date_to: datetime,
        campaign_id: int | None,
        provider: str | None,
        status: str | None = None,
        currency: str | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        attribution_join = and_(
            MarketingAttribution.campaign_id == MarketingCampaign.id,
            MarketingAttribution.attributed_at >= date_from,
            MarketingAttribution.attributed_at < date_to,
        )
        order_join = and_(
            Order.UserId == MarketingAttribution.user_id,
            Order.createdAt >= MarketingAttribution.attributed_at,
            Order.createdAt >= date_from,
            Order.createdAt < date_to,
            Order.destroyTime.is_(None),
        )
        conditions = []
        if campaign_id is not None:
            conditions.append(MarketingCampaign.id == campaign_id)
        if provider is not None:
            conditions.append(MarketingCampaign.provider == provider)
        if status is not None:
            conditions.append(MarketingCampaign.status == status)
        if currency is not None:
            conditions.append(MarketingCampaign.currency == currency)

        statement = (
            select(
                MarketingCampaign.id.label("campaign_id"),
                MarketingCampaign.name.label("campaign_name"),
                MarketingCampaign.code,
                MarketingCampaign.provider,
                MarketingCampaign.status,
                MarketingCampaign.currency,
                func.count(func.distinct(MarketingAttribution.user_id)).label("attributed_users"),
                func.count(Order.id).label("applications"),
                func.count(func.distinct(Order.UserId)).label("unique_applicants"),
                func.sum(case((Order.status == int(OrderStatus.COMPLETED), 1), else_=0)).label(
                    "completed_applications"
                ),
            )
            .select_from(MarketingCampaign)
            .outerjoin(MarketingAttribution, attribution_join)
            .outerjoin(Order, order_join)
            .where(*conditions)
            .group_by(MarketingCampaign.id)
            .order_by(MarketingCampaign.createdAt.desc(), MarketingCampaign.id.desc())
        )
        if limit is not None:
            statement = statement.offset(offset).limit(limit)
        return [dict(row) for row in (await self.session.execute(statement)).mappings().all()]

    async def count_report_campaigns(
        self,
        *,
        campaign_id: int | None,
        provider: str | None,
        status: str | None,
        currency: str | None,
    ) -> int:
        conditions = []
        if campaign_id is not None:
            conditions.append(MarketingCampaign.id == campaign_id)
        if provider is not None:
            conditions.append(MarketingCampaign.provider == provider)
        if status is not None:
            conditions.append(MarketingCampaign.status == status)
        if currency is not None:
            conditions.append(MarketingCampaign.currency == currency)
        result = await self.session.execute(
            select(func.count(MarketingCampaign.id)).where(*conditions)
        )
        return int(result.scalar_one())

    async def spend_rows(
        self,
        *,
        date_from: date,
        date_to: date,
        campaign_id: int | None,
        provider: str | None,
        currency: str | None,
    ) -> list[dict[str, Any]]:
        conditions = [
            MarketingDailyMetric.metric_date >= date_from,
            MarketingDailyMetric.metric_date <= date_to,
        ]
        if campaign_id is not None:
            conditions.append(MarketingCampaign.id == campaign_id)
        if provider is not None:
            conditions.append(MarketingCampaign.provider == provider)
        if currency is not None:
            conditions.append(MarketingCampaign.currency == currency)
        statement = (
            select(
                MarketingCampaign.id.label("campaign_id"),
                MarketingCampaign.currency,
                func.coalesce(func.sum(MarketingDailyMetric.spend), 0).label("spend"),
            )
            .join(MarketingCampaign, MarketingCampaign.id == MarketingDailyMetric.campaign_id)
            .where(*conditions)
            .group_by(MarketingCampaign.id, MarketingCampaign.currency)
        )
        return [dict(row) for row in (await self.session.execute(statement)).mappings().all()]

    async def daily_series(
        self,
        *,
        date_from: date,
        date_to: date,
        campaign_id: int | None,
        provider: str | None,
        currency: str | None,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
        campaign_conditions = []
        if campaign_id is not None:
            campaign_conditions.append(MarketingCampaign.id == campaign_id)
        if provider is not None:
            campaign_conditions.append(MarketingCampaign.provider == provider)
        if currency is not None:
            campaign_conditions.append(MarketingCampaign.currency == currency)

        attribution_result = await self.session.execute(
            select(
                func.date(MarketingAttribution.attributed_at).label("day"),
                func.count(MarketingAttribution.id).label("attributed_users"),
            )
            .join(MarketingCampaign)
            .where(
                func.date(MarketingAttribution.attributed_at) >= date_from,
                func.date(MarketingAttribution.attributed_at) <= date_to,
                *campaign_conditions,
            )
            .group_by(func.date(MarketingAttribution.attributed_at))
        )
        order_result = await self.session.execute(
            select(
                func.date(Order.createdAt).label("day"),
                func.count(Order.id).label("applications"),
                func.sum(case((Order.status == int(OrderStatus.COMPLETED), 1), else_=0)).label(
                    "completed_applications"
                ),
            )
            .join(MarketingAttribution, MarketingAttribution.user_id == Order.UserId)
            .join(MarketingCampaign, MarketingCampaign.id == MarketingAttribution.campaign_id)
            .where(
                Order.createdAt >= MarketingAttribution.attributed_at,
                func.date(Order.createdAt) >= date_from,
                func.date(Order.createdAt) <= date_to,
                Order.destroyTime.is_(None),
                *campaign_conditions,
            )
            .group_by(func.date(Order.createdAt))
        )
        metric_result = await self.session.execute(
            select(
                MarketingDailyMetric.metric_date.label("day"),
                func.sum(MarketingDailyMetric.impressions).label("impressions"),
                func.sum(MarketingDailyMetric.starts).label("starts"),
                func.sum(MarketingDailyMetric.spend).label("spend"),
            )
            .join(MarketingCampaign)
            .where(
                MarketingDailyMetric.metric_date >= date_from,
                MarketingDailyMetric.metric_date <= date_to,
                *campaign_conditions,
            )
            .group_by(MarketingDailyMetric.metric_date)
        )
        return (
            [dict(row) for row in attribution_result.mappings().all()],
            [dict(row) for row in order_result.mappings().all()],
            [dict(row) for row in metric_result.mappings().all()],
        )
