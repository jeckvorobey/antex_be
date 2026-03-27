"""Репозиторий лимитов банков."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.models.limitation import Limitation
from app.repositories.base import BaseRepository


class LimitationRepository(BaseRepository[Limitation]):
    model = Limitation

    async def get_all_with_bank(self) -> list[Limitation]:
        result = await self.session.execute(
            select(Limitation).options(selectinload(Limitation.bank))
        )
        return list(result.scalars().all())

    async def get_by_bank(self, bank_id: int) -> Limitation | None:
        result = await self.session.execute(
            select(Limitation).where(Limitation.BankId == bank_id)
        )
        return result.scalar_one_or_none()

    async def set_limits(self, bank_id: int, amount: int, base_amount: int) -> Limitation | None:
        lim = await self.get_by_bank(bank_id)
        if lim:
            lim.amount = amount
            lim.baseAmount = base_amount
            await self.session.flush()
        return lim

    async def update_amount(self, bank_id: int, delta: int) -> Limitation | None:
        lim = await self.get_by_bank(bank_id)
        if lim:
            lim.amount = max(0, lim.amount + delta)
            await self.session.flush()
        return lim

    async def add_bank(self, bank_id: int, amount: int = 50000) -> Limitation:
        lim = Limitation(BankId=bank_id, amount=amount, baseAmount=amount)
        self.session.add(lim)
        await self.session.flush()
        return lim

    async def delete_bank(self, bank_id: int) -> None:
        lim = await self.get_by_bank(bank_id)
        if lim:
            await self.session.delete(lim)
            await self.session.flush()
