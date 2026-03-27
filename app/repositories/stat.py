"""Репозиторий статистики."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select

from app.models.stat import Stat
from app.repositories.base import BaseRepository


class StatRepository(BaseRepository[Stat]):
    model = Stat

    async def increment_click(self, user_id: int, trigger: str) -> Stat:
        result = await self.session.execute(
            select(Stat).where(Stat.UserId == user_id, Stat.trigger == trigger)
        )
        stat = result.scalar_one_or_none()
        if stat:
            stat.count += 1
        else:
            stat = Stat(UserId=user_id, count=1, trigger=trigger)
            self.session.add(stat)
        await self.session.flush()
        return stat

    async def get_stats_period(self, date_from: datetime, date_to: datetime) -> list[Stat]:
        result = await self.session.execute(
            select(Stat).where(Stat.createdAt >= date_from, Stat.createdAt <= date_to)
        )
        return list(result.scalars().all())
