"""Схемы администратора."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class AdminLogin(BaseModel):
    username: str
    password: str


class AdminOut(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: int
    username: str
    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime = Field(alias="updatedAt")


class AdminTokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class AdminSummaryOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    orders_today: int = Field(alias="ordersToday")
    users_total: int = Field(alias="usersTotal")
    rub_thb_rate: float | None = Field(alias="rubThbRate")
