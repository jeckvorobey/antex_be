"""Репозиторий банковских счетов."""

from __future__ import annotations

from sqlalchemy import select

from app.models.bank_account import BankAccount
from app.repositories.base import BaseRepository


class BankAccountRepository(BaseRepository[BankAccount]):
    model = BankAccount

    async def get_by_order(self, order_id: int) -> BankAccount | None:
        result = await self.session.execute(
            select(BankAccount).where(BankAccount.OrderId == order_id)
        )
        return result.scalar_one_or_none()

    async def get_by_bank(self, bank_id: int) -> list[BankAccount]:
        result = await self.session.execute(
            select(BankAccount).where(BankAccount.BankId == bank_id)
        )
        return list(result.scalars().all())
