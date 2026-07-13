"""Оркестрация campaign CRUD, метрик и отчетов."""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.unique_code import generate_unique_code
from app.exceptions import AntExException
from app.models.marketing import MarketingCampaign
from app.modules.marketing.admin_repository import MarketingAdminRepository
from app.modules.marketing.constants import MARKETING_CODE_ALPHABET, MARKETING_CODE_LENGTH
from app.modules.marketing.repository import MarketingRepository
from app.modules.marketing.schemas import (
    ApplicationRowOut,
    CampaignCreate,
    CampaignOut,
    CampaignUpdate,
    DailyMetricOut,
    DailyMetricUpsert,
)


class MarketingAdminService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repository = MarketingAdminRepository(session)
        self.code_repository = MarketingRepository(session)

    async def create_campaign(self, payload: CampaignCreate) -> CampaignOut:
        username = (settings.telegram_bot_username or "").strip().removeprefix("@")
        if not username:
            raise AntExException(
                "Telegram bot username is not configured",
                code="TELEGRAM_BOT_USERNAME_REQUIRED",
                status_code=503,
            )

        for _ in range(5):
            code = await generate_unique_code(
                length=MARKETING_CODE_LENGTH,
                alphabet=MARKETING_CODE_ALPHABET,
                exists=self.code_repository.campaign_code_exists,
            )
            campaign = MarketingCampaign(code=code, **payload.model_dump(by_alias=False))
            try:
                async with self.session.begin_nested():
                    self.session.add(campaign)
                    await self.session.flush()
            except IntegrityError:
                continue
            await self.session.commit()
            await self.session.refresh(campaign)
            return self.campaign_out(campaign)

        raise AntExException(
            "Unable to persist a unique marketing code",
            code="UNIQUE_CODE_EXHAUSTED",
            status_code=503,
        )

    async def update_campaign(
        self,
        campaign_id: int,
        payload: CampaignUpdate,
    ) -> CampaignOut:
        campaign = await self.require_campaign(campaign_id)
        values = payload.model_dump(exclude_unset=True, by_alias=False)
        starts_at = values.get("starts_at", campaign.starts_at)
        ends_at = values.get("ends_at", campaign.ends_at)
        if starts_at and ends_at and ends_at < starts_at:
            raise AntExException(
                "endsAt must not be earlier than startsAt",
                code="INVALID_CAMPAIGN_DATES",
                status_code=422,
            )
        for field, value in values.items():
            setattr(campaign, field, value)
        await self.session.commit()
        await self.session.refresh(campaign)
        return self.campaign_out(campaign)

    async def upsert_daily_metric(
        self,
        campaign_id: int,
        metric_date: date,
        payload: DailyMetricUpsert,
    ) -> DailyMetricOut:
        await self.require_campaign(campaign_id)
        metric = await self.repository.upsert_daily_metric(
            campaign_id,
            metric_date,
            payload.model_dump(by_alias=False),
        )
        await self.session.commit()
        await self.session.refresh(metric)
        return DailyMetricOut.model_validate(metric, from_attributes=True)

    async def require_campaign(self, campaign_id: int) -> MarketingCampaign:
        campaign = await self.repository.get_campaign(campaign_id)
        if campaign is None:
            raise AntExException(
                "Marketing campaign not found",
                code="MARKETING_CAMPAIGN_NOT_FOUND",
                status_code=404,
            )
        return campaign

    @staticmethod
    def campaign_out(
        campaign: MarketingCampaign,
        aggregates: dict[str, int] | None = None,
    ) -> CampaignOut:
        username = (settings.telegram_bot_username or "").strip().removeprefix("@")
        return CampaignOut(
            id=campaign.id,
            code=campaign.code,
            name=campaign.name,
            provider=campaign.provider,
            source=campaign.source,
            medium=campaign.medium,
            externalId=campaign.external_id,
            objective=campaign.objective,
            status=campaign.status,
            budget=float(campaign.budget) if campaign.budget is not None else None,
            currency=campaign.currency,
            startsAt=campaign.starts_at,
            endsAt=campaign.ends_at,
            notes=campaign.notes,
            link=f"https://t.me/{username}?startapp=market_{campaign.code}",
            marketParameter=f"market={campaign.code}",
            createdAt=campaign.createdAt,
            updatedAt=campaign.updatedAt,
            attributedUsers=(aggregates or {}).get("attributed_users", 0),
            applications=(aggregates or {}).get("applications", 0),
        )

    async def application_report(
        self,
        *,
        date_from: date,
        date_to: date,
        campaign_id: int | None,
        provider: str | None,
        status: str | None,
        currency: str | None,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[ApplicationRowOut]:
        start, end = _date_bounds(date_from, date_to)
        rows = await self.repository.application_rows(
            date_from=start,
            date_to=end,
            campaign_id=campaign_id,
            provider=provider,
            status=status,
            currency=currency,
            limit=limit,
            offset=offset,
        )
        spend_rows = await self.repository.spend_rows(
            date_from=date_from,
            date_to=date_to,
            campaign_id=campaign_id,
            provider=provider,
            currency=currency,
        )
        spend_by_campaign = {row["campaign_id"]: float(row["spend"] or 0) for row in spend_rows}
        return [
            _application_out(row, spend_by_campaign.get(row["campaign_id"], 0.0)) for row in rows
        ]

    async def dashboard(
        self,
        *,
        date_from: date,
        date_to: date,
        campaign_id: int | None,
        provider: str | None,
        currency: str | None,
    ) -> dict[str, Any]:
        comparison = await self.application_report(
            date_from=date_from,
            date_to=date_to,
            campaign_id=campaign_id,
            provider=provider,
            status=None,
            currency=currency,
        )
        spend_rows = await self.repository.spend_rows(
            date_from=date_from,
            date_to=date_to,
            campaign_id=campaign_id,
            provider=provider,
            currency=currency,
        )
        attribution_rows, order_rows, metric_rows = await self.repository.daily_series(
            date_from=date_from,
            date_to=date_to,
            campaign_id=campaign_id,
            provider=provider,
            currency=currency,
        )
        attributed = sum(row.attributed_users for row in comparison)
        applications = sum(row.applications for row in comparison)
        unique_applicants = sum(row.unique_applicants for row in comparison)
        completed = sum(row.completed_applications for row in comparison)
        spend_by_currency: dict[str, float] = {}
        for row in spend_rows:
            key = row["currency"] or "UNSPECIFIED"
            spend_by_currency[key] = spend_by_currency.get(key, 0.0) + float(row["spend"] or 0)
        spend_total = (
            sum(spend_by_currency.values())
            if currency is not None or len(spend_by_currency) <= 1
            else None
        )
        summary = {
            "attributedUsers": attributed,
            "applications": applications,
            "uniqueApplicants": unique_applicants,
            "completedApplications": completed,
            "attributionToApplicationRate": _rate(unique_applicants, attributed),
            "applicationCompletionRate": _rate(completed, applications),
            "spendTotal": spend_total,
            "costPerApplication": (
                round(spend_total / applications, 4)
                if spend_total is not None and applications > 0
                else None
            ),
            "costPerAttributedUser": (
                round(spend_total / attributed, 4)
                if spend_total is not None and attributed > 0
                else None
            ),
        }
        time_series = _zero_filled_series(
            date_from,
            date_to,
            attribution_rows,
            order_rows,
            metric_rows,
        )
        return {
            "summary": summary,
            "funnel": [
                {"stage": "Attributed users", "value": attributed},
                {"stage": "Unique applicants", "value": unique_applicants},
                {"stage": "Completed applications", "value": completed},
            ],
            "timeSeries": time_series,
            "campaignComparison": comparison,
            "spendByCurrency": [
                {"currency": key, "spend": value}
                for key, value in sorted(spend_by_currency.items())
            ],
            "appliedFilters": _filters(date_from, date_to, campaign_id, provider, currency),
        }


def _date_bounds(date_from: date, date_to: date) -> tuple[datetime, datetime]:
    return (
        datetime.combine(date_from, time.min, tzinfo=UTC),
        datetime.combine(date_to + timedelta(days=1), time.min, tzinfo=UTC),
    )


def _rate(numerator: int, denominator: int) -> float | None:
    return round(numerator / denominator * 100, 4) if denominator else None


def _application_out(row: dict[str, Any], spend: float) -> ApplicationRowOut:
    applications = int(row["applications"] or 0)
    attributed = int(row["attributed_users"] or 0)
    unique = int(row["unique_applicants"] or 0)
    completed = int(row["completed_applications"] or 0)
    return ApplicationRowOut(
        campaignId=row["campaign_id"],
        campaignName=row["campaign_name"],
        code=row["code"],
        provider=row["provider"],
        status=row["status"],
        currency=row["currency"],
        attributedUsers=attributed,
        applications=applications,
        uniqueApplicants=unique,
        completedApplications=completed,
        attributionToApplicationRate=_rate(unique, attributed),
        applicationCompletionRate=_rate(completed, applications),
        spend=spend,
        costPerApplication=round(spend / applications, 4) if applications else None,
    )


def _zero_filled_series(
    date_from: date,
    date_to: date,
    attribution_rows: list[dict[str, Any]],
    order_rows: list[dict[str, Any]],
    metric_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    current = date_from
    while current <= date_to:
        key = current.isoformat()
        result[key] = {
            "date": key,
            "attributedUsers": 0,
            "applications": 0,
            "completedApplications": 0,
            "impressions": 0,
            "starts": 0,
            "spend": 0.0,
        }
        current += timedelta(days=1)

    for rows, mapping in (
        (attribution_rows, {"attributed_users": "attributedUsers"}),
        (
            order_rows,
            {"applications": "applications", "completed_applications": "completedApplications"},
        ),
        (metric_rows, {"impressions": "impressions", "starts": "starts", "spend": "spend"}),
    ):
        for row in rows:
            day = row["day"]
            key = day.isoformat() if hasattr(day, "isoformat") else str(day)
            if key not in result:
                continue
            for source, target in mapping.items():
                value = row[source] or 0
                result[key][target] = float(value) if isinstance(value, Decimal) else int(value)
    return list(result.values())


def _filters(
    date_from: date,
    date_to: date,
    campaign_id: int | None,
    provider: str | None,
    currency: str | None,
) -> dict[str, object | None]:
    return {
        "dateFrom": date_from.isoformat(),
        "dateTo": date_to.isoformat(),
        "campaignId": campaign_id,
        "provider": provider,
        "currency": currency,
    }
