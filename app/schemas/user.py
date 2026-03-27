"""Схемы пользователя."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class UserOut(BaseModel):
    id: int
    username: str | None
    first_name: str | None
    last_name: str | None
    language_code: str | None
    is_bot: bool
    chatId: int | None
    role: int
    is_premium: bool
    createdAt: datetime
    updatedAt: datetime

    model_config = {"from_attributes": True}


class UserUpdate(BaseModel):
    role: int | None = None
    chatId: int | None = None
