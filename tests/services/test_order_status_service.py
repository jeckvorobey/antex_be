from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.enums.order import OrderStatus
from app.repositories import aex as aex_repositories
from app.services import aex as aex_service_module
from app.services import order_status
from app.services.order_status import update_order_status


@pytest.mark.asyncio
async def test_update_order_status_persists_and_notifies(monkeypatch) -> None:
    initial_order = SimpleNamespace(id=5, status=int(OrderStatus.CREATED))
    updated_order = SimpleNamespace(id=5, status=int(OrderStatus.PROCESSING))
    hydrated_order = SimpleNamespace(id=5, status=int(OrderStatus.PROCESSING))
    commit_mock = AsyncMock()
    first_get_done = False

    class _FakeRepo:
        def __init__(self, db) -> None:
            self.db = db

        async def get_one(self, order_id: int):
            nonlocal first_get_done
            assert order_id == 5
            if not first_get_done:
                first_get_done = True
                return initial_order
            return hydrated_order

        async def update_status(self, order_id: int, status: int):
            assert order_id == 5
            assert status == int(OrderStatus.PROCESSING)
            return updated_order

    db = SimpleNamespace(commit=commit_mock, rollback=AsyncMock())
    notify_mock = AsyncMock()
    manager = SimpleNamespace(telegram_id=700001, username="manager")

    class _FakeUserRepo:
        def __init__(self, db) -> None:
            self.db = db

        async def get_manager(self):
            return manager

    monkeypatch.setattr(order_status, "OrderRepository", _FakeRepo)
    monkeypatch.setattr(order_status, "UserRepository", _FakeUserRepo)
    monkeypatch.setattr(order_status, "notify_order_status_changed", notify_mock)

    updated = await update_order_status(
        db,
        order_id=5,
        status=OrderStatus.PROCESSING,
    )

    assert updated is hydrated_order
    assert commit_mock.await_count == 2
    notify_mock.assert_awaited_once_with(
        hydrated_order,
        manager_chat_url="https://t.me/manager",
    )


@pytest.mark.asyncio
async def test_update_order_status_keeps_success_when_notification_fails(monkeypatch) -> None:
    initial_order = SimpleNamespace(id=5, status=int(OrderStatus.CREATED))
    updated_order = SimpleNamespace(id=5, status=int(OrderStatus.PROCESSING))
    hydrated_order = SimpleNamespace(id=5, status=int(OrderStatus.PROCESSING))
    commit_mock = AsyncMock()
    rollback_mock = AsyncMock()
    first_get_done = False

    class _FakeRepo:
        def __init__(self, db) -> None:
            self.db = db

        async def get_one(self, order_id: int):
            nonlocal first_get_done
            assert order_id == 5
            if not first_get_done:
                first_get_done = True
                return initial_order
            return hydrated_order

        async def update_status(self, order_id: int, status: int):
            assert order_id == 5
            assert status == int(OrderStatus.PROCESSING)
            return updated_order

    db = SimpleNamespace(commit=commit_mock, rollback=rollback_mock)
    notify_mock = AsyncMock(side_effect=RuntimeError("proxy down"))
    manager = SimpleNamespace(telegram_id=700001, username="manager")

    class _FakeUserRepo:
        def __init__(self, db) -> None:
            self.db = db

        async def get_manager(self):
            return manager

    monkeypatch.setattr(order_status, "OrderRepository", _FakeRepo)
    monkeypatch.setattr(order_status, "UserRepository", _FakeUserRepo)
    monkeypatch.setattr(order_status, "notify_order_status_changed", notify_mock)

    updated = await update_order_status(
        db,
        order_id=5,
        status=OrderStatus.PROCESSING,
    )

    assert updated is hydrated_order
    assert commit_mock.await_count == 1
    rollback_mock.assert_awaited_once()
    notify_mock.assert_awaited_once_with(
        hydrated_order,
        manager_chat_url="https://t.me/manager",
    )


