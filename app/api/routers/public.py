"""Публичные справочные роуты."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import DbDep
from app.repositories.city import CityRepository
from app.repositories.rate import RateRepository
from app.schemas.city import CityOut, build_city_out
from app.schemas.rate import RateOut

router = APIRouter(prefix="/public", tags=["public"])


@router.get("/cities", response_model=list[CityOut])
async def public_cities(db: DbDep) -> list[CityOut]:
    return [build_city_out(city) for city in await CityRepository(db).get_all()]


@router.get("/rates", response_model=list[RateOut])
async def public_rates(db: DbDep) -> list[RateOut]:
    return [RateOut.model_validate(rate) for rate in await RateRepository(db).get_all()]
