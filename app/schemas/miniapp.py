"""Схемы miniapp API."""
# ruff: noqa: N815

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.city import CityOut
from app.schemas.rate import RateOut


class MiniappProfileResponse(BaseModel):
    id: int
    username: str | None
    first_name: str | None
    last_name: str | None
    language_code: str | None
    role: int
    is_premium: bool
    city: CityOut | None = None


class MiniappRatesResponse(BaseModel):
    items: list[RateOut]


class MiniappCitiesResponse(BaseModel):
    items: list[CityOut]


class MiniappOrderCreate(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    city_id: int = Field(alias="cityId")
    currency_sell: str = Field(alias="currencySell", min_length=3, max_length=20)
    amount_sell: int = Field(alias="amountSell", gt=0)
    currency_buy: str = Field(alias="currencyBuy", min_length=3, max_length=20)
    amount_buy: float | None = Field(default=None, alias="amountBuy")
    rate: float | None = None
    address: str | None = None
    contact_telegram: str | None = Field(default=None, alias="contactTelegram", max_length=255)
    method_get: str | None = Field(default=None, alias="methodGet", max_length=20)


class MiniappOrderItem(BaseModel):
    id: int
    cityId: int
    currencySell: str
    amountSell: int
    currencyBuy: str
    amountBuy: float | None
    rate: float | None
    status: int
    address: str | None
    contactTelegram: str | None
    methodGet: str | None
    createdAt: datetime
    updatedAt: datetime
    city: CityOut


class MiniappOrdersResponse(BaseModel):
    items: list[MiniappOrderItem]


class MiniappOrderCreatedResponse(BaseModel):
    success: bool = True
    orderId: int


def build_miniapp_profile(user) -> MiniappProfileResponse:
    from app.schemas.city import build_city_out

    return MiniappProfileResponse(
        id=user.id,
        username=user.username,
        first_name=user.first_name,
        last_name=user.last_name,
        language_code=user.language_code,
        role=user.role,
        is_premium=user.is_premium,
        city=build_city_out(user.city) if user.city else None,
    )


def build_miniapp_order_item(order) -> MiniappOrderItem:
    from app.schemas.city import build_city_out

    return MiniappOrderItem(
        id=order.id,
        cityId=order.CityId,
        currencySell=order.currencySell,
        amountSell=order.amountSell,
        currencyBuy=order.currencyBuy,
        amountBuy=order.amountBuy,
        rate=order.rate,
        status=order.status,
        address=order.address,
        contactTelegram=order.contactTelegram,
        methodGet=order.methodGet,
        createdAt=order.createdAt,
        updatedAt=order.updatedAt,
        city=build_city_out(order.city),
    )
