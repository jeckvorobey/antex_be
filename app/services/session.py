"""Сервис сессий бота (хранится в User.session как JSON)."""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User


async def get(db: AsyncSession, user_id: int) -> dict[str, Any]:
    user = await db.get(User, user_id)
    if not user or not user.session:
        return {}
    try:
        return json.loads(user.session)
    except (json.JSONDecodeError, TypeError):
        return {}


async def save(db: AsyncSession, user_id: int, data: dict[str, Any]) -> None:
    user = await db.get(User, user_id)
    if user:
        user.session = json.dumps(data, ensure_ascii=False)
        await db.flush()


async def delete(db: AsyncSession, user_id: int) -> None:
    user = await db.get(User, user_id)
    if user:
        user.session = None
        await db.flush()
