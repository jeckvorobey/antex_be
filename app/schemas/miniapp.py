"""Схемы miniapp API."""
# ruff: noqa: N815

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.enums.country import Country
from app.schemas.city import CityOut
from app.schemas.rate import RateOut


class MiniappProfileResponse(BaseModel):
    id: int
    username: str | None
    first_name: str | None
    last_name: str | None
    language_code: str | None
    role: int
    is_premium: bool
    city: CityOut | None = None


class MiniappProfileSummary(BaseModel):
    id: int
    displayName: str
    username: str | None
    photoUrl: str | None
    isPremium: bool
    languageCode: str


class MiniappQuickAction(BaseModel):
    id: str
    title: str
    subtitle: str
    icon: str
    route: str | None = None
    tone: str


class MiniappRateCard(BaseModel):
    id: str
    label: str
    country: str
    countryLabel: str
    countryFlag: str
    fromCurrency: str
    toCurrency: str
    rate: float
    calculationRate: float
    rateDisplay: str
    rateText: str
    amountSellExample: int
    amountBuyExample: float
    updatedAt: datetime
    availableMethods: list[str]


class MiniappCountryFilterItem(BaseModel):
    id: str
    label: str
    currency: str
    code: str
    flag: str


class MiniappRatesSection(BaseModel):
    featured: list[MiniappRateCard]
    chips: list[str]
    previewLimit: int
    updatedAt: datetime | None


class MiniappServiceItem(BaseModel):
    id: str
    title: str
    subtitle: str
    icon: str


class MiniappLocationItem(BaseModel):
    id: str
    city: str
    country: str
    countryLabel: str
    countryFlag: str
    hours: str
    accent: str


class MiniappBanner(BaseModel):
    title: str
    actionLabel: str


class MiniappHomeResponse(BaseModel):
    profile: MiniappProfileSummary
    quickActions: list[MiniappQuickAction]
    countries: list[MiniappCountryFilterItem]
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
    rateDisplay: str
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


class MiniappMenuItem(BaseModel):
    id: str
    title: str
    icon: str
    action: str
    route: str | None = None
    href: str | None = None


class MiniappProfileScreenResponse(BaseModel):
    user: MiniappProfileSummary
    menu: list[MiniappMenuItem]
    version: str


class MiniappAexReferralItem(BaseModel):
    id: int
    displayName: str
    joinedAt: datetime
    earnedAex: float


class MiniappAexReferralResponse(BaseModel):
    referralCode: str
    referralLink: str
    referrals: list[MiniappAexReferralItem]
    totalReferrals: int


class MiniappRatesResponse(BaseModel):
    items: list[RateOut]


class MiniappCitiesResponse(BaseModel):
    items: list[CityOut]


class MiniappOrderCreate(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    country: Country
    city_id: int | None = Field(default=None, alias="cityId")
    currency_sell: str = Field(alias="currencySell", min_length=3, max_length=20)
    amount_sell: int = Field(alias="amountSell", gt=0)
    currency_buy: str = Field(alias="currencyBuy", min_length=3, max_length=20)
    amount_buy: float = Field(alias="amountBuy", gt=0)
    rate: float = Field(gt=0)
    method_get: Literal["qrcode", "cash", "bank_account", "pay_services"] = Field(alias="methodGet")


class MiniappOrderItem(BaseModel):
    id: int
    publicNumber: str
    cityId: int | None
    country: str
    currencySell: str
    amountSell: int
    currencyBuy: str
    amountBuy: float | None
    rate: float | None
    status: int
    contactTelegram: str | None
    methodGet: str
    createdAt: datetime
    updatedAt: datetime
    city: CityOut | None = None


class MiniappOrdersResponse(BaseModel):
    items: list[MiniappOrderItem]
    limit: int
    offset: int
    total: int
    hasMore: bool


class MiniappAexTransactionItem(BaseModel):
    id: int
    type: str
    amount: float
    balanceAfter: float
    description: str
    createdAt: datetime


class MiniappAexTransactionsResponse(BaseModel):
    items: list[MiniappAexTransactionItem]
    limit: int
    offset: int
    total: int
    hasMore: bool


class MiniappOrderCreatedResponse(BaseModel):
    success: bool = True
    orderId: int


def build_miniapp_profile_summary(user) -> MiniappProfileSummary:
    """Строит компактный профиль для backend-driven экранов miniapp."""
    display_name = " ".join(part for part in (user.first_name, user.last_name) if part).strip()
    if not display_name:
        display_name = user.username or "Гость AntEx"

    return MiniappProfileSummary(
        id=user.id,
        displayName=display_name,
        username=user.username,
        photoUrl=user.photo_url,
        isPremium=user.is_premium,
        languageCode=user.language_code_app or user.language_code or "ru",
    )


def build_miniapp_profile(user) -> MiniappProfileResponse:
    """Строит legacy-профиль пользователя miniapp."""
    from app.schemas.city import build_city_out

    return MiniappProfileResponse(
        id=user.id,
        username=user.username,
        first_name=user.first_name,
        last_name=user.last_name,
        language_code=user.language_code,
        role=user.role,
        is_premium=user.is_premium,
        city=build_city_out(user.city) if user.city else None,
    )


def build_miniapp_aex_referral_item(
    user,
    earned_aex: Decimal | float = 0.0,
) -> MiniappAexReferralItem:
    """Строит строку реферала для miniapp AEX referral screen."""
    display_name = " ".join(part for part in (user.first_name, user.last_name) if part).strip()
    if not display_name:
        display_name = user.username or f"User #{user.id}"

    return MiniappAexReferralItem(
        id=user.id,
        displayName=display_name,
        joinedAt=user.createdAt,
        earnedAex=float(earned_aex),
    )


def build_miniapp_order_item(order) -> MiniappOrderItem:
    """Строит карточку заявки miniapp из ORM-модели."""
    from app.schemas.city import build_city_out

    return MiniappOrderItem(
        id=order.id,
        publicNumber=order.publicNumber,
        cityId=order.CityId,
        country=order.country.value,
        currencySell=order.currencySell,
        amountSell=order.amountSell,
        currencyBuy=order.currencyBuy,
        amountBuy=order.amountBuy,
        rate=order.rate,
        status=order.status,
        contactTelegram=order.contactTelegram,
        methodGet=order.methodGet,
        createdAt=order.createdAt,
        updatedAt=order.updatedAt,
        city=build_city_out(order.city) if order.city else None,
    )
