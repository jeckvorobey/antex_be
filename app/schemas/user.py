"""Схемы пользователя."""
# ruff: noqa: N815

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from app.enums.user import get_role_title
from app.schemas.auth import build_trusted_contact
from app.schemas.city import CityOut


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
    city_id: int | None
    city: CityOut | None = None
    trusted_contact: str | None
    trusted_contact_source: str | None
    trusted_contact_ready: bool
    createdAt: datetime
    updatedAt: datetime


class UserUpdate(BaseModel):
    role: int | None = None
    city_id: int | None = None


def build_user_out(user) -> UserOut:
    from app.schemas.city import build_city_out
    trusted_contact = build_trusted_contact(user)

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
        role=user.role,
        role_name=get_role_title(user.role),
        is_premium=user.is_premium,
        city_id=user.city_id,
        city=build_city_out(user.city) if user.city else None,
        trusted_contact=trusted_contact.contact,
        trusted_contact_source=trusted_contact.source,
        trusted_contact_ready=trusted_contact.ready,
        createdAt=user.createdAt,
        updatedAt=user.updatedAt,
    )
