"""Схемы курса валют."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class RateOut(BaseModel):
    id: int
    currency: str
    price: float
    createdAt: datetime
    updatedAt: datetime

    model_config = {"from_attributes": True}


class RatesResponse(BaseModel):
    rates: list[RateOut]
    rubthb: float
    allowance: float
