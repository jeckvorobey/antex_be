"""Схемы администратора."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.user import UserOut


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
    rate_text: str = Field(alias="rateText")
    updated_at: datetime = Field(alias="updatedAt")


class AdminSummaryUsersOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    total: int
    new_today: int = Field(alias="newToday")
    active_today: int = Field(alias="activeToday")


class AdminSummaryOrdersOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    total: int
    today: int
    new: int
    in_progress: int = Field(alias="inProgress")
    completed_today: int = Field(alias="completedToday")


class AdminSummaryTurnoverOut(BaseModel):
    currency: str
    today: float
    total: float


class AdminSummaryAttentionOrderOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: int
    public_number: str = Field(alias="publicNumber")
    amount_sell: int = Field(alias="amountSell")
    currency_sell: str = Field(alias="currencySell")
    amount_buy: float | None = Field(alias="amountBuy")
    currency_buy: str = Field(alias="currencyBuy")
    status: int
    created_at: datetime = Field(alias="createdAt")
    age_minutes: int = Field(alias="ageMinutes")
    reason: str
    overdue: bool


class AdminSummaryOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    orders_today: int = Field(alias="ordersToday")
    users_total: int = Field(alias="usersTotal")
    featured_rates: list[AdminSummaryRateOut] = Field(alias="featuredRates")
    users: AdminSummaryUsersOut
    orders: AdminSummaryOrdersOut
    attention_orders: list[AdminSummaryAttentionOrderOut] = Field(alias="attentionOrders")
    turnover: list[AdminSummaryTurnoverOut]
    rates: list[AdminSummaryRateOut]
    generated_at: datetime = Field(alias="generatedAt")


class PaginatedUsersResponse(BaseModel):
    items: list[UserOut]
    total: int
    limit: int
    offset: int
