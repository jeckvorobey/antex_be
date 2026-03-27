"""Репозиторий курсов валют."""

from __future__ import annotations

from sqlalchemy import delete, select

from app.models.rate import Rate
from app.repositories.base import BaseRepository


class RateRepository(BaseRepository[Rate]):
    model = Rate

    async def find_or_create(self, currency: str, price: float) -> tuple[Rate, bool]:
        result = await self.session.execute(select(Rate).where(Rate.currency == currency))
        rate = result.scalar_one_or_none()
        if rate:
            return rate, False
        rate = Rate(currency=currency, price=price)
        self.session.add(rate)
        await self.session.flush()
        return rate, True

    async def upsert(self, currency: str, price: float) -> Rate:
        result = await self.session.execute(select(Rate).where(Rate.currency == currency))
        rate = result.scalar_one_or_none()
        if rate:
            rate.price = price
        else:
            rate = Rate(currency=currency, price=price)
            self.session.add(rate)
        await self.session.flush()
        return rate

    async def destroy_all(self) -> None:
        await self.session.execute(delete(Rate))
        await self.session.flush()
