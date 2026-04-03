"""Репозиторий пользователей."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.enums.user import UserRole
from app.models.user import User
from app.repositories.base import BaseRepository


class UserRepository(BaseRepository[User]):
    model = User

    async def find_or_create(self, tg_id: int, **defaults: object) -> tuple[User, bool]:
        result = await self.session.execute(select(User).where(User.telegram_id == tg_id))
        user = result.scalar_one_or_none()
        if user:
            for field, value in defaults.items():
                if value is not None and hasattr(User, field):
                    setattr(user, field, value)
            if user.language_code_app is None:
                user.language_code_app = "ru"
            await self.session.flush()
            await self.session.refresh(user)
            return user, False
        user = User(telegram_id=tg_id, **defaults)
        self.session.add(user)
        await self.session.flush()
        await self.session.refresh(user)
        return user, True

    async def get_one(self, user_id: int) -> User | None:
        result = await self.session.execute(
            select(User).where(User.id == user_id).options(selectinload(User.city))
        )
        return result.scalar_one_or_none()

    async def list_all(self) -> list[User]:
        result = await self.session.execute(
            select(User).options(selectinload(User.city)).order_by(User.id)
        )
        return list(result.scalars().all())

    async def set_role(self, user_id: int, role: int) -> User | None:
        user = await self.session.get(User, user_id)
        if user:
            user.role = role
            await self.session.flush()
        return user

    async def get_manager_by_city(self, city_id: int) -> User | None:
        result = await self.session.execute(
            select(User).where(User.city_id == city_id, User.role == int(UserRole.MANAGER))
        )
        return result.scalar_one_or_none()

    async def get_users_interval(self, date_from: datetime, date_to: datetime) -> list[User]:
        result = await self.session.execute(
            select(User).where(User.createdAt >= date_from, User.createdAt <= date_to)
        )
        return list(result.scalars().all())
