"""Схемы аутентификации."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class TelegramAuthRequest(BaseModel):
    init_data: str = Field(max_length=16 * 1024)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    is_new_user: bool
    telegram_write_access: bool


class TrustedContactResponse(BaseModel):
    ready: bool
    contact: str | None
    source: Literal["username", "phone"] | None
    phone: str | None
    username: str | None


class TrustedContactUpdate(BaseModel):
    phone: str = Field(min_length=5, max_length=32)


def build_trusted_contact(user) -> TrustedContactResponse:
    username = user.username.strip() if isinstance(user.username, str) else None
    phone = user.phone.strip() if isinstance(user.phone, str) else None

    if username:
        return TrustedContactResponse(
            ready=True,
            contact=username,
            source="username",
            phone=phone,
            username=username,
        )

    if phone:
        return TrustedContactResponse(
            ready=True,
            contact=phone,
            source="phone",
            phone=phone,
            username=None,
        )

    return TrustedContactResponse(
        ready=False,
        contact=None,
        source=None,
        phone=None,
        username=None,
    )
