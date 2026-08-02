"""Схемы курса валют."""
# ruff: noqa: N815

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from app.enums.country import Country
from app.services.exchange import (
    format_admin_rate_value,
    format_direct_admin_rate_value,
    format_rate_value,
    get_admin_base_rate,
    get_admin_final_rate,
    get_client_rate,
    get_direct_base_rate,
    get_direct_final_rate,
    get_display_pair,
    should_reverse_display_pair,
)
from app.services.rate_fetcher import INTERNAL_RATE_CURRENCIES


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
    country: Country | None
    countryRuName: str | None
    isInternal: bool
    baseRate: float
    baseRateDisplay: str
    finalRate: float
    finalRateDisplay: str
    margin: float
    isReversed: bool
    displayCurrencySell: str
    displayCurrencyBuy: str
    directBaseRate: float
    directBaseRateDisplay: str
    directFinalRate: float
    directFinalRateDisplay: str


class RateCreate(BaseModel):
    model_config = {"extra": "forbid"}

    currency: str = Field(min_length=3, max_length=20)
    country: Country
    price: float
    margin: float = Field(default=3.0, ge=0.0, le=100.0)

    @field_validator("currency")
    @classmethod
    def reject_internal_currency(cls, value: str) -> str:
        """Запрещает создание системных внутренних пар через admin API."""
        normalized = value.upper()
        if normalized in INTERNAL_RATE_CURRENCIES:
            raise ValueError("Internal rate currency is reserved")
        return normalized

    @field_validator("country")
    @classmethod
    def reject_internal_country(cls, value: Country) -> Country:
        if value is Country.INTERNAL:
            raise ValueError("Internal exchange country is reserved")
        return value


class RateUpdate(BaseModel):
    model_config = {"extra": "forbid"}

    currency: str | None = Field(default=None, min_length=3, max_length=20)
    country: Country | None = None
    price: float | None = None
    margin: float | None = Field(default=None, ge=0.0, le=100.0)

    @field_validator("currency")
    @classmethod
    def reject_internal_currency(cls, value: str | None) -> str | None:
        """Запрещает переименование внешнего курса во внутреннюю пару."""
        if value is None:
            return None
        normalized = value.upper()
        if normalized in INTERNAL_RATE_CURRENCIES:
            raise ValueError("Internal rate currency is reserved")
        return normalized

    @field_validator("country")
    @classmethod
    def reject_internal_country(cls, value: Country | None) -> Country | None:
        if value is Country.INTERNAL:
            raise ValueError("Internal exchange country is reserved")
        return value


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
    display_sell, display_buy = get_display_pair(rate)
    direct_base_price = get_direct_base_rate(rate)
    direct_final_price = get_direct_final_rate(rate)
    return AdminRateOut(
        id=rate.id,
        currency=rate.currency,
        country=rate.country,
        countryRuName=rate.country.ru_name if rate.country else None,
        isInternal=rate.is_internal,
        price=final_price,
        priceDisplay=format_admin_rate_value(rate, final_price),
        baseRate=base_price,
        baseRateDisplay=format_admin_rate_value(rate, base_price),
        finalRate=final_price,
        finalRateDisplay=format_admin_rate_value(rate, final_price),
        margin=rate.margin,
        isReversed=should_reverse_display_pair(rate.currency),
        displayCurrencySell=display_sell,
        displayCurrencyBuy=display_buy,
        directBaseRate=direct_base_price,
        directBaseRateDisplay=format_direct_admin_rate_value(rate, direct_base_price),
        directFinalRate=direct_final_price,
        directFinalRateDisplay=format_direct_admin_rate_value(rate, direct_final_price),
        createdAt=rate.createdAt,
        updatedAt=rate.updatedAt,
    )
