"""Схемы заявки на обмен."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class OrderCreate(BaseModel):
    currencySell: str
    amountSell: int
    currencyBuy: str
    amountBuy: int
    rate: float
    BankId: int
    CardId: int | None = None
    address: str | None = None
    methodGet: str | None = None


class OrderUpdate(BaseModel):
    status: int | None = None
    address: str | None = None
    methodGet: str | None = None
    endTime: datetime | None = None


class OrderOut(BaseModel):
    id: int
    UserId: int
    BankId: int
    CardId: int | None
    currencySell: str
    amountSell: int
    currencyBuy: str
    amountBuy: int
    rate: float
    status: int
    address: str | None
    methodGet: str | None
    endTime: datetime | None
    destroyTime: datetime | None
    createdAt: datetime
    updatedAt: datetime

    model_config = {"from_attributes": True}
