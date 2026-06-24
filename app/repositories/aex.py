"""Репозитории AEX."""

from __future__ import annotations

from decimal import Decimal
from typing import ClassVar

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.models.aex import AexLedgerEntry, AexPersonalRate, AexRate, AexWallet
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

    async def get_all_with_users(self) -> list[AexWallet]:
        result = await self.session.execute(
            select(AexWallet).options(selectinload(AexWallet.user)).order_by(AexWallet.id)
        )
        return list(result.scalars().all())


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
    ) -> list[AexLedgerEntry]:
        result = await self.session.execute(
            select(AexLedgerEntry)
            .options(selectinload(AexLedgerEntry.wallet))
            .order_by(self._default_order)
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())


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

    async def get_all_with_users(self) -> list[AexPersonalRate]:
        result = await self.session.execute(
            select(AexPersonalRate)
            .options(selectinload(AexPersonalRate.user))
            .order_by(AexPersonalRate.id)
        )
        return list(result.scalars().all())
