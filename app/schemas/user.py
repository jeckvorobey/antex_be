"""Схемы пользователя."""
# ruff: noqa: N815

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.enums.user import UserRole, get_role_title, is_assignable_user_role, normalize_user_role
from app.schemas.auth import build_trusted_contact
from app.schemas.city import CityOut
from app.services.aex_rate import DEFAULT_ATXG_RATE, normalize_aex_rate, rate_to_percent


class UserNavigationItem(BaseModel):
    name: str
    label: str
    icon: str
    route: str
    badge_key: str | None = None


def get_role_navigation(role: int | UserRole) -> list[UserNavigationItem]:
    normalized_role = normalize_user_role(role)
    if normalized_role == int(UserRole.MANAGER):
        return [
            UserNavigationItem(
                name="managerDashboard",
                label="Дашборд",
                icon="space_dashboard",
                route="managerDashboard",
                badge_key=None,
            ),
            UserNavigationItem(
                name="managerOrders",
                label="Заявки",
                icon="receipt_long",
                route="managerOrders",
                badge_key=None,
            ),
            UserNavigationItem(
                name="managerChats",
                label="Чаты",
                icon="chat_bubble_outline",
                route="managerChats",
                badge_key="unread_chats",
            ),
            UserNavigationItem(
                name="managerSettings",
                label="Настройки",
                icon="settings",
                route="managerProfile",
                badge_key=None,
            ),
        ]
    return [
        UserNavigationItem(
            name="home",
            label="Главная",
            icon="home",
            route="home",
            badge_key=None,
        ),
        UserNavigationItem(
            name="exchange",
            label="Обмен",
            icon="currency_exchange",
            route="exchange",
            badge_key=None,
        ),
        UserNavigationItem(
            name="history",
            label="История",
            icon="history",
            route="history",
            badge_key=None,
        ),
        UserNavigationItem(
            name="profile",
            label="Профиль",
            icon="person_outline",
            route="profile",
            badge_key=None,
        ),
    ]


class UserAttributionOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    source_type: str | None = Field(default=None, alias="sourceType")
    acquired_at: datetime | None = Field(default=None, alias="acquiredAt")
    primary_campaign_id: int | None = Field(default=None, alias="primaryCampaignId")
    primary_campaign_name: str | None = Field(default=None, alias="primaryCampaignName")
    last_touch_at: datetime | None = Field(default=None, alias="lastTouchAt")
    last_touch_campaign_id: int | None = Field(default=None, alias="lastTouchCampaignId")
    last_touch_campaign_name: str | None = Field(default=None, alias="lastTouchCampaignName")
    last_touch_user_state: str | None = Field(default=None, alias="lastTouchUserState")
    last_order_campaign_id: int | None = Field(default=None, alias="lastOrderCampaignId")
    last_order_campaign_name: str | None = Field(default=None, alias="lastOrderCampaignName")
    last_order_attribution_type: str | None = Field(default=None, alias="lastOrderAttributionType")
    last_order_attributed_at: datetime | None = Field(default=None, alias="lastOrderAttributedAt")
    last_order_created_at: datetime | None = Field(default=None, alias="lastOrderCreatedAt")
    source_status: str = Field(alias="sourceStatus")


class UserOut(BaseModel):
    id: int
    telegram_id: int | None
    username: str | None
    phone: str | None
    first_name: str | None
    last_name: str | None
    language_code: str | None
    language_code_app: str
    photo_url: str | None
    is_bot: bool
    role: int
    role_name: str
    is_premium: bool
    telegram_write_access: bool
    city_id: int | None
    city: CityOut | None = None
    trusted_contact: str | None
    trusted_contact_source: str | None
    trusted_contact_ready: bool
    referral_code: str | None = None
    referred_by: int | None = None
    referral_rate: str = "0.002000"
    referral_rate_percent: str = "0.200000"
    aex_balance: str = "0"
    balance: str = "0"
    attribution: UserAttributionOut | None = None
    navigation: list[UserNavigationItem] = Field(default_factory=list)
    createdAt: datetime
    updatedAt: datetime


class UserUpdate(BaseModel):
    role: int | None = None
    city_id: int | None = None

    @field_validator("role")
    @classmethod
    def validate_role(cls, value: int | None) -> int | None:
        if value is None:
            return None
        if not is_assignable_user_role(value):
            raise ValueError("Only user and manager roles are allowed")
        return normalize_user_role(value)


class TelegramWriteAccessRequest(BaseModel):
    """Результат нативного запроса Telegram Mini App для текущего пользователя."""

    model_config = ConfigDict(extra="forbid")

    status: Literal["allowed", "cancelled", "unsupported"]


class TelegramWriteAccessResponse(BaseModel):
    telegram_write_access: bool


def _format_referral_rate(rate: Decimal) -> str:
    return str(normalize_aex_rate(rate))


def _format_referral_rate_percent(rate: Decimal) -> str:
    return str(rate_to_percent(rate))


def _resolve_aex_balance(user) -> str:
    wallet = user.__dict__.get("aex_wallet")
    if wallet is None:
        return "0"
    return str(wallet.balance_available)


def build_user_out(
    user,
    *,
    referral_rate: Decimal | None = None,
    attribution: dict[str, object] | None = None,
    referred_by: int | None = None,
) -> UserOut:
    from app.schemas.city import build_city_out

    trusted_contact = build_trusted_contact(user)
    effective_referral_rate = referral_rate
    if effective_referral_rate is None:
        personal_rate = user.__dict__.get("aex_personal_rate")
        effective_referral_rate = (
            personal_rate.rate if personal_rate is not None else DEFAULT_ATXG_RATE
        )
    aex_balance = _resolve_aex_balance(user)

    return UserOut(
        id=user.id,
        telegram_id=user.telegram_id,
        username=user.username,
        phone=user.phone,
        first_name=user.first_name,
        last_name=user.last_name,
        language_code=user.language_code,
        language_code_app=user.language_code_app or "ru",
        photo_url=user.photo_url,
        is_bot=user.is_bot,
        role=normalize_user_role(user.role),
        role_name=get_role_title(user.role),
        is_premium=user.is_premium,
        telegram_write_access=user.telegram_write_access,
        city_id=user.city_id,
        city=build_city_out(user.city) if user.city else None,
        trusted_contact=trusted_contact.contact,
        trusted_contact_source=trusted_contact.source,
        trusted_contact_ready=trusted_contact.ready,
        referral_code=getattr(user, "referral_code", None),
        referred_by=referred_by,
        referral_rate=_format_referral_rate(effective_referral_rate),
        referral_rate_percent=_format_referral_rate_percent(effective_referral_rate),
        aex_balance=aex_balance,
        balance=aex_balance,
        attribution=UserAttributionOut(**attribution) if attribution is not None else None,
        navigation=get_role_navigation(user.role),
        createdAt=user.createdAt,
        updatedAt=user.updatedAt,
    )
