"""Схемы курса валют."""
# ruff: noqa: N815

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class RateOut(BaseModel):
    id: int
    currency: str
    price: float
    createdAt: datetime
    updatedAt: datetime

    model_config = {"from_attributes": True}


class RateCreate(BaseModel):
    currency: str = Field(min_length=3, max_length=20)
    price: float


class RateUpdate(BaseModel):
    currency: str | None = Field(default=None, min_length=3, max_length=20)
    price: float | None = None
