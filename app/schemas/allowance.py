"""Схемы надбавки к курсу."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class AllowanceOut(BaseModel):
    id: int
    value: float
    createdAt: datetime
    updatedAt: datetime

    model_config = {"from_attributes": True}


class AllowanceUpdate(BaseModel):
    value: float
