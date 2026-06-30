"""Репозиторий пользователей."""

from __future__ import annotations

from datetime import datetime
from typing import ClassVar

from sqlalchemy import or_, select
from sqlalchemy.orm import selectinload

from app.enums.user import LEGACY_ADMIN_ROLE, UserRole
from app.models.user import User
from app.repositories.base import BaseRepository


class UserRepository(BaseRepository[User]):
    model = User
    _nullable_refresh_fields: ClassVar[set[str]] = {"photo_url"}

    async def get_by_telegram_id(self, tg_id: int) -> User | None:
        result = await self.session.execute(
            select(User).where(User.telegram_id == tg_id).options(selectinload(User.city))
        )
        return result.scalar_one_or_none()

    async def find_or_create(self, tg_id: int, **defaults: object) -> tuple[User, bool]:
        result = await self.session.execute(select(User).where(User.telegram_id == tg_id))
        user = result.scalar_one_or_none()
        if user:
            for field, value in defaults.items():
                should_refresh = value is not None or field in self._nullable_refresh_fields
                if should_refresh and hasattr(User, field):
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


    async def search(self, query: str | None) -> list[User]:
        if not query:
            return await self.list_all()

        pattern = f"%{query}%"
        conditions = [
            User.username.ilike(pattern),
            User.first_name.ilike(pattern),
            User.last_name.ilike(pattern),
        ]

        if query.isdigit():
            conditions.append(User.id == int(query))
            conditions.append(User.telegram_id == int(query))

        result = await self.session.execute(
            select(User)
            .options(selectinload(User.city))
            .where(or_(*conditions))
            .order_by(User.id)
        )
        return list(result.scalars().all())

    async def set_role(self, user_id: int, role: int) -> User | None:
        user = await self.session.get(User, user_id)
        if user:
            user.role = role
            await self.session.flush()
        return user

    async def set_phone(self, user_id: int, phone: str) -> User | None:
        user = await self.session.get(User, user_id)
        if user:
            user.phone = phone
            await self.session.flush()
            await self.session.refresh(user)
        return user

    async def get_manager_by_city(self, city_id: int) -> User | None:
        result = await self.session.execute(
            select(User).where(
                User.city_id == city_id,
                User.role.in_([int(UserRole.MANAGER), LEGACY_ADMIN_ROLE]),
            )
        )
        return result.scalar_one_or_none()

    async def get_manager(self) -> User | None:
        result = await self.session.execute(
            select(User)
            .where(User.role.in_([int(UserRole.MANAGER), LEGACY_ADMIN_ROLE]))
            .order_by(User.id.asc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def get_users_interval(self, date_from: datetime, date_to: datetime) -> list[User]:
        result = await self.session.execute(
            select(User).where(User.createdAt >= date_from, User.createdAt <= date_to)
        )
        return list(result.scalars().all())
