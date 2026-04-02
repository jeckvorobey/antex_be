"""Схемы заявки на обмен."""
# ruff: noqa: N815

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.city import CityOut
from app.schemas.user import UserOut


class OrderCreate(BaseModel):
    CityId: int
    currencySell: str = Field(min_length=3, max_length=20)
    amountSell: int = Field(gt=0)
    currencyBuy: str = Field(min_length=3, max_length=20)
    amountBuy: float | None = None
    rate: float | None = None
    address: str | None = None
    contactTelegram: str | None = None
    methodGet: str | None = None


class OrderUpdate(BaseModel):
    status: int | None = None
    address: str | None = None
    methodGet: str | None = None
    endTime: datetime | None = None
    amountBuy: float | None = None
    rate: float | None = None


class OrderOut(BaseModel):
    id: int
    UserId: int
    CityId: int
    currencySell: str
    amountSell: int
    currencyBuy: str
    amountBuy: float | None
    rate: float | None
    status: int
    address: str | None
    contactTelegram: str | None
    methodGet: str | None
    endTime: datetime | None
    destroyTime: datetime | None
    user: UserOut | None = None
    city: CityOut | None = None
    createdAt: datetime
    updatedAt: datetime


class OrderStatusUpdate(BaseModel):
    status: int


def build_order_out(order) -> OrderOut:
    from app.schemas.city import build_city_out
    from app.schemas.user import build_user_out

    return OrderOut(
        id=order.id,
        UserId=order.UserId,
        CityId=order.CityId,
        currencySell=order.currencySell,
        amountSell=order.amountSell,
        currencyBuy=order.currencyBuy,
        amountBuy=order.amountBuy,
        rate=order.rate,
        status=order.status,
        address=order.address,
        contactTelegram=order.contactTelegram,
        methodGet=order.methodGet,
        endTime=order.endTime,
        destroyTime=order.destroyTime,
        user=build_user_out(order.user) if getattr(order, "user", None) else None,
        city=build_city_out(order.city) if getattr(order, "city", None) else None,
        createdAt=order.createdAt,
        updatedAt=order.updatedAt,
    )
