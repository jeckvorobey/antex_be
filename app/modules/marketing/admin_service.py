"""Оркестрация campaign CRUD, метрик и отчетов."""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from typing import Any

import jwt
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.reference_deletion import ReferenceDeletionService
from app.core.security import create_access_token, decode_access_token
from app.core.unique_code import generate_unique_code
from app.enums.order import OrderStatus
from app.exceptions import AntExException
from app.models.marketing import MarketingCampaign, MarketingCurrency, MarketingPlatform
from app.modules.marketing.admin_repository import MarketingAdminRepository
from app.modules.marketing.constants import (
    MARKETING_CODE_ALPHABET,
    MARKETING_CODE_LENGTH,
    MARKETING_CODE_PREVIEW_TOKEN_TYPE,
    MARKETING_CODE_PREVIEW_TTL_SECONDS,
)
from app.modules.marketing.repository import MarketingRepository
from app.modules.marketing.schemas import (
    ApplicationAttributionOut,
    ApplicationRowOut,
    CampaignCreate,
    CampaignOut,
    CampaignUpdate,
    DailyMetricOut,
    DailyMetricUpsert,
    MarketingCurrencyCreate,
    MarketingCurrencyOut,
    MarketingPlatformCreate,
    MarketingPlatformOut,
)


class MarketingAdminService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repository = MarketingAdminRepository(session)
        self.code_repository = MarketingRepository(session)
        self.reference_deletion = ReferenceDeletionService(session)

    async def generate_campaign_code(self) -> str:
        """Генерирует уникальный на текущий момент код без записи в БД."""
        return await generate_unique_code(
            length=MARKETING_CODE_LENGTH,
            alphabet=MARKETING_CODE_ALPHABET,
            exists=self.code_repository.campaign_code_exists,
        )

    async def generate_campaign_code_preview(self) -> tuple[str, str]:
        """Возвращает незаписанный код и короткоживущую подпись."""
        code = await self.generate_campaign_code()
        token = create_access_token(
            {"type": MARKETING_CODE_PREVIEW_TOKEN_TYPE, "code": code},
            ttl=MARKETING_CODE_PREVIEW_TTL_SECONDS,
        )
        return code, token

    @staticmethod
    def preview_code_from_token(token: str) -> str:
        """Проверяет подпись preview token и извлекает серверный marketing code."""
        try:
            payload = decode_access_token(token)
        except jwt.PyJWTError as error:
            raise AntExException(
                "Invalid marketing code preview",
                code="INVALID_MARKETING_CODE_PREVIEW",
                status_code=422,
            ) from error

        code = payload.get("code")
        if (
            payload.get("type") != MARKETING_CODE_PREVIEW_TOKEN_TYPE
            or not isinstance(code, str)
            or len(code) != MARKETING_CODE_LENGTH
            or any(symbol not in MARKETING_CODE_ALPHABET for symbol in code)
        ):
            raise AntExException(
                "Invalid marketing code preview",
                code="INVALID_MARKETING_CODE_PREVIEW",
                status_code=422,
            )
        return code

    async def create_campaign(self, payload: CampaignCreate) -> CampaignOut:
        """Валидирует и атомарно сохраняет кампанию, используя показанный или новый код."""
        username = (settings.telegram_bot_username or "").strip().removeprefix("@")
        if not username:
            raise AntExException(
                "Telegram bot username is not configured",
                code="TELEGRAM_BOT_USERNAME_REQUIRED",
                status_code=503,
            )

        platform = await self.repository.get_platform_by_slug(payload.provider)
        currency = await self.repository.get_currency_by_code(payload.currency)
        if platform is None or currency is None:
            raise AntExException(
                "Unknown marketing reference",
                code="UNKNOWN_MARKETING_REFERENCE",
                status_code=422,
            )

        preview_code = (
            self.preview_code_from_token(payload.code_token)
            if payload.code_token is not None
            else None
        )
        attempts = 1 if preview_code else 5
        values = payload.model_dump(
            by_alias=False,
            exclude={"provider", "currency", "code_token"},
        )
        for _ in range(attempts):
            code = preview_code or await self.generate_campaign_code()
            campaign = MarketingCampaign(
                code=code,
                platform_id=platform.id,
                currency_id=currency.id,
                **values,
            )
            try:
                async with self.session.begin_nested():
                    self.session.add(campaign)
                    await self.session.flush()
            except IntegrityError as error:
                if preview_code:
                    raise AntExException(
                        "Marketing code already exists",
                        code="MARKETING_CODE_ALREADY_EXISTS",
                        status_code=409,
                    ) from error
                continue
            await self.session.commit()
            return self.campaign_out(await self.require_campaign(campaign.id))

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
        if "currency" in values:
            currency = await self.repository.get_currency_by_code(values.pop("currency"))
            if currency is None:
                raise AntExException(
                    "Unknown marketing currency",
                    code="UNKNOWN_MARKETING_CURRENCY",
                    status_code=422,
                )
            values["currency_id"] = currency.id
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
        return self.campaign_out(await self.require_campaign(campaign.id))

    async def list_platforms(self) -> list[MarketingPlatformOut]:
        return [
            MarketingPlatformOut(slug=item.slug, name=item.name)
            for item in await self.repository.list_platforms()
        ]

    async def list_currencies(self) -> list[MarketingCurrencyOut]:
        return [
            MarketingCurrencyOut(code=item.code, name=item.name)
            for item in await self.repository.list_currencies()
        ]

    async def create_platform(self, payload: MarketingPlatformCreate) -> MarketingPlatformOut:
        item = MarketingPlatform(**payload.model_dump())
        self.session.add(item)
        try:
            await self.session.commit()
        except IntegrityError as error:
            await self.session.rollback()
            raise AntExException(
                "Marketing platform already exists",
                code="MARKETING_PLATFORM_ALREADY_EXISTS",
                status_code=409,
            ) from error
        return MarketingPlatformOut(slug=item.slug, name=item.name)

    async def create_currency(self, payload: MarketingCurrencyCreate) -> MarketingCurrencyOut:
        item = MarketingCurrency(**payload.model_dump())
        self.session.add(item)
        try:
            await self.session.commit()
        except IntegrityError as error:
            await self.session.rollback()
            raise AntExException(
                "Marketing currency already exists",
                code="MARKETING_CURRENCY_ALREADY_EXISTS",
                status_code=409,
            ) from error
        return MarketingCurrencyOut(code=item.code, name=item.name)

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
        aggregates: dict[str, Any] | None = None,
    ) -> CampaignOut:
        username = (settings.telegram_bot_username or "").strip().removeprefix("@")
        metrics = aggregates or {}
        spend = float(metrics.get("spend", 0))
        new_users = int(metrics.get("new_users", 0))
        applications = int(metrics.get("applications", 0))
        completed = int(metrics.get("completed_applications", 0))
        return CampaignOut(
            id=campaign.id,
            code=campaign.code,
            name=campaign.name,
            provider=campaign.platform.slug,
            externalId=campaign.external_id,
            objective=campaign.objective,
            status=campaign.status,
            budget=float(campaign.budget) if campaign.budget is not None else None,
            currency=campaign.currency.code,
            startsAt=campaign.starts_at,
            endsAt=campaign.ends_at,
            notes=campaign.notes,
            link=f"https://t.me/{username}?startapp=market_{campaign.code}",
            marketParameter=f"market={campaign.code}",
            createdAt=campaign.createdAt,
            updatedAt=campaign.updatedAt,
            attributedUsers=metrics.get("attributed_users", 0),
            newUsers=new_users,
            returningUsers=metrics.get("returning_users", 0),
            touches=metrics.get("touches", 0),
            uniqueTouchedUsers=metrics.get("unique_touched_users", 0),
            applications=applications,
            completedApplications=completed,
            spend=spend,
            costPerNewUser=round(spend / new_users, 4) if new_users else None,
            costPerApplication=round(spend / applications, 4) if applications else None,
            costPerCompletedApplication=round(spend / completed, 4) if completed else None,
            campaignType="paid" if campaign.budget and campaign.budget > 0 else "free",
        )

    async def delete_platform(self, slug: str) -> bool:
        """Удаляет платформу или скрывает её при наличии исторических кампаний."""
        item = await self.repository.get_platform_any_by_slug(slug)
        if item is None or item.deleted_at is not None:
            raise AntExException(
                "Marketing platform not found",
                code="MARKETING_PLATFORM_NOT_FOUND",
                status_code=404,
            )
        return await self.reference_deletion.delete_or_soft_delete(
            item,
            lambda: self.repository.platform_has_campaigns(item.id),
        )

    async def delete_currency(self, code: str) -> None:
        """Физически удаляет валюту, только когда она не используется компаниями."""
        item = await self.repository.get_currency_by_code(code)
        if item is None:
            raise AntExException(
                "Marketing currency not found",
                code="MARKETING_CURRENCY_NOT_FOUND",
                status_code=404,
            )
        if await self.repository.currency_has_campaigns(item.id):
            raise AntExException(
                "Marketing currency is in use",
                code="MARKETING_CURRENCY_IN_USE",
                status_code=409,
            )
        await self.session.delete(item)
        await self.session.commit()

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

    async def application_attribution_report(
        self,
        *,
        date_from: date,
        date_to: date,
        campaign_id: int | None,
        provider: str | None,
        status: str | None,
        currency: str | None,
        limit: int,
        offset: int,
    ) -> tuple[list[ApplicationAttributionOut], int]:
        start, end = _date_bounds(date_from, date_to)
        rows, total = await self.repository.application_attribution_rows(
            date_from=start,
            date_to=end,
            campaign_id=campaign_id,
            provider=provider,
            status=status,
            currency=currency,
            limit=limit,
            offset=offset,
        )
        items = []
        for row in rows:
            delta = row["application_at"] - row["touch_at"]
            items.append(
                ApplicationAttributionOut(
                    orderId=row["order_id"],
                    publicNumber=row["public_number"],
                    userId=row["user_id"],
                    campaignId=row["campaign_id"],
                    campaignName=row["campaign_name"],
                    userState=row["user_state"],
                    attributionType=row["attribution_type"],
                    touchAt=row["touch_at"],
                    applicationAt=row["application_at"],
                    hoursToApplication=round(delta.total_seconds() / 3600, 2),
                    status=row["status"],
                    completed=row["status"] == int(OrderStatus.COMPLETED),
                )
            )
        return items, total

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
        attribution_rows, touch_rows, order_rows, metric_rows = await self.repository.daily_series(
            date_from=date_from,
            date_to=date_to,
            campaign_id=campaign_id,
            provider=provider,
            currency=currency,
        )
        attributed = sum(row.attributed_users for row in comparison)
        new_users = sum(row.new_users for row in comparison)
        returning_users = sum(row.returning_users for row in comparison)
        touches = sum(row.touches for row in comparison)
        unique_touched_users = sum(row.unique_touched_users for row in comparison)
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
            "newUsers": new_users,
            "returningUsers": returning_users,
            "touches": touches,
            "uniqueTouchedUsers": unique_touched_users,
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
            "costPerNewUser": (
                round(spend_total / new_users, 4)
                if spend_total is not None and new_users > 0
                else None
            ),
            "costPerCompletedApplication": (
                round(spend_total / completed, 4)
                if spend_total is not None and completed > 0
                else None
            ),
        }
        time_series = _zero_filled_series(
            date_from,
            date_to,
            attribution_rows,
            touch_rows,
            order_rows,
            metric_rows,
        )
        return {
            "summary": summary,
            "funnel": [
                {"stage": "New users", "value": new_users},
                {"stage": "Marketing touches", "value": touches},
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
    new_users = int(row["new_users"] or 0)
    returning_users = int(row["returning_users"] or 0)
    touches = int(row["touches"] or 0)
    unique_touched = int(row["unique_touched_users"] or 0)
    new_applications = int(row["new_user_applications"] or 0)
    returning_applications = int(row["returning_user_applications"] or 0)
    return ApplicationRowOut(
        campaignId=row["campaign_id"],
        campaignName=row["campaign_name"],
        code=row["code"],
        provider=row["provider"],
        status=row["status"],
        currency=row["currency"],
        attributedUsers=attributed,
        newUsers=new_users,
        returningUsers=returning_users,
        touches=touches,
        uniqueTouchedUsers=unique_touched,
        applications=applications,
        newUserApplications=new_applications,
        returningUserApplications=returning_applications,
        uniqueApplicants=unique,
        completedApplications=completed,
        attributionToApplicationRate=_rate(unique, attributed),
        newUserToApplicationRate=_rate(new_applications, new_users),
        touchToApplicationRate=_rate(applications, touches),
        applicationCompletionRate=_rate(completed, applications),
        spend=spend,
        costPerApplication=round(spend / applications, 4) if applications else None,
        costPerNewUser=round(spend / new_users, 4) if new_users else None,
        costPerCompletedApplication=round(spend / completed, 4) if completed else None,
    )


def _zero_filled_series(
    date_from: date,
    date_to: date,
    attribution_rows: list[dict[str, Any]],
    touch_rows: list[dict[str, Any]],
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
            "newUsers": 0,
            "returningUsers": 0,
            "touches": 0,
            "applications": 0,
            "completedApplications": 0,
            "impressions": 0,
            "starts": 0,
            "spend": 0.0,
        }
        current += timedelta(days=1)

    for row in attribution_rows:
        day = row["day"]
        bucket = result.get(day.isoformat() if hasattr(day, "isoformat") else str(day))
        if bucket is not None:
            bucket["attributedUsers"] = int(row["attributed_users"] or 0)
            bucket["newUsers"] = int(row["attributed_users"] or 0)

    for row in touch_rows:
        day = row["day"]
        bucket = result.get(day.isoformat() if hasattr(day, "isoformat") else str(day))
        if bucket is not None:
            bucket["returningUsers"] = int(row["returning_users"] or 0)
            bucket["touches"] = int(row["touches"] or 0)

    for row in order_rows:
        day = row["day"]
        bucket = result.get(day.isoformat() if hasattr(day, "isoformat") else str(day))
        if bucket is not None:
            bucket["applications"] = int(row["applications"] or 0)
            bucket["completedApplications"] = int(row["completed_applications"] or 0)

    for row in metric_rows:
        day = row["day"]
        bucket = result.get(day.isoformat() if hasattr(day, "isoformat") else str(day))
        if bucket is not None:
            bucket["impressions"] = int(row["impressions"] or 0)
            bucket["starts"] = int(row["starts"] or 0)
            spend = row["spend"] or 0
            bucket["spend"] = float(spend) if isinstance(spend, Decimal) else int(spend)
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
