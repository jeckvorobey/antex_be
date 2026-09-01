"""Репозиторий заданий Telegram-синхронизации заявок."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import or_, select

from app.models.order_telegram_sync_task import OrderTelegramSyncTask
from app.repositories.base import BaseRepository


class OrderTelegramSyncTaskRepository(BaseRepository[OrderTelegramSyncTask]):
    model = OrderTelegramSyncTask

    async def enqueue(self, *, order_id: int, status: int, target: str) -> OrderTelegramSyncTask:
        existing = await self.session.scalar(
            select(OrderTelegramSyncTask).where(
                OrderTelegramSyncTask.OrderId == order_id,
                OrderTelegramSyncTask.status == status,
                OrderTelegramSyncTask.target == target,
            )
        )
        if existing is not None:
            return existing
        task = OrderTelegramSyncTask(
            OrderId=order_id,
            status=status,
            target=target,
            state="pending",
            nextAttemptAt=datetime.now(UTC),
        )
        self.session.add(task)
        await self.session.flush()
        return task

    async def claim_due(
        self,
        *,
        limit: int,
        lease_seconds: int,
    ) -> list[OrderTelegramSyncTask]:
        now = datetime.now(UTC)
        stale_before = now - timedelta(seconds=lease_seconds)
        result = await self.session.execute(
            select(OrderTelegramSyncTask)
            .where(
                or_(
                    (
                        OrderTelegramSyncTask.state.in_(("pending", "retry"))
                        & (OrderTelegramSyncTask.nextAttemptAt <= now)
                    ),
                    (
                        (OrderTelegramSyncTask.state == "processing")
                        & (OrderTelegramSyncTask.lockedAt <= stale_before)
                    ),
                )
            )
            .order_by(OrderTelegramSyncTask.nextAttemptAt, OrderTelegramSyncTask.id)
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        tasks = list(result.scalars().all())
        for task in tasks:
            task.state = "processing"
            task.lockedAt = now
        await self.session.flush()
        return tasks