@pytest.mark.asyncio
async def test_update_order_status_sends_referral_reversal_notification(monkeypatch) -> None:
    initial_order = SimpleNamespace(id=5, status=int(OrderStatus.PROCESSING))
    updated_order = SimpleNamespace(id=5, status=int(OrderStatus.CANCELLED))
    hydrated_order = SimpleNamespace(id=5, status=int(OrderStatus.CANCELLED))
    referral_entry = SimpleNamespace(wallet_id=77, amount=Decimal("12.345"))
    wallet = SimpleNamespace(user_id=77, balance_available=Decimal("100"))
    commit_mock = AsyncMock()
    rollback_mock = AsyncMock()
    first_get_done = False
    execute_mock = AsyncMock(
        return_value=SimpleNamespace(scalar_one_or_none=lambda: referral_entry)
    )
    referral_notify_mock = AsyncMock()
    status_notify_mock = AsyncMock()
    manager = SimpleNamespace(telegram_id=700001, username="manager")
    reversal_debit = AsyncMock()

    class _FakeRepo:
        def __init__(self, db) -> None:
            self.db = db

        async def get_one(self, order_id: int):
            nonlocal first_get_done
            assert order_id == 5
            if not first_get_done:
                first_get_done = True
                return initial_order
            return hydrated_order

        async def update_status(self, order_id: int, status: int):
            assert order_id == 5
            assert status == int(OrderStatus.CANCELLED)
            return updated_order

    class _FakeUserRepo:
        def __init__(self, db) -> None:
            self.db = db

        async def get_manager(self):
            return manager

    class _FakeWalletRepo:
        def __init__(self, db) -> None:
            self.db = db

        async def get_by_id(self, wallet_id: int):
            assert wallet_id == referral_entry.wallet_id
            return wallet

    class _FakeAexService:
        def __init__(self) -> None:
            self.debit = reversal_debit

    db = SimpleNamespace(commit=commit_mock, rollback=rollback_mock, execute=execute_mock)

    monkeypatch.setattr(order_status, "OrderRepository", _FakeRepo)
    monkeypatch.setattr(order_status, "UserRepository", _FakeUserRepo)
    monkeypatch.setattr(order_status, "_notify_referral_reversal", referral_notify_mock)
    monkeypatch.setattr(order_status, "notify_order_status_changed", status_notify_mock)
    monkeypatch.setattr(aex_repositories, "AexWalletRepository", _FakeWalletRepo)
    monkeypatch.setattr(aex_service_module, "AexService", _FakeAexService)

    updated = await update_order_status(
        db,
        order_id=5,
        status=OrderStatus.CANCELLED,
    )

    assert updated is hydrated_order
    assert commit_mock.await_count == 3
    reversal_debit.assert_awaited_once_with(
        db,
        77,
        Decimal("12.345"),
        reference_type="referral_reversal",
        reference_id="5",
        description="Referral bonus reversal for cancelled order #5",
    )
    referral_notify_mock.assert_awaited_once_with(
        db,
        referrer_id=77,
        order_id=5,
        amount=Decimal("12.345"),
    )
    status_notify_mock.assert_awaited_once_with(
        hydrated_order,
        manager_chat_url="https://t.me/manager",
    )


@pytest.mark.asyncio
async def test_update_order_status_ignores_referral_reversal_notification_failure(
    monkeypatch,
) -> None:
    initial_order = SimpleNamespace(id=5, status=int(OrderStatus.PROCESSING))
    updated_order = SimpleNamespace(id=5, status=int(OrderStatus.CANCELLED))
    hydrated_order = SimpleNamespace(id=5, status=int(OrderStatus.CANCELLED))
    referral_entry = SimpleNamespace(wallet_id=77, amount=Decimal("12.345"))
    wallet = SimpleNamespace(user_id=77, balance_available=Decimal("100"))
    commit_mock = AsyncMock()
    rollback_mock = AsyncMock()
    first_get_done = False
    execute_mock = AsyncMock(
        return_value=SimpleNamespace(scalar_one_or_none=lambda: referral_entry)
    )
    referral_notify_mock = AsyncMock(side_effect=RuntimeError("proxy down"))
    status_notify_mock = AsyncMock()
    manager = SimpleNamespace(telegram_id=700001, username="manager")
    reversal_debit = AsyncMock()

    class _FakeRepo:
        def __init__(self, db) -> None:
            self.db = db

        async def get_one(self, order_id: int):
            nonlocal first_get_done
            assert order_id == 5
            if not first_get_done:
                first_get_done = True
                return initial_order
            return hydrated_order

        async def update_status(self, order_id: int, status: int):
            assert order_id == 5
            assert status == int(OrderStatus.CANCELLED)
            return updated_order

    class _FakeUserRepo:
        def __init__(self, db) -> None:
            self.db = db

        async def get_manager(self):
            return manager

    class _FakeWalletRepo:
        def __init__(self, db) -> None:
            self.db = db

        async def get_by_id(self, wallet_id: int):
            assert wallet_id == referral_entry.wallet_id
            return wallet

    class _FakeAexService:
        def __init__(self) -> None:
            self.debit = reversal_debit

    db = SimpleNamespace(commit=commit_mock, rollback=rollback_mock, execute=execute_mock)

    monkeypatch.setattr(order_status, "OrderRepository", _FakeRepo)
    monkeypatch.setattr(order_status, "UserRepository", _FakeUserRepo)
    monkeypatch.setattr(order_status, "_notify_referral_reversal", referral_notify_mock)
    monkeypatch.setattr(order_status, "notify_order_status_changed", status_notify_mock)
    monkeypatch.setattr(aex_repositories, "AexWalletRepository", _FakeWalletRepo)
    monkeypatch.setattr(aex_service_module, "AexService", _FakeAexService)

    updated = await update_order_status(
        db,
        order_id=5,
        status=OrderStatus.CANCELLED,
    )

    assert updated is hydrated_order
    assert commit_mock.await_count == 3
    reversal_debit.assert_awaited_once_with(
        db,
        77,
        Decimal("12.345"),
        reference_type="referral_reversal",
        reference_id="5",
        description="Referral bonus reversal for cancelled order #5",
    )
    referral_notify_mock.assert_awaited_once_with(
        db,
        referrer_id=77,
        order_id=5,
        amount=Decimal("12.345"),
    )
    status_notify_mock.assert_awaited_once_with(
        hydrated_order,
        manager_chat_url="https://t.me/manager",
    )
