"""Схемы пользователя."""
# ruff: noqa: N815

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from app.enums.user import get_role_title
from app.schemas.city import CityOut


class UserOut(BaseModel):
    id: int
    telegram_id: int | None
    username: str | None
    first_name: str | None
    last_name: str | None
    language_code: str | None
    language_code_app: str
    is_bot: bool
    role: int
    role_name: str
    is_premium: bool
    city_id: int | None
    city: CityOut | None = None
    createdAt: datetime
    updatedAt: datetime


class UserUpdate(BaseModel):
    role: int | None = None
    city_id: int | None = None


def build_user_out(user) -> UserOut:
    from app.schemas.city import build_city_out

    return UserOut(
        id=user.id,
        telegram_id=user.telegram_id,
        username=user.username,
        first_name=user.first_name,
        last_name=user.last_name,
        language_code=user.language_code,
        language_code_app=user.language_code_app or "ru",
        is_bot=user.is_bot,
        role=user.role,
        role_name=get_role_title(user.role),
        is_premium=user.is_premium,
        city_id=user.city_id,
        city=build_city_out(user.city) if user.city else None,
        createdAt=user.createdAt,
        updatedAt=user.updatedAt,
    )
