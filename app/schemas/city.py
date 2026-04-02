"""Схемы городов."""
# ruff: noqa: N815

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.enums.country import Country


class CityCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    country: Country


class CityUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    country: Country | None = None


class CityOut(BaseModel):
    id: int
    name: str
    country: Country
    countryRuName: str
    countryCode: str
    countryFlag: str
    createdAt: datetime
    updatedAt: datetime


def build_city_out(city) -> CityOut:
    return CityOut(
        id=city.id,
        name=city.name,
        country=city.country,
        countryRuName=city.country.ru_name,
        countryCode=city.country.code,
        countryFlag=city.country.flag,
        createdAt=city.createdAt,
        updatedAt=city.updatedAt,
    )
