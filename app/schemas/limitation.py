"""Схемы лимитов."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class LimitationOut(BaseModel):
    id: int
    BankId: int
    amount: int
    baseAmount: int
    icon: str | None
    isActive: bool
    createdAt: datetime
    updatedAt: datetime

    model_config = {"from_attributes": True}


class LimitationUpdate(BaseModel):
    amount: int | None = None
    baseAmount: int | None = None
    icon: str | None = None
    isActive: bool | None = None
