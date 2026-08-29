"""Публичные справочные роуты."""

from __future__ import annotations

from fastapi import APIRouter, Request, status

from app.api.deps import DbDep
from app.repositories.city import CityRepository
from app.repositories.rate import RateRepository
from app.schemas.city import CityOut, build_city_out
from app.schemas.rate import RateOut, build_rate_out
from app.schemas.site_lead import SiteLeadCreate, SiteLeadOut, build_site_lead_out
from app.services.site_leads import create_site_lead as create_site_lead_service

router = APIRouter(prefix="/public", tags=["public"])


@router.get("/cities", response_model=list[CityOut])
async def public_cities(db: DbDep) -> list[CityOut]:
    return [build_city_out(city) for city in await CityRepository(db).get_all()]


@router.get("/rates", response_model=list[RateOut])
async def public_rates(db: DbDep) -> list[RateOut]:
    return [build_rate_out(rate) for rate in await RateRepository(db).get_visible()]


@router.post("/site-leads", response_model=SiteLeadOut, status_code=status.HTTP_201_CREATED)
async def create_site_lead(request: Request, body: SiteLeadCreate, db: DbDep) -> SiteLeadOut:
    lead = await create_site_lead_service(db, body, request)
    return build_site_lead_out(lead)
