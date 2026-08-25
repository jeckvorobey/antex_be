from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import ANY, AsyncMock

import pytest
from sqlalchemy.exc import SQLAlchemyError

from app.enums.order import OrderStatus
from app.repositories import aex as aex_repositories
from app.services import aex as aex_service_module
from app.services import order_status
from app.services import referral as referral_service_module
from app.services.order_status import update_order_status


@pytest.mark.parametrize(
    "delivery",
    [
        order_status.DeliveryOutcome.RICH,
        order_status.DeliveryOutcome.FALLBACK,
        order_status.DeliveryOutcome.FAILED,
    ],
)
@pytest.mark.asyncio
async def test_take_order_in_work_uses_single_manager_and_reports_delivery(
    monkeypatch: pytest.MonkeyPatch,
    delivery: order_status.DeliveryOutcome,
) -> None:
    current_order = SimpleNamespace(id=5, status=int(OrderStatus.CREATED))
    hydrated_order = SimpleNamespace(id=5, status=int(OrderStatus.PROCESSING))
    manager = SimpleNamespace(id=7, username="manager")
    handoff = AsyncMock(return_value=delivery)
    status_update = AsyncMock(return_value=hydrated_order)

    class _FakeOrderRepository:
        def __init__(self, db) -> None:
            self.db = db

        async def get_one(self, order_id: int):
            assert order_id == 5
            return current_order

    class _FakeUserRepository:
        def __init__(self, db) -> None:
            self.db = db

        async def get_manager(self):
            return manager

    monkeypatch.setattr(order_status, "OrderRepository", _FakeOrderRepository)
    monkeypatch.setattr(order_status, "UserRepository", _FakeUserRepository)
    monkeypatch.setattr(order_status, "update_order_status", status_update)
    monkeypatch.setattr(order_status, "send_customer_handoff", handoff)

    result = await order_status.take_order_in_work(SimpleNamespace(), order_id=5)

    assert result.order is hydrated_order
    assert result.delivery == delivery
    status_update.assert_awaited_once_with(
        ANY,
        order_id=5,
        status=OrderStatus.PROCESSING,
        notify_user=False,
    )
    handoff.assert_awaited_once_with(hydrated_order, manager)


