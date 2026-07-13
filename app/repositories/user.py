"""Репозиторий пользователей."""

from __future__ import annotations

from datetime import datetime
from typing import ClassVar

from sqlalchemy import func, or_, select
from sqlalchemy.orm import selectinload

from app.enums.user import LEGACY_ADMIN_ROLE, UserRole
from app.models.user import User
from app.repositories.base import BaseRepository


class UserRepository(BaseRepository[User]):
    model = User
    _nullable_refresh_fields: ClassVar[set[str]] = {"photo_url"}

    @staticmethod
    def _admin_user_options():
        return (
            selectinload(User.city),
            selectinload(User.aex_wallet),
            selectinload(User.aex_personal_rate),
        )

    async def get_by_telegram_id(self, tg_id: int) -> User | None:
        result = await self.session.execute(
            select(User).where(User.telegram_id == tg_id).options(*self._admin_user_options())
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
            select(User).where(User.id == user_id).options(*self._admin_user_options())
        )
        return result.scalar_one_or_none()

    async def list_all(self) -> list[User]:
        result = await self.session.execute(
            select(User).options(*self._admin_user_options()).order_by(User.id)
        )
        return list(result.scalars().all())


    async def search(self, query: str | None) -> list[User]:
        statement = select(User).options(*self._admin_user_options()).order_by(User.id)
        if query:
            pattern = f"%{query}%"
            conditions = [
                User.username.ilike(pattern),
                User.first_name.ilike(pattern),
                User.last_name.ilike(pattern),
                User.phone.ilike(pattern),
            ]

            if query.isdigit():
                conditions.append(User.id == int(query))
                conditions.append(User.telegram_id == int(query))

            statement = statement.where(or_(*conditions))

        result = await self.session.execute(statement)
        return list(result.scalars().all())

    async def search_paginated(
        self,
        query: str | None,
        *,
        limit: int,
        offset: int,
    ) -> tuple[list[User], int]:
        statement = select(User)
        count_statement = select(func.count(User.id))
        if query:
            pattern = f"%{query}%"
            conditions = [
                User.username.ilike(pattern),
                User.first_name.ilike(pattern),
                User.last_name.ilike(pattern),
                User.phone.ilike(pattern),
            ]
            if query.isdigit():
                conditions.append(User.id == int(query))
                conditions.append(User.telegram_id == int(query))
            statement = statement.where(or_(*conditions))
            count_statement = count_statement.where(or_(*conditions))

        result = await self.session.execute(
            statement
            .options(*self._admin_user_options())
            .order_by(User.id)
            .limit(limit)
            .offset(offset)
        )
        total_result = await self.session.execute(count_statement)
        return list(result.scalars().all()), total_result.scalar_one()

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

    async def get_by_referral_code(self, code: str) -> User | None:
        result = await self.session.execute(select(User).where(User.referral_code == code))
        return result.scalar_one_or_none()

    async def get_referrals(self, user_id: int) -> list[User]:
        result = await self.session.execute(
            select(User)
            .where(User.referred_by == user_id)
            .options(selectinload(User.city))
            .order_by(User.id)
        )
        return list(result.scalars().all())

    async def get_referrals_paginated(
        self,
        user_id: int,
        *,
        limit: int,
        offset: int,
    ) -> tuple[list[User], int]:
        statement = (
            select(User)
            .where(User.referred_by == user_id)
            .options(selectinload(User.city))
            .order_by(User.id)
            .limit(limit)
            .offset(offset)
        )
        count_statement = select(func.count(User.id)).where(User.referred_by == user_id)

        result = await self.session.execute(statement)
        total_result = await self.session.execute(count_statement)
        return list(result.scalars().all()), total_result.scalar_one()

    async def count_referrals(self, user_id: int) -> int:
        result = await self.session.execute(
            select(func.count(User.id)).where(User.referred_by == user_id)
        )
        return result.scalar_one()

    async def get_users_without_referral_code(self) -> list[User]:
        """Получить всех пользователей без реферального кода."""
        result = await self.session.execute(
            select(User).where(User.referral_code.is_(None)).order_by(User.id)
        )
        return list(result.scalars().all())
