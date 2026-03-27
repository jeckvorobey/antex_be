"""Схемы банковского счёта."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class BankAccountOut(BaseModel):
    id: int
    BankId: int
    OrderId: int
    account: str
    recipient: str
    createdAt: datetime
    updatedAt: datetime

    model_config = {"from_attributes": True}


class BankAccountCreate(BaseModel):
    BankId: int
    OrderId: int
    account: str
    recipient: str
