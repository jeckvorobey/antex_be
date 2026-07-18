"""Защищенный Admin API управления маркетингом."""

from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Annotated

from fastapi import APIRouter, Query, status

from app.api.deps import AdminUser, DbDep
from app.exceptions import AntExException
from app.modules.marketing.admin_service import MarketingAdminService
from app.modules.marketing.constants import MARKETING_CAMPAIGN_STATUSES
from app.modules.marketing.schemas import (
    ApplicationListOut,
    CampaignCodePreviewOut,
    CampaignCreate,
    CampaignListOut,
    CampaignOut,
    CampaignUpdate,
    DailyMetricOut,
    DailyMetricUpsert,
    DashboardOut,
    MarketingCurrencyCreate,
    MarketingCurrencyOut,
    MarketingPlatformCreate,
    MarketingPlatformOut,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/admin/marketing", tags=["admin-marketing"])


@router.post("/campaigns", response_model=CampaignOut, status_code=status.HTTP_201_CREATED)
async def create_campaign(
    payload: CampaignCreate,
    db: DbDep,
    _: AdminUser,
) -> CampaignOut:
    return await MarketingAdminService(db).create_campaign(payload)


@router.post("/campaigns/code-preview", response_model=CampaignCodePreviewOut)
async def generate_campaign_code_preview(
    db: DbDep,
    _: AdminUser,
) -> CampaignCodePreviewOut:
    """Выдаёт незаписанный уникальный код для предварительного показа в форме."""
    code, token = await MarketingAdminService(db).generate_campaign_code_preview()
    return CampaignCodePreviewOut(code=code, token=token)


@router.get("/platforms", response_model=list[MarketingPlatformOut])
async def list_platforms(db: DbDep, _: AdminUser) -> list[MarketingPlatformOut]:
    return await MarketingAdminService(db).list_platforms()


@router.post("/platforms", response_model=MarketingPlatformOut, status_code=status.HTTP_201_CREATED)
async def create_platform(
    payload: MarketingPlatformCreate,
    db: DbDep,
    _: AdminUser,
) -> MarketingPlatformOut:
    return await MarketingAdminService(db).create_platform(payload)


@router.delete("/platforms/{slug}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_platform(slug: str, db: DbDep, _: AdminUser) -> None:
    await MarketingAdminService(db).delete_platform(slug)


@router.get("/currencies", response_model=list[MarketingCurrencyOut])
async def list_currencies(db: DbDep, _: AdminUser) -> list[MarketingCurrencyOut]:
    return await MarketingAdminService(db).list_currencies()


@router.post(
    "/currencies",
    response_model=MarketingCurrencyOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_currency(
    payload: MarketingCurrencyCreate,
    db: DbDep,
    _: AdminUser,
) -> MarketingCurrencyOut:
    return await MarketingAdminService(db).create_currency(payload)


@router.delete("/currencies/{code}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_currency(code: str, db: DbDep, _: AdminUser) -> None:
    await MarketingAdminService(db).delete_currency(code.upper())


@router.get("/campaigns", response_model=CampaignListOut)
async def list_campaigns(
    db: DbDep,
    _: AdminUser,
    search: str | None = None,
    provider: str | None = None,
    campaign_status: Annotated[str | None, Query(alias="status")] = None,
    include_archived: bool = False,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> CampaignListOut:
    _validate_filter_values(provider=provider, campaign_status=campaign_status)
    service = MarketingAdminService(db)
    items, total = await service.repository.list_campaigns(
        search=search,
        provider=provider,
        status=campaign_status,
        include_archived=include_archived,
        limit=limit,
        offset=offset,
    )
    aggregates = await service.repository.campaign_aggregates([item.id for item in items])
    return CampaignListOut(
        items=[service.campaign_out(item, aggregates.get(item.id)) for item in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/campaigns/{campaign_id}", response_model=CampaignOut)
async def get_campaign(campaign_id: int, db: DbDep, _: AdminUser) -> CampaignOut:
    service = MarketingAdminService(db)
    return service.campaign_out(await service.require_campaign(campaign_id))


@router.patch("/campaigns/{campaign_id}", response_model=CampaignOut)
async def update_campaign(
    campaign_id: int,
    payload: CampaignUpdate,
    db: DbDep,
    _: AdminUser,
) -> CampaignOut:
    return await MarketingAdminService(db).update_campaign(campaign_id, payload)


@router.put(
    "/campaigns/{campaign_id}/daily-metrics/{metric_date}",
    response_model=DailyMetricOut,
)
async def upsert_daily_metric(
    campaign_id: int,
    metric_date: date,
    payload: DailyMetricUpsert,
    db: DbDep,
    admin: AdminUser,
) -> DailyMetricOut:
    result = await MarketingAdminService(db).upsert_daily_metric(
        campaign_id,
        metric_date,
        payload,
    )
    logger.info(
        "Marketing daily metric saved: campaign_id=%s metric_date=%s admin_id=%s",
        campaign_id,
        metric_date,
        admin.id,
    )
    return result


@router.get("/applications", response_model=ApplicationListOut)
async def get_applications(
    db: DbDep,
    _: AdminUser,
    date_from: Annotated[date | None, Query(alias="dateFrom")] = None,
    date_to: Annotated[date | None, Query(alias="dateTo")] = None,
    campaign_id: Annotated[int | None, Query(alias="campaignId")] = None,
    provider: str | None = None,
    campaign_status: Annotated[str | None, Query(alias="status")] = None,
    currency: str | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ApplicationListOut:
    date_from, date_to = _period(date_from, date_to)
    currency = currency.upper() if currency else None
    _validate_filter_values(provider=provider, campaign_status=campaign_status)
    rows = await MarketingAdminService(db).application_report(
        date_from=date_from,
        date_to=date_to,
        campaign_id=campaign_id,
        provider=provider,
        status=campaign_status,
        currency=currency,
        limit=limit,
        offset=offset,
    )
    total = await MarketingAdminService(db).repository.count_report_campaigns(
        campaign_id=campaign_id,
        provider=provider,
        status=campaign_status,
        currency=currency,
    )
    return ApplicationListOut(
        items=rows,
        total=total,
        limit=limit,
        offset=offset,
        appliedFilters={
            "dateFrom": date_from.isoformat(),
            "dateTo": date_to.isoformat(),
            "campaignId": campaign_id,
            "provider": provider,
            "status": campaign_status,
            "currency": currency,
        },
    )


@router.get("/dashboard", response_model=DashboardOut)
async def get_dashboard(
    db: DbDep,
    _: AdminUser,
    date_from: Annotated[date | None, Query(alias="dateFrom")] = None,
    date_to: Annotated[date | None, Query(alias="dateTo")] = None,
    campaign_id: Annotated[int | None, Query(alias="campaignId")] = None,
    provider: str | None = None,
    currency: str | None = None,
) -> DashboardOut:
    date_from, date_to = _period(date_from, date_to)
    currency = currency.upper() if currency else None
    _validate_filter_values(provider=provider, campaign_status=None)
    data = await MarketingAdminService(db).dashboard(
        date_from=date_from,
        date_to=date_to,
        campaign_id=campaign_id,
        provider=provider,
        currency=currency,
    )
    return DashboardOut.model_validate(data)


def _period(date_from: date | None, date_to: date | None) -> tuple[date, date]:
    today = date.today()
    end = date_to or today
    start = date_from or end - timedelta(days=29)
    if start > end:
        raise AntExException(
            "dateFrom must not be later than dateTo",
            code="INVALID_MARKETING_DATE_RANGE",
            status_code=422,
        )
    return start, end


def _validate_filter_values(*, provider: str | None, campaign_status: str | None) -> None:
    if campaign_status is not None and campaign_status not in MARKETING_CAMPAIGN_STATUSES:
        raise AntExException(
            "Unsupported campaign status",
            code="UNSUPPORTED_CAMPAIGN_STATUS",
            status_code=422,
        )
