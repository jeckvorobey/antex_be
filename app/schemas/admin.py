"""Схемы администратора."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class AdminLogin(BaseModel):
    username: str
    password: str


class AdminOut(BaseModel):
    id: int
    username: str
    createdAt: datetime
    updatedAt: datetime

    model_config = {"from_attributes": True}


class AdminTokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
