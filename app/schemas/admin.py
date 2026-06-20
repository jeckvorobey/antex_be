"""Схемы администратора."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class AdminCreate(BaseModel):
    username: str = Field(min_length=3, max_length=255)
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=8, max_length=255)


class AdminPasswordUpdate(BaseModel):
    admin_id: int = Field(alias="admin_id")
    password: str = Field(min_length=8, max_length=255)


class AdminLogin(BaseModel):
    username: str
    password: str


class AdminOut(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: int
    username: str
    email: str | None
    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime = Field(alias="updatedAt")


class AdminTokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class AdminSummaryRateOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    pair_id: str = Field(alias="pairId")
    label: str
    final_rate: float = Field(alias="finalRate")
    final_rate_display: str = Field(alias="finalRateDisplay")


class AdminSummaryOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    orders_today: int = Field(alias="ordersToday")
    users_total: int = Field(alias="usersTotal")
    featured_rates: list[AdminSummaryRateOut] = Field(alias="featuredRates")
