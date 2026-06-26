"""Репозитории AEX."""

from __future__ import annotations

from decimal import Decimal
from typing import ClassVar

from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.models.aex import AexLedgerEntry, AexPartnerRate, AexPersonalRate, AexRate, AexWallet
from app.repositories.base import BaseRepository


class AexWalletRepository(BaseRepository[AexWallet]):
    """Репозиторий кошельков AEX."""

    model = AexWallet

    async def get_by_user_id(self, user_id: int) -> AexWallet | None:
        result = await self.session.execute(select(AexWallet).where(AexWallet.user_id == user_id))
        return result.scalar_one_or_none()

    async def get_or_create(self, user_id: int) -> AexWallet:
        """Получить или создать кошелёк для пользователя."""
        wallet = await self.get_by_user_id(user_id)
        if wallet is None:
            wallet = await self.create(
                user_id=user_id,
                balance_available=Decimal("0"),
                balance_reserved=Decimal("0"),
            )
        return wallet

    async def get_all_with_users(
        self,
        *,
        limit: int | None = None,
        offset: int | None = None,
        search: str | None = None,
    ) -> tuple[list[AexWallet], int]:
        statement = select(AexWallet).options(selectinload(AexWallet.user)).join(AexWallet.user)
        count_statement = select(func.count(AexWallet.id)).join(AexWallet.user)
        if search:
            pattern = f"%{search}%"
            from app.models.user import User

            conditions = [User.username.ilike(pattern), User.first_name.ilike(pattern)]
            if search.isdigit():
                conditions.extend([User.id == int(search), AexWallet.user_id == int(search)])
            from sqlalchemy import or_

            statement = statement.where(or_(*conditions))
            count_statement = count_statement.where(or_(*conditions))
        statement = statement.order_by(AexWallet.id)
        if offset is not None:
            statement = statement.offset(offset)
        if limit is not None:
            statement = statement.limit(limit)
        result = await self.session.execute(statement)
        total_result = await self.session.execute(count_statement)
        return list(result.scalars().all()), total_result.scalar_one()


class AexLedgerEntryRepository(BaseRepository[AexLedgerEntry]):
    """Репозиторий записей журнала AEX."""

    model = AexLedgerEntry
    _default_order: ClassVar = AexLedgerEntry.id.desc()

    async def get_by_wallet(
        self,
        wallet_id: int,
        *,
        limit: int = 50,
        offset: int = 0,
    ) -> list[AexLedgerEntry]:
        result = await self.session.execute(
            select(AexLedgerEntry)
            .where(AexLedgerEntry.wallet_id == wallet_id)
            .order_by(self._default_order)
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())

    async def get_by_wallet_cursor(
        self,
        wallet_id: int,
        *,
        limit: int = 50,
        cursor: int | None = None,
    ) -> list[AexLedgerEntry]:
        """Cursor-based pagination: возвращает записи после cursor (DESC)."""
        query = (
            select(AexLedgerEntry)
            .where(AexLedgerEntry.wallet_id == wallet_id)
            .order_by(self._default_order)
            .limit(limit + 1)  # Fetch one extra to detect has_more
        )
        if cursor is not None:
            query = query.where(AexLedgerEntry.id < cursor)
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def count_by_wallet(self, wallet_id: int) -> int:
        from sqlalchemy import func

        result = await self.session.execute(
            select(func.count(AexLedgerEntry.id)).where(AexLedgerEntry.wallet_id == wallet_id)
        )
        return result.scalar_one()

    async def get_all_paginated(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
        user_id: int | None = None,
        entry_type: str | None = None,
        date_from=None,
        date_to=None,
    ) -> list[AexLedgerEntry]:
        statement = (
            select(AexLedgerEntry)
            .options(selectinload(AexLedgerEntry.wallet).selectinload(AexWallet.user))
            .join(AexLedgerEntry.wallet)
        )
        if user_id is not None:
            statement = statement.where(AexWallet.user_id == user_id)
        if entry_type is not None:
            statement = statement.where(AexLedgerEntry.entry_type == entry_type)
        if date_from is not None:
            statement = statement.where(AexLedgerEntry.createdAt >= date_from)
        if date_to is not None:
            statement = statement.where(AexLedgerEntry.createdAt <= date_to)
        result = await self.session.execute(
            statement.order_by(self._default_order).limit(limit).offset(offset)
        )
        return list(result.scalars().all())

    async def count_all(
        self,
        *,
        user_id: int | None = None,
        entry_type: str | None = None,
        date_from=None,
        date_to=None,
    ) -> int:
        statement = select(func.count(AexLedgerEntry.id)).join(AexLedgerEntry.wallet)
        if user_id is not None:
            statement = statement.where(AexWallet.user_id == user_id)
        if entry_type is not None:
            statement = statement.where(AexLedgerEntry.entry_type == entry_type)
        if date_from is not None:
            statement = statement.where(AexLedgerEntry.createdAt >= date_from)
        if date_to is not None:
            statement = statement.where(AexLedgerEntry.createdAt <= date_to)
        result = await self.session.execute(statement)
        return result.scalar_one()


class AexRateRepository(BaseRepository[AexRate]):
    """Репозиторий глобальных ставок AEX."""

    model = AexRate

    async def get_current(self) -> AexRate | None:
        result = await self.session.execute(select(AexRate).order_by(AexRate.id.desc()).limit(1))
        return result.scalar_one_or_none()


class AexPersonalRateRepository(BaseRepository[AexPersonalRate]):
    """Репозиторий персональных ставок AEX."""

    model = AexPersonalRate

    async def get_by_user_id(self, user_id: int) -> AexPersonalRate | None:
        result = await self.session.execute(
            select(AexPersonalRate).where(AexPersonalRate.user_id == user_id)
        )
        return result.scalar_one_or_none()

    async def get_all_with_users(
        self,
        *,
        limit: int | None = None,
        offset: int | None = None,
    ) -> tuple[list[AexPersonalRate], int]:
        statement = (
            select(AexPersonalRate)
            .options(selectinload(AexPersonalRate.user))
            .order_by(AexPersonalRate.id)
        )
        if offset is not None:
            statement = statement.offset(offset)
        if limit is not None:
            statement = statement.limit(limit)
        result = await self.session.execute(statement)
        total_result = await self.session.execute(select(func.count(AexPersonalRate.id)))
        return list(result.scalars().all()), total_result.scalar_one()


class AexPartnerRateRepository(BaseRepository[AexPartnerRate]):
    """Репозиторий партнёрских ставок AEX."""

    model = AexPartnerRate

    async def get_by_user_id(self, user_id: int) -> AexPartnerRate | None:
        result = await self.session.execute(
            select(AexPartnerRate).where(AexPartnerRate.user_id == user_id)
        )
        return result.scalar_one_or_none()

    async def get_all_with_users(
        self,
        *,
        limit: int | None = None,
        offset: int | None = None,
    ) -> tuple[list[AexPartnerRate], int]:
        statement = (
            select(AexPartnerRate)
            .options(selectinload(AexPartnerRate.user))
            .order_by(AexPartnerRate.id)
        )
        if offset is not None:
            statement = statement.offset(offset)
        if limit is not None:
            statement = statement.limit(limit)
        result = await self.session.execute(statement)
        total_result = await self.session.execute(select(func.count(AexPartnerRate.id)))
        return list(result.scalars().all()), total_result.scalar_one()
