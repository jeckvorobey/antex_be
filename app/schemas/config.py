"""Схемы конфигурации."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class AppConfigOut(BaseModel):
    id: int
    enabled: bool
    createdAt: datetime
    updatedAt: datetime

    model_config = {"from_attributes": True}
