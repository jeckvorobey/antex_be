"""Схемы карты."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class CardOut(BaseModel):
    id: int
    bank: str
    name: str
    number: str
    isActive: bool
    createdAt: datetime
    updatedAt: datetime

    model_config = {"from_attributes": True}


class CardCreate(BaseModel):
    bank: str
    name: str
    number: str
    isActive: bool = True
