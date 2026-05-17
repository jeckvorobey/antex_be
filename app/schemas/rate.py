"""Схемы курса валют."""
# ruff: noqa: N815

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.enums.country import Country
from app.services.exchange import (
    format_rate_value,
    get_admin_base_rate,
    get_admin_final_rate,
    get_client_rate,
)


class RateOut(BaseModel):
    id: int
    currency: str
    country: Country
    countryRuName: str
    price: float
    priceDisplay: str
    createdAt: datetime
    updatedAt: datetime

    model_config = {"from_attributes": True}


class AdminRateOut(RateOut):
    baseRate: float
    baseRateDisplay: str
    finalRate: float
    finalRateDisplay: str
    margin: float


class RateCreate(BaseModel):
    model_config = {"extra": "forbid"}

    currency: str = Field(min_length=3, max_length=20)
    country: Country
    price: float
    margin: float = Field(default=3.0, ge=0.0, le=100.0)


class RateUpdate(BaseModel):
    model_config = {"extra": "forbid"}

    currency: str | None = Field(default=None, min_length=3, max_length=20)
    country: Country | None = None
    price: float | None = None
    margin: float | None = Field(default=None, ge=0.0, le=100.0)


def build_rate_out(rate) -> RateOut:
    client_price = get_client_rate(rate)
    return RateOut(
        id=rate.id,
        currency=rate.currency,
        country=rate.country,
        countryRuName=rate.country.ru_name,
        price=client_price,
        priceDisplay=format_rate_value(client_price),
        createdAt=rate.createdAt,
        updatedAt=rate.updatedAt,
    )


def build_admin_rate_out(rate) -> AdminRateOut:
    base_price = get_admin_base_rate(rate)
    final_price = get_admin_final_rate(rate)
    return AdminRateOut(
        id=rate.id,
        currency=rate.currency,
        country=rate.country,
        countryRuName=rate.country.ru_name,
        price=final_price,
        priceDisplay=format_rate_value(final_price),
        baseRate=base_price,
        baseRateDisplay=format_rate_value(base_price),
        finalRate=final_price,
        finalRateDisplay=format_rate_value(final_price),
        margin=rate.margin,
        createdAt=rate.createdAt,
        updatedAt=rate.updatedAt,
    )
