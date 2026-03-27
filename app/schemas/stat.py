"""Схемы статистики."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class StatOut(BaseModel):
    id: int
    UserId: int
    count: int
    trigger: str
    createdAt: datetime
    updatedAt: datetime

    model_config = {"from_attributes": True}
