"""Сервис пользователей для бота (check/find_or_create)."""

from __future__ import annotations

from aiogram.types import User as TgUser
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.repositories.user import UserRepository


async def check_user(db: AsyncSession, tg_user: TgUser) -> tuple[User, bool]:
    repo = UserRepository(db)
    user, created = await repo.find_or_create(
        tg_user.id,
        username=tg_user.username,
        first_name=tg_user.first_name,
        last_name=tg_user.last_name,
        language_code=tg_user.language_code,
        is_bot=tg_user.is_bot,
        is_premium=getattr(tg_user, "is_premium", False) or False,
        chatId=tg_user.id,
    )
    user.username = tg_user.username
    user.first_name = tg_user.first_name
    user.last_name = tg_user.last_name
    user.language_code = tg_user.language_code
    user.is_bot = tg_user.is_bot
    user.is_premium = getattr(tg_user, "is_premium", False) or False
    user.chatId = tg_user.id
    return user, created
