"""Схемы курса валют."""
# ruff: noqa: N815

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.services.rate import format_rate_value, get_client_rate


class RateOut(BaseModel):
    id: int
    currency: str
    price: float
    priceDisplay: str
    createdAt: datetime
    updatedAt: datetime

    model_config = {"from_attributes": True}


class AdminRateOut(RateOut):
    margin: float


class RateCreate(BaseModel):
    currency: str = Field(min_length=3, max_length=20)
    price: float
    margin: float = Field(default=3.0, ge=0.0, le=100.0)


class RateUpdate(BaseModel):
    currency: str | None = Field(default=None, min_length=3, max_length=20)
    price: float | None = None
    margin: float | None = Field(default=None, ge=0.0, le=100.0)


def build_rate_out(rate) -> RateOut:
    client_price = get_client_rate(rate)
    return RateOut(
        id=rate.id,
        currency=rate.currency,
        price=client_price,
        priceDisplay=format_rate_value(client_price),
        createdAt=rate.createdAt,
        updatedAt=rate.updatedAt,
    )


def build_admin_rate_out(rate) -> AdminRateOut:
    return AdminRateOut(
        id=rate.id,
        currency=rate.currency,
        price=rate.price,
        priceDisplay=format_rate_value(rate.price),
        margin=rate.margin,
        createdAt=rate.createdAt,
        updatedAt=rate.updatedAt,
    )
