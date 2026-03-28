"""Pydantic-схемы miniapp API."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class MiniappProfileSummary(BaseModel):
    id: int
    displayName: str
    username: str | None
    isPremium: bool
    languageCode: str


class MiniappQuickAction(BaseModel):
    id: str
    title: str
    subtitle: str
    icon: str
    route: str | None = None
    tone: str = "default"


class MiniappRateCard(BaseModel):
    id: str
    label: str
    fromCurrency: str
    toCurrency: str
    rate: float
    rateText: str
    amountSellExample: int
    amountBuyExample: float
    updatedAt: datetime


class MiniappRatesSection(BaseModel):
    featured: list[MiniappRateCard]
    chips: list[str]
    updatedAt: datetime
    allowance: float


class MiniappServiceItem(BaseModel):
    id: str
    title: str
    subtitle: str
    icon: str


class MiniappLocationItem(BaseModel):
    id: str
    city: str
    hours: str
    accent: str


class MiniappBanner(BaseModel):
    title: str
    actionLabel: str


class MiniappHomeResponse(BaseModel):
    profile: MiniappProfileSummary
    quickActions: list[MiniappQuickAction]
    rates: MiniappRatesSection
    banner: MiniappBanner
    services: list[MiniappServiceItem]
    locations: list[MiniappLocationItem]


class MiniappQuoteResponse(BaseModel):
    currencySell: str
    currencyBuy: str
    amountSell: int
    amountBuy: float
    rate: float
    rateText: str
    updatedAt: datetime
    availableMethods: list[str]


class MiniappCalculatorState(BaseModel):
    fromCurrency: str
    toCurrency: str
    amountSell: int


class MiniappExchangeScreenResponse(BaseModel):
    calculator: MiniappCalculatorState
    chips: list[str]
    pairs: list[MiniappRateCard]
    quote: MiniappQuoteResponse


class MiniappBankSummary(BaseModel):
    id: int
    code: str
    name: str


class MiniappOrderItem(BaseModel):
    id: int
    currencySell: str
    amountSell: int
    currencyBuy: str
    amountBuy: float
    rate: float
    status: int
    methodGet: str | None
    contactTelegram: str | None
    createdAt: datetime
    bank: MiniappBankSummary


class MiniappOrdersResponse(BaseModel):
    items: list[MiniappOrderItem]


class MiniappOrderCreate(BaseModel):
    currencySell: str = Field(min_length=3, max_length=10)
    currencyBuy: str = Field(min_length=3, max_length=10)
    amountSell: int = Field(gt=0)
    contactTelegram: str | None = Field(default=None, max_length=255)
    methodGet: str | None = Field(default="cash", max_length=20)


class MiniappMenuItem(BaseModel):
    id: str
    title: str
    icon: str
    action: str
    route: str | None = None
    href: str | None = None


class MiniappProfileResponse(BaseModel):
    user: MiniappProfileSummary
    menu: list[MiniappMenuItem]
    version: str
