from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.enums.order import OrderStatus
from app.services import order_status
from app.services.order_status import update_order_status


@pytest.mark.asyncio
async def test_update_order_status_persists_and_notifies(monkeypatch) -> None:
    initial_order = SimpleNamespace(id=5, status=int(OrderStatus.CREATED))
    updated_order = SimpleNamespace(id=5, status=int(OrderStatus.PROCESSING))
    hydrated_order = SimpleNamespace(id=5, status=int(OrderStatus.PROCESSING))
    commit_mock = AsyncMock()

    class _FakeRepo:
        def __init__(self, db) -> None:
            self.db = db

        async def get_one(self, order_id: int):
            assert order_id == 5
            if commit_mock.await_count == 0:
                return initial_order
            return hydrated_order

        async def update_status(self, order_id: int, status: int):
            assert order_id == 5
            assert status == int(OrderStatus.PROCESSING)
            return updated_order

    db = SimpleNamespace(commit=commit_mock)
    notify_mock = AsyncMock()

    monkeypatch.setattr(order_status, "OrderRepository", _FakeRepo)
    monkeypatch.setattr(order_status, "notify_order_status_changed", notify_mock)

    updated = await update_order_status(
        db,
        order_id=5,
        status=OrderStatus.PROCESSING,
    )

    assert updated is hydrated_order
    assert commit_mock.await_count == 2
    notify_mock.assert_awaited_once_with(hydrated_order)
