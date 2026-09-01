from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from aiogram.exceptions import TelegramBadRequest
from sqlalchemy import func, select

from app.models.order_telegram_sync_task import OrderTelegramSyncTask
from app.repositories.order_telegram_sync_task import OrderTelegramSyncTaskRepository
from app.services import order_telegram_sync


@pytest.mark.asyncio
async def test_enqueue_deduplicates_same_order_status_and_target(db_session) -> None:
    repo = OrderTelegramSyncTaskRepository(db_session)

    first = await repo.enqueue(order_id=1, status=2, target="user")
    second = await repo.enqueue(order_id=1, status=2, target="user")
    await db_session.commit()

    count = await db_session.scalar(select(func.count(OrderTelegramSyncTask.id)))
    assert first.id == second.id
    assert count == 1


@pytest.mark.asyncio
async def test_stale_task_finishes_without_telegram_delivery(monkeypatch) -> None:
    task = SimpleNamespace(
        OrderId=5,
        status=1,
        target="manager",
        state="processing",
        lockedAt=datetime.now(UTC),
        deliveredAt=None,
        lastErrorCode=None,
        attemptCount=0,
    )
    current_order = SimpleNamespace(id=5, status=2)
    delivery = AsyncMock()

    class FakeOrderRepository:
        def __init__(self, db) -> None:
            del db

        async def get_one(self, order_id: int):
            assert order_id == 5
            return current_order

    monkeypatch.setattr(order_telegram_sync, "OrderRepository", FakeOrderRepository)
    monkeypatch.setattr(order_telegram_sync, "_deliver_manager", delivery)

    await order_telegram_sync.process_order_telegram_sync_task(SimpleNamespace(), task)

    assert task.state == "delivered"
    assert task.lastErrorCode == "stale_status"
    delivery.assert_not_awaited()


@pytest.mark.asyncio
async def test_missing_manager_message_link_is_permanent_failure(monkeypatch) -> None:
    task = SimpleNamespace(
        OrderId=5,
        status=2,
        target="manager",
        state="processing",
        lockedAt=datetime.now(UTC),
        deliveredAt=None,
        lastErrorCode=None,
        attemptCount=0,
        nextAttemptAt=datetime.now(UTC),
    )
    current_order = SimpleNamespace(
        id=5,
        status=2,
        managerNotificationChatId=None,
        managerNotificationMessageId=None,
    )

    class FakeOrderRepository:
        def __init__(self, db) -> None:
            del db

        async def get_one(self, order_id: int):
            return current_order

    monkeypatch.setattr(order_telegram_sync, "OrderRepository", FakeOrderRepository)

    await order_telegram_sync.process_order_telegram_sync_task(SimpleNamespace(), task)

    assert task.state == "failed"
    assert task.attemptCount == 1
    assert task.lastErrorCode == "message_link_missing"


@pytest.mark.asyncio
async def test_temporary_failure_schedules_exponential_retry(monkeypatch) -> None:
    task = SimpleNamespace(
        OrderId=5,
        status=2,
        target="manager",
        state="processing",
        lockedAt=datetime.now(UTC),
        deliveredAt=None,
        lastErrorCode=None,
        attemptCount=2,
        nextAttemptAt=datetime.now(UTC),
    )
    current_order = SimpleNamespace(id=5, status=2)

    class FakeOrderRepository:
        def __init__(self, db) -> None:
            del db

        async def get_one(self, order_id: int):
            return current_order

    monkeypatch.setattr(order_telegram_sync, "OrderRepository", FakeOrderRepository)
    monkeypatch.setattr(
        order_telegram_sync,
        "_deliver_manager",
        AsyncMock(return_value=(order_telegram_sync.SyncResult.RETRY, "telegram_timeout")),
    )
    before = datetime.now(UTC)

    await order_telegram_sync.process_order_telegram_sync_task(SimpleNamespace(), task)

    assert task.state == "retry"
    assert task.attemptCount == 3
    assert task.lastErrorCode == "telegram_timeout"
    assert task.nextAttemptAt >= before


@pytest.mark.asyncio
async def test_message_not_modified_is_delivered(monkeypatch) -> None:
    bot = SimpleNamespace(
        edit_message_text=AsyncMock(
            side_effect=TelegramBadRequest(
                method="editMessageText",
                message="message is not modified",
            )
        )
    )
    from app.telegram import bot as telegram_bot

    monkeypatch.setattr(telegram_bot, "bot", bot)
    monkeypatch.setattr(order_telegram_sync, "build_manager_status_text", lambda order: "current")
    monkeypatch.setattr(order_telegram_sync, "build_manager_status_markup", lambda order: None)
    order = SimpleNamespace(
        id=5,
        managerNotificationChatId=700001,
        managerNotificationMessageId=42,
    )

    result = await order_telegram_sync._deliver_manager(order)

    assert result == (order_telegram_sync.SyncResult.DELIVERED, None)