@pytest.mark.asyncio
async def test_take_order_in_work_persists_replacement_message_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    current_order = SimpleNamespace(id=5, status=int(OrderStatus.CREATED))
    hydrated_order = SimpleNamespace(
        id=5,
        status=int(OrderStatus.PROCESSING),
        userNotificationMessageId=None,
    )
    manager = SimpleNamespace(id=7, username="manager")
    commit = AsyncMock()
    db = SimpleNamespace(commit=commit)

    class _FakeOrderRepository:
        def __init__(self, db) -> None:
            self.db = db

        async def get_one(self, order_id: int):
            assert order_id == 5
            return current_order

    class _FakeUserRepository:
        def __init__(self, db) -> None:
            self.db = db

        async def get_manager(self):
            return manager

    async def handoff(order, assigned_manager):
        assert assigned_manager is manager
        order.userNotificationMessageId = 89
        return order_status.DeliveryOutcome.RICH

    monkeypatch.setattr(order_status, "OrderRepository", _FakeOrderRepository)
    monkeypatch.setattr(order_status, "UserRepository", _FakeUserRepository)
    monkeypatch.setattr(order_status, "update_order_status", AsyncMock(return_value=hydrated_order))
    monkeypatch.setattr(order_status, "send_customer_handoff", handoff)

    await order_status.take_order_in_work(db, order_id=5)

    commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_take_order_in_work_reconciles_inaccessible_customer_chat(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Сбрасывает локальный доступ после постоянной ошибки handoff-доставки."""
    current_order = SimpleNamespace(id=5, status=int(OrderStatus.CREATED))
    customer = SimpleNamespace(id=8, telegram_id=700002, telegram_write_access=True)
    hydrated_order = SimpleNamespace(
        id=5,
        status=int(OrderStatus.PROCESSING),
        user=customer,
        userNotificationMessageId=55,
    )
    db = SimpleNamespace(commit=AsyncMock(), rollback=AsyncMock())

    class _FakeOrderRepository:
        def __init__(self, session) -> None:
            self.session = session

        async def get_one(self, order_id: int):
            return current_order

    class _FakeUserRepository:
        def __init__(self, session) -> None:
            self.session = session

        async def get_manager(self):
            return SimpleNamespace(id=7, username="manager")

    monkeypatch.setattr(order_status, "OrderRepository", _FakeOrderRepository)
    monkeypatch.setattr(order_status, "UserRepository", _FakeUserRepository)
    monkeypatch.setattr(
        order_status,
        "update_order_status",
        AsyncMock(return_value=hydrated_order),
    )
    monkeypatch.setattr(
        order_status,
        "send_customer_handoff",
        AsyncMock(return_value=order_status.DeliveryOutcome.INACCESSIBLE),
    )

    await order_status.take_order_in_work(db, order_id=5)

    assert customer.telegram_write_access is False
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_take_order_in_work_keeps_delivery_when_message_id_commit_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    current_order = SimpleNamespace(id=5, status=int(OrderStatus.CREATED))
    hydrated_order = SimpleNamespace(
        id=5,
        status=int(OrderStatus.PROCESSING),
        userNotificationMessageId=None,
    )
    reloaded_order = SimpleNamespace(
        id=5,
        status=int(OrderStatus.PROCESSING),
        userNotificationMessageId=None,
    )
    manager = SimpleNamespace(id=7, username="manager")
    rollback = AsyncMock()
    db = SimpleNamespace(
        commit=AsyncMock(side_effect=SQLAlchemyError("tracking write unavailable")),
        rollback=rollback,
    )
    get_count = 0

    class _FakeOrderRepository:
        def __init__(self, db) -> None:
            self.db = db

        async def get_one(self, order_id: int):
            nonlocal get_count
            assert order_id == 5
            get_count += 1
            return current_order if get_count == 1 else reloaded_order

    class _FakeUserRepository:
        def __init__(self, db) -> None:
            self.db = db

        async def get_manager(self):
            return manager

    async def handoff(order, assigned_manager):
        order.userNotificationMessageId = 89
        return order_status.DeliveryOutcome.RICH

    monkeypatch.setattr(order_status, "OrderRepository", _FakeOrderRepository)
    monkeypatch.setattr(order_status, "UserRepository", _FakeUserRepository)
    monkeypatch.setattr(order_status, "update_order_status", AsyncMock(return_value=hydrated_order))
    monkeypatch.setattr(order_status, "send_customer_handoff", handoff)

    result = await order_status.take_order_in_work(db, order_id=5)

    assert result.order is reloaded_order
    assert result.delivery == order_status.DeliveryOutcome.RICH
    rollback.assert_awaited_once()


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
    notify_mock.assert_awaited_once_with(hydrated_order)


@pytest.mark.asyncio
async def test_update_order_status_reconciles_inaccessible_customer_chat(monkeypatch) -> None:
    """Сбрасывает локальный доступ по outcome статусного уведомления."""
    initial_order = SimpleNamespace(id=5, status=int(OrderStatus.CREATED))
    updated_order = SimpleNamespace(id=5, status=int(OrderStatus.PROCESSING))
    customer = SimpleNamespace(id=8, telegram_id=700002, telegram_write_access=True)
    hydrated_order = SimpleNamespace(
        id=5,
        status=int(OrderStatus.PROCESSING),
        user=customer,
    )
    commit_mock = AsyncMock()
    first_get_done = False

    class _FakeRepo:
        def __init__(self, db) -> None:
            self.db = db

        async def get_one(self, order_id: int):
            nonlocal first_get_done
            if not first_get_done:
                first_get_done = True
                return initial_order
            return hydrated_order

        async def update_status(self, order_id: int, status: int):
            return updated_order

    class _FakeUserRepo:
        def __init__(self, db) -> None:
            self.db = db

        async def get_manager(self):
            return SimpleNamespace(telegram_id=700001, username="manager")

    monkeypatch.setattr(order_status, "OrderRepository", _FakeRepo)
    monkeypatch.setattr(order_status, "UserRepository", _FakeUserRepo)
    monkeypatch.setattr(
        order_status,
        "notify_order_status_changed",
        AsyncMock(return_value=order_status.DeliveryOutcome.INACCESSIBLE),
    )
    db = SimpleNamespace(commit=commit_mock, rollback=AsyncMock())

    await update_order_status(db, order_id=5, status=OrderStatus.PROCESSING)

    assert customer.telegram_write_access is False
    assert commit_mock.await_count == 2


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
    notify_mock.assert_awaited_once_with(hydrated_order)


@pytest.mark.asyncio
async def test_update_order_status_passes_public_number_to_referral_notification(
    monkeypatch,
) -> None:
    initial_order = SimpleNamespace(
        id=5,
        status=int(OrderStatus.PROCESSING),
        publicNumber="2026070068",
        amountSell=Decimal("100"),
        UserId=42,
        currencySell="USDT",
        currencyBuy="VND",
    )
    updated_order = SimpleNamespace(id=5, status=int(OrderStatus.COMPLETED))
    hydrated_order = SimpleNamespace(
        id=5,
        status=int(OrderStatus.COMPLETED),
        publicNumber="2026070068",
        amountSell=Decimal("100"),
        UserId=42,
        currencySell="USDT",
        currencyBuy="VND",
    )
    commit_mock = AsyncMock()
    first_get_done = False
    credit_referral_bonus = AsyncMock(return_value=Decimal("5.00"))
    status_notify_mock = AsyncMock()
    manager = SimpleNamespace(telegram_id=700001, username="manager")

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
            assert status == int(OrderStatus.COMPLETED)
            return updated_order

    class _FakeUserRepo:
        def __init__(self, db) -> None:
            self.db = db

        async def get_manager(self):
            return manager

    class _FakeReferralService:
        def __init__(self) -> None:
            self.credit_referral_bonus = credit_referral_bonus

    db = SimpleNamespace(commit=commit_mock, rollback=AsyncMock())

    monkeypatch.setattr(order_status, "OrderRepository", _FakeRepo)
    monkeypatch.setattr(order_status, "UserRepository", _FakeUserRepo)
    monkeypatch.setattr(referral_service_module, "ReferralService", _FakeReferralService)
    monkeypatch.setattr(order_status, "notify_order_status_changed", status_notify_mock)

    updated = await update_order_status(
        db,
        order_id=5,
        status=OrderStatus.COMPLETED,
    )

    assert updated is hydrated_order
    credit_referral_bonus.assert_awaited_once_with(
        db,
        order_id=5,
        order_public_number="2026070068",
        order_amount=Decimal("100"),
        referred_user_id=42,
        currency_sell="USDT",
        currency_buy="VND",
    )
    status_notify_mock.assert_awaited_once_with(hydrated_order)


@pytest.mark.asyncio
async def test_update_order_status_sends_referral_reversal_notification(monkeypatch) -> None:
    initial_order = SimpleNamespace(id=5, status=int(OrderStatus.PROCESSING))
    updated_order = SimpleNamespace(id=5, status=int(OrderStatus.CANCELLED))
    hydrated_order = SimpleNamespace(
        id=5,
        status=int(OrderStatus.CANCELLED),
        publicNumber="2026070068",
    )
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
        order_public_number="2026070068",
        amount=Decimal("12.345"),
    )
    status_notify_mock.assert_awaited_once_with(hydrated_order)


@pytest.mark.asyncio
async def test_update_order_status_ignores_referral_reversal_notification_failure(
    monkeypatch,
) -> None:
    initial_order = SimpleNamespace(id=5, status=int(OrderStatus.PROCESSING))
    updated_order = SimpleNamespace(id=5, status=int(OrderStatus.CANCELLED))
    hydrated_order = SimpleNamespace(
        id=5,
        status=int(OrderStatus.CANCELLED),
        publicNumber="2026070068",
    )
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
        order_public_number="2026070068",
        amount=Decimal("12.345"),
    )
    status_notify_mock.assert_awaited_once_with(hydrated_order)
