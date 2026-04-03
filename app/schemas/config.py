"""Схемы конфигурации."""
# ruff: noqa: N815

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class AppConfigOut(BaseModel):
    id: int
    enabled: bool
    allowance: float
    createdAt: datetime
    updatedAt: datetime

    model_config = {"from_attributes": True}


class AppConfigUpdate(BaseModel):
    enabled: bool | None = None
    allowance: float | None = None


class AllowanceOut(BaseModel):
    value: float


class AllowanceUpdate(BaseModel):
    value: float = Field(ge=0.0, le=100.0)
