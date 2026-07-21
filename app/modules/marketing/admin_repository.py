"""Запросы Admin API маркетингового домена."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import case, func, or_, select, union_all
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.enums.order import OrderStatus
from app.models.attribution import MarketingTouch, OrderAttribution, UserAcquisition
from app.models.marketing import (
    MarketingAttribution,
    MarketingCampaign,
    MarketingCurrency,
    MarketingDailyMetric,
    MarketingPlatform,
)
from app.models.order import Order


class MarketingAdminRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_campaign(self, campaign_id: int) -> MarketingCampaign | None:
        return await self.session.scalar(
            select(MarketingCampaign)
            .options(
                selectinload(MarketingCampaign.platform),
                selectinload(MarketingCampaign.currency),
            )
            .where(MarketingCampaign.id == campaign_id)
        )

    async def list_platforms(self) -> list[MarketingPlatform]:
        return list(
            (
                await self.session.scalars(
                    select(MarketingPlatform)
                    .where(MarketingPlatform.deleted_at.is_(None))
                    .order_by(MarketingPlatform.name)
                )
            ).all()
        )

    async def list_currencies(self) -> list[MarketingCurrency]:
        return list(
            (
                await self.session.scalars(
                    select(MarketingCurrency).order_by(MarketingCurrency.code)
                )
            ).all()
        )

    async def get_platform_by_slug(self, slug: str) -> MarketingPlatform | None:
        return await self.session.scalar(
            select(MarketingPlatform).where(
                MarketingPlatform.slug == slug,
                MarketingPlatform.deleted_at.is_(None),
            )
        )

    async def get_platform_any_by_slug(self, slug: str) -> MarketingPlatform | None:
        return await self.session.scalar(
            select(MarketingPlatform).where(MarketingPlatform.slug == slug)
        )

    async def platform_has_campaigns(self, platform_id: int) -> bool:
        return bool(
            await self.session.scalar(
                select(MarketingCampaign.id)
                .where(MarketingCampaign.platform_id == platform_id)
                .limit(1)
            )
        )

    async def currency_has_campaigns(self, currency_id: int) -> bool:
        return bool(
            await self.session.scalar(
                select(MarketingCampaign.id)
                .where(MarketingCampaign.currency_id == currency_id)
                .limit(1)
            )
        )

    async def get_currency_by_code(self, code: str) -> MarketingCurrency | None:
        return await self.session.scalar(
            select(MarketingCurrency).where(MarketingCurrency.code == code)
        )

    async def list_campaigns(
        self,
        *,
        search: str | None,
        provider: str | None,
        status: str | None,
        include_archived: bool,
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
            conditions.append(MarketingPlatform.slug == provider)
        if status:
            conditions.append(MarketingCampaign.status == status)
        elif not include_archived:
            conditions.append(MarketingCampaign.status != "archived")

        total = int(
            (
                await self.session.execute(
                    select(func.count(MarketingCampaign.id))
                    .join(MarketingPlatform)
                    .where(*conditions)
                )
            ).scalar_one()
        )
        result = await self.session.execute(
            select(MarketingCampaign)
            .join(MarketingPlatform)
            .options(
                selectinload(MarketingCampaign.platform),
                selectinload(MarketingCampaign.currency),
            )
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

    async def campaign_aggregates(self, campaign_ids: list[int]) -> dict[int, dict[str, Any]]:
        if not campaign_ids:
            return {}
        result: dict[int, dict[str, Any]] = {item_id: {} for item_id in campaign_ids}
        attributed_source = union_all(
            select(
                UserAcquisition.campaign_id.label("campaign_id"),
                UserAcquisition.user_id.label("user_id"),
            ).where(UserAcquisition.campaign_id.is_not(None)),
            select(
                MarketingAttribution.campaign_id.label("campaign_id"),
                MarketingAttribution.user_id.label("user_id"),
            ),
        ).subquery()
        grouped_queries = {
            "attributed": select(
                attributed_source.c.campaign_id,
                func.count(func.distinct(attributed_source.c.user_id)),
            )
            .where(attributed_source.c.campaign_id.in_(campaign_ids))
            .group_by(attributed_source.c.campaign_id),
            "new_users": select(UserAcquisition.campaign_id, func.count(UserAcquisition.id))
            .where(UserAcquisition.campaign_id.in_(campaign_ids))
            .group_by(UserAcquisition.campaign_id),
            "touches": select(
                MarketingTouch.campaign_id,
                func.count(MarketingTouch.id),
                func.count(func.distinct(MarketingTouch.user_id)),
                func.count(
                    func.distinct(
                        case((MarketingTouch.user_state == "returning", MarketingTouch.user_id))
                    )
                ),
            )
            .where(MarketingTouch.campaign_id.in_(campaign_ids))
            .group_by(MarketingTouch.campaign_id),
            "applications": select(
                OrderAttribution.campaign_id,
                func.count(OrderAttribution.id),
                func.sum(case((Order.status == int(OrderStatus.COMPLETED), 1), else_=0)),
            )
            .join(Order, Order.id == OrderAttribution.order_id)
            .where(OrderAttribution.campaign_id.in_(campaign_ids), Order.destroyTime.is_(None))
            .group_by(OrderAttribution.campaign_id),
            "spend": select(
                MarketingDailyMetric.campaign_id,
                func.coalesce(func.sum(MarketingDailyMetric.spend), 0),
            )
            .where(MarketingDailyMetric.campaign_id.in_(campaign_ids))
            .group_by(MarketingDailyMetric.campaign_id),
        }
        for kind, statement in grouped_queries.items():
            for row in (await self.session.execute(statement)).all():
                campaign_id = int(row[0])
                if kind == "attributed":
                    result[campaign_id]["attributed_users"] = int(row[1] or 0)
                elif kind == "new_users":
                    result[campaign_id]["new_users"] = int(row[1] or 0)
                elif kind == "touches":
                    result[campaign_id].update(
                        touches=int(row[1] or 0),
                        unique_touched_users=int(row[2] or 0),
                        returning_users=int(row[3] or 0),
                    )
                elif kind == "applications":
                    result[campaign_id].update(
                        applications=int(row[1] or 0),
                        completed_applications=int(row[2] or 0),
                    )
                else:
                    result[campaign_id]["spend"] = float(row[1] or 0)
        for values in result.values():
            for key in (
                "new_users",
                "returning_users",
                "touches",
                "unique_touched_users",
                "applications",
                "completed_applications",
            ):
                values.setdefault(key, 0)
            values.setdefault("attributed_users", 0)
            values.setdefault("spend", 0.0)
        return result

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
        conditions = []
        if campaign_id is not None:
            conditions.append(MarketingCampaign.id == campaign_id)
        if provider is not None:
            conditions.append(MarketingPlatform.slug == provider)
        if status is not None:
            conditions.append(MarketingCampaign.status == status)
        if currency is not None:
            conditions.append(MarketingCurrency.code == currency)

        attributed_source = union_all(
            select(
                UserAcquisition.campaign_id.label("campaign_id"),
                UserAcquisition.user_id.label("user_id"),
            ).where(UserAcquisition.campaign_id.is_not(None)),
            select(
                MarketingAttribution.campaign_id.label("campaign_id"),
                MarketingAttribution.user_id.label("user_id"),
            ),
        ).subquery()
        attributed_count = (
            select(func.count(func.distinct(attributed_source.c.user_id)))
            .where(attributed_source.c.campaign_id == MarketingCampaign.id)
            .correlate(MarketingCampaign)
            .scalar_subquery()
        )
        acquisition_count = (
            select(func.count(UserAcquisition.id))
            .where(
                UserAcquisition.campaign_id == MarketingCampaign.id,
                UserAcquisition.acquired_at >= date_from,
                UserAcquisition.acquired_at < date_to,
            )
            .correlate(MarketingCampaign)
            .scalar_subquery()
        )
        returning_users = (
            select(func.count(func.distinct(MarketingTouch.user_id)))
            .where(
                MarketingTouch.campaign_id == MarketingCampaign.id,
                MarketingTouch.user_state == "returning",
                MarketingTouch.touched_at >= date_from,
                MarketingTouch.touched_at < date_to,
            )
            .correlate(MarketingCampaign)
            .scalar_subquery()
        )
        touches = (
            select(func.count(MarketingTouch.id))
            .where(
                MarketingTouch.campaign_id == MarketingCampaign.id,
                MarketingTouch.touched_at >= date_from,
                MarketingTouch.touched_at < date_to,
            )
            .correlate(MarketingCampaign)
            .scalar_subquery()
        )
        unique_touched = (
            select(func.count(func.distinct(MarketingTouch.user_id)))
            .where(
                MarketingTouch.campaign_id == MarketingCampaign.id,
                MarketingTouch.touched_at >= date_from,
                MarketingTouch.touched_at < date_to,
            )
            .correlate(MarketingCampaign)
            .scalar_subquery()
        )
        order_base = [
            OrderAttribution.campaign_id == MarketingCampaign.id,
            Order.id == OrderAttribution.order_id,
            Order.createdAt >= date_from,
            Order.createdAt < date_to,
            Order.destroyTime.is_(None),
        ]
        applications = (
            select(func.count(OrderAttribution.id))
            .select_from(OrderAttribution)
            .join(Order, Order.id == OrderAttribution.order_id)
            .where(*order_base)
            .correlate(MarketingCampaign)
            .scalar_subquery()
        )
        unique_applicants = (
            select(func.count(func.distinct(Order.UserId)))
            .select_from(OrderAttribution)
            .join(Order, Order.id == OrderAttribution.order_id)
            .where(*order_base)
            .correlate(MarketingCampaign)
            .scalar_subquery()
        )
        completed = (
            select(func.count(OrderAttribution.id))
            .select_from(OrderAttribution)
            .join(Order, Order.id == OrderAttribution.order_id)
            .where(*order_base, Order.status == int(OrderStatus.COMPLETED))
            .correlate(MarketingCampaign)
            .scalar_subquery()
        )
        new_applications = (
            select(func.count(OrderAttribution.id))
            .select_from(OrderAttribution)
            .join(Order, Order.id == OrderAttribution.order_id)
            .where(*order_base, OrderAttribution.attribution_type == "acquisition")
            .correlate(MarketingCampaign)
            .scalar_subquery()
        )
        returning_applications = (
            select(func.count(OrderAttribution.id))
            .select_from(OrderAttribution)
            .join(Order, Order.id == OrderAttribution.order_id)
            .where(*order_base, OrderAttribution.attribution_type == "reengagement")
            .correlate(MarketingCampaign)
            .scalar_subquery()
        )

        statement = (
            select(
                MarketingCampaign.id.label("campaign_id"),
                MarketingCampaign.name.label("campaign_name"),
                MarketingCampaign.code,
                MarketingPlatform.slug.label("provider"),
                MarketingCampaign.status,
                MarketingCurrency.code.label("currency"),
                attributed_count.label("attributed_users"),
                acquisition_count.label("new_users"),
                returning_users.label("returning_users"),
                touches.label("touches"),
                unique_touched.label("unique_touched_users"),
                applications.label("applications"),
                new_applications.label("new_user_applications"),
                returning_applications.label("returning_user_applications"),
                unique_applicants.label("unique_applicants"),
                completed.label("completed_applications"),
            )
            .select_from(MarketingCampaign)
            .join(MarketingPlatform)
            .join(MarketingCurrency)
            .where(*conditions)
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
            conditions.append(MarketingPlatform.slug == provider)
        if status is not None:
            conditions.append(MarketingCampaign.status == status)
        if currency is not None:
            conditions.append(MarketingCurrency.code == currency)
        result = await self.session.execute(
            select(func.count(MarketingCampaign.id))
            .join(MarketingPlatform)
            .join(MarketingCurrency)
            .where(*conditions)
        )
        return int(result.scalar_one())

    async def application_attribution_rows(
        self,
        *,
        date_from: datetime,
        date_to: datetime,
        campaign_id: int | None,
        provider: str | None,
        status: str | None,
        currency: str | None,
        limit: int,
        offset: int,
    ) -> tuple[list[dict[str, Any]], int]:
        conditions = [
            Order.createdAt >= date_from,
            Order.createdAt < date_to,
            Order.destroyTime.is_(None),
            OrderAttribution.campaign_id.is_not(None),
        ]
        if campaign_id is not None:
            conditions.append(MarketingCampaign.id == campaign_id)
        if provider is not None:
            conditions.append(MarketingPlatform.slug == provider)
        if status is not None:
            conditions.append(MarketingCampaign.status == status)
        if currency is not None:
            conditions.append(MarketingCurrency.code == currency)
        joins = (
            select(OrderAttribution)
            .join(Order, Order.id == OrderAttribution.order_id)
            .join(MarketingTouch, MarketingTouch.id == OrderAttribution.marketing_touch_id)
            .join(MarketingCampaign, MarketingCampaign.id == OrderAttribution.campaign_id)
            .join(MarketingPlatform)
            .join(MarketingCurrency)
        )
        total = int(
            (
                await self.session.execute(
                    select(func.count(OrderAttribution.id))
                    .select_from(OrderAttribution)
                    .join(Order, Order.id == OrderAttribution.order_id)
                    .join(MarketingTouch, MarketingTouch.id == OrderAttribution.marketing_touch_id)
                    .join(MarketingCampaign, MarketingCampaign.id == OrderAttribution.campaign_id)
                    .join(MarketingPlatform)
                    .join(MarketingCurrency)
                    .where(*conditions)
                )
            ).scalar_one()
        )
        del joins
        statement = (
            select(
                Order.id.label("order_id"),
                Order.publicNumber.label("public_number"),
                Order.UserId.label("user_id"),
                MarketingCampaign.id.label("campaign_id"),
                MarketingCampaign.name.label("campaign_name"),
                MarketingTouch.user_state,
                OrderAttribution.attribution_type,
                OrderAttribution.attributed_at.label("touch_at"),
                Order.createdAt.label("application_at"),
                Order.status,
            )
            .select_from(OrderAttribution)
            .join(Order, Order.id == OrderAttribution.order_id)
            .join(MarketingTouch, MarketingTouch.id == OrderAttribution.marketing_touch_id)
            .join(MarketingCampaign, MarketingCampaign.id == OrderAttribution.campaign_id)
            .join(MarketingPlatform)
            .join(MarketingCurrency)
            .where(*conditions)
            .order_by(Order.createdAt.desc(), Order.id.desc())
            .offset(offset)
            .limit(limit)
        )
        return [
            dict(row) for row in (await self.session.execute(statement)).mappings().all()
        ], total

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
            conditions.append(MarketingPlatform.slug == provider)
        if currency is not None:
            conditions.append(MarketingCurrency.code == currency)
        statement = (
            select(
                MarketingCampaign.id.label("campaign_id"),
                MarketingCurrency.code.label("currency"),
                func.coalesce(func.sum(MarketingDailyMetric.spend), 0).label("spend"),
            )
            .join(MarketingCampaign, MarketingCampaign.id == MarketingDailyMetric.campaign_id)
            .join(MarketingPlatform)
            .join(MarketingCurrency)
            .where(*conditions)
            .group_by(MarketingCampaign.id, MarketingCurrency.code)
        )
        return [dict(row) for row in (await self.session.execute(statement)).mappings().all()]

    async def dashboard_unique_counts(
        self,
        *,
        date_from: datetime,
        date_to: datetime,
        campaign_id: int | None,
        provider: str | None,
        currency: str | None,
    ) -> tuple[int, int, int]:
        touch_conditions = [
            MarketingTouch.touched_at >= date_from,
            MarketingTouch.touched_at < date_to,
        ]
        applicant_conditions = [
            Order.createdAt >= date_from,
            Order.createdAt < date_to,
            Order.destroyTime.is_(None),
        ]
        for conditions in (touch_conditions, applicant_conditions):
            if campaign_id is not None:
                conditions.append(MarketingCampaign.id == campaign_id)
            if provider is not None:
                conditions.append(MarketingPlatform.slug == provider)
            if currency is not None:
                conditions.append(MarketingCurrency.code == currency)
        touched = (
            select(func.count(func.distinct(MarketingTouch.user_id)))
            .join(MarketingCampaign, MarketingCampaign.id == MarketingTouch.campaign_id)
            .join(MarketingPlatform)
            .join(MarketingCurrency)
            .where(*touch_conditions)
            .scalar_subquery()
        )
        returning = (
            select(func.count(func.distinct(MarketingTouch.user_id)))
            .join(MarketingCampaign, MarketingCampaign.id == MarketingTouch.campaign_id)
            .join(MarketingPlatform)
            .join(MarketingCurrency)
            .where(*touch_conditions, MarketingTouch.user_state == "returning")
            .scalar_subquery()
        )
        applicants = (
            select(func.count(func.distinct(Order.UserId)))
            .join(OrderAttribution, OrderAttribution.order_id == Order.id)
            .join(MarketingCampaign, MarketingCampaign.id == OrderAttribution.campaign_id)
            .join(MarketingPlatform)
            .join(MarketingCurrency)
            .where(*applicant_conditions)
            .scalar_subquery()
        )
        row = (await self.session.execute(select(touched, returning, applicants))).one()
        return int(row[0] or 0), int(row[1] or 0), int(row[2] or 0)

    async def daily_series(
        self,
        *,
        date_from: date,
        date_to: date,
        campaign_id: int | None,
        provider: str | None,
        currency: str | None,
    ) -> tuple[
        list[dict[str, Any]],
        list[dict[str, Any]],
        list[dict[str, Any]],
        list[dict[str, Any]],
    ]:
        campaign_conditions = []
        if campaign_id is not None:
            campaign_conditions.append(MarketingCampaign.id == campaign_id)
        if provider is not None:
            campaign_conditions.append(MarketingPlatform.slug == provider)
        if currency is not None:
            campaign_conditions.append(MarketingCurrency.code == currency)

        attribution_result = await self.session.execute(
            select(
                func.date(UserAcquisition.acquired_at).label("day"),
                func.count(UserAcquisition.id).label("attributed_users"),
            )
            .join(MarketingCampaign, MarketingCampaign.id == UserAcquisition.campaign_id)
            .join(MarketingPlatform)
            .join(MarketingCurrency)
            .where(
                func.date(UserAcquisition.acquired_at) >= date_from,
                func.date(UserAcquisition.acquired_at) <= date_to,
                *campaign_conditions,
            )
            .group_by(func.date(UserAcquisition.acquired_at))
        )
        touch_result = await self.session.execute(
            select(
                func.date(MarketingTouch.touched_at).label("day"),
                func.count(MarketingTouch.id).label("touches"),
                func.count(
                    func.distinct(
                        case((MarketingTouch.user_state == "returning", MarketingTouch.user_id))
                    )
                ).label("returning_users"),
            )
            .join(MarketingCampaign, MarketingCampaign.id == MarketingTouch.campaign_id)
            .join(MarketingPlatform)
            .join(MarketingCurrency)
            .where(
                func.date(MarketingTouch.touched_at) >= date_from,
                func.date(MarketingTouch.touched_at) <= date_to,
                *campaign_conditions,
            )
            .group_by(func.date(MarketingTouch.touched_at))
        )
        order_result = await self.session.execute(
            select(
                func.date(Order.createdAt).label("day"),
                func.count(Order.id).label("applications"),
                func.sum(case((Order.status == int(OrderStatus.COMPLETED), 1), else_=0)).label(
                    "completed_applications"
                ),
            )
            .join(OrderAttribution, OrderAttribution.order_id == Order.id)
            .join(MarketingCampaign, MarketingCampaign.id == OrderAttribution.campaign_id)
            .join(MarketingPlatform)
            .join(MarketingCurrency)
            .where(
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
            .join(MarketingPlatform)
            .join(MarketingCurrency)
            .where(
                MarketingDailyMetric.metric_date >= date_from,
                MarketingDailyMetric.metric_date <= date_to,
                *campaign_conditions,
            )
            .group_by(MarketingDailyMetric.metric_date)
        )
        return (
            [dict(row) for row in attribution_result.mappings().all()],
            [dict(row) for row in touch_result.mappings().all()],
            [dict(row) for row in order_result.mappings().all()],
            [dict(row) for row in metric_result.mappings().all()],
        )
