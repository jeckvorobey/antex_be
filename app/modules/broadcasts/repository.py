"""Репозиторий рассылок."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select

from app.modules.broadcasts.models import Broadcast
from app.repositories.base import BaseRepository


class BroadcastRepository(BaseRepository[Broadcast]):
    model = Broadcast

    async def has_active_broadcast(self) -> bool:
        result = await self.session.execute(
            select(Broadcast.id).where(Broadcast.status.in_(("pending", "running"))).limit(1)
        )
        return result.scalar_one_or_none() is not None

    async def get_active(self) -> list[Broadcast]:
        result = await self.session.execute(
            select(Broadcast)
            .where(Broadcast.status.in_(("pending", "running")))
            .order_by(Broadcast.id.asc())
        )
        return list(result.scalars().all())

    async def get_recent(self, *, limit: int = 50, offset: int = 0) -> list[Broadcast]:
        result = await self.session.execute(
            select(Broadcast)
            .order_by(Broadcast.createdAt.desc(), Broadcast.id.desc())
            .offset(offset)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def mark_running(self, broadcast: Broadcast, *, total_count: int) -> Broadcast:
        broadcast.status = "running"
        broadcast.total_count = total_count
        broadcast.started_at = datetime.now(UTC)
        return await self.update(broadcast)

    async def update_counts(
        self,
        broadcast: Broadcast,
        *,
        success_count: int,
        failed_count: int,
    ) -> Broadcast:
        broadcast.success_count = success_count
        broadcast.failed_count = failed_count
        return await self.update(broadcast)

    async def mark_completed(
        self,
        broadcast: Broadcast,
        *,
        success_count: int,
        failed_count: int,
    ) -> Broadcast:
        broadcast.status = "completed"
        broadcast.success_count = success_count
        broadcast.failed_count = failed_count
        broadcast.finished_at = datetime.now(UTC)
        broadcast.last_error = None
        return await self.update(broadcast)

    async def mark_failed(
        self,
        broadcast: Broadcast,
        *,
        success_count: int,
        failed_count: int,
        error_message: str,
    ) -> Broadcast:
        broadcast.status = "failed"
        broadcast.success_count = success_count
        broadcast.failed_count = failed_count
        broadcast.finished_at = datetime.now(UTC)
        broadcast.last_error = error_message
        return await self.update(broadcast)
