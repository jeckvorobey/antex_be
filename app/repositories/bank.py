"""Репозиторий банков."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.models.bank import Bank
from app.repositories.base import BaseRepository


class BankRepository(BaseRepository[Bank]):
    model = Bank

    async def bulk_create(self, banks: list[dict]) -> list[Bank]:
        objs = [Bank(**data) for data in banks]
        self.session.add_all(objs)
        await self.session.flush()
        return objs

    async def get_all_paginated(self, offset: int = 0, limit: int = 50) -> list[Bank]:
        result = await self.session.execute(
            select(Bank).offset(offset).limit(limit)
        )
        return list(result.scalars().all())

    async def get_by_code(self, code: str) -> Bank | None:
        result = await self.session.execute(select(Bank).where(Bank.code == code))
        return result.scalar_one_or_none()

    async def get_with_limitation(self, bank_id: int) -> Bank | None:
        result = await self.session.execute(
            select(Bank)
            .where(Bank.id == bank_id)
            .options(selectinload(Bank.limitation))
        )
        return result.scalar_one_or_none()
