"""Репозиторий пользователей."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select

from app.models.user import User
from app.repositories.base import BaseRepository


class UserRepository(BaseRepository[User]):
    model = User

    async def find_or_create(self, tg_id: int, **defaults: object) -> tuple[User, bool]:
        user = await self.session.get(User, tg_id)
        if user:
            return user, False
        user = User(id=tg_id, **defaults)
        self.session.add(user)
        await self.session.flush()
        await self.session.refresh(user)
        return user, True

    async def set_role(self, user_id: int, role: int) -> User | None:
        user = await self.session.get(User, user_id)
        if user:
            user.role = role
            await self.session.flush()
        return user

    async def get_users_interval(self, date_from: datetime, date_to: datetime) -> list[User]:
        result = await self.session.execute(
            select(User).where(User.createdAt >= date_from, User.createdAt <= date_to)
        )
        return list(result.scalars().all())
