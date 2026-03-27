"""Схемы банка."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class BankOut(BaseModel):
    id: int
    code: str
    name: str
    createdAt: datetime
    updatedAt: datetime

    model_config = {"from_attributes": True}


class BankCreate(BaseModel):
    code: str
    name: str
