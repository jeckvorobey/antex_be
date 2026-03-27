"""Репозиторий надбавки к курсу."""

from __future__ import annotations

from sqlalchemy import select

from app.models.allowance import Allowance
from app.repositories.base import BaseRepository


class AllowanceRepository(BaseRepository[Allowance]):
    model = Allowance

    async def get_value(self) -> float:
        result = await self.session.execute(select(Allowance).limit(1))
        allowance = result.scalar_one_or_none()
        return allowance.value if allowance else 0.02

    async def update_value(self, value: float) -> Allowance:
        result = await self.session.execute(select(Allowance).limit(1))
        allowance = result.scalar_one_or_none()
        if allowance:
            allowance.value = value
        else:
            allowance = Allowance(value=value)
            self.session.add(allowance)
        await self.session.flush()
        return allowance
