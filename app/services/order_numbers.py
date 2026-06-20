"""Сервис генерации публичных номеров заявок."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.order_number_counter import OrderNumberCounter


class OrderNumberService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def next_public_number(self, *, created_at: datetime) -> str:
        localized = created_at.astimezone(UTC)
        year = localized.year
        month = localized.month

        result = await self.session.execute(
            select(OrderNumberCounter).where(OrderNumberCounter.year == year)
        )
        counter = result.scalar_one_or_none()
        if counter is None:
            counter = OrderNumberCounter(year=year, lastValue=0)
            self.session.add(counter)
            await self.session.flush()

        counter.lastValue += 1
        await self.session.flush()
        return f"{year:04d}{month:02d}{counter.lastValue:04d}"
