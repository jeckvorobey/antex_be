"""Регрессия смены статуса после снятия менеджерской роли."""

from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select

from app.enums.country import Country
from app.enums.order import OrderStatus
from app.enums.user import LEGACY_ADMIN_ROLE, UserRole
from app.exceptions import AntExException
from app.models.chat import ChatConversation
from app.models.order import Order
from app.models.order_telegram_sync_task import OrderTelegramSyncTask
from app.models.user import User
from app.services.order_status import take_order_in_work, update_order_status


async def make_assigned_order(db, old_role=UserRole.USER, status=OrderStatus.PROCESSING):
    """Создаёт реальную заявку и отдельную беседу прежнего владельца."""
    old = User(telegram_id=901001, role=int(old_role))
    manager = User(telegram_id=901002, role=int(UserRole.MANAGER))
    customer = User(telegram_id=901003)
    db.add_all([old, manager, customer])
    await db.flush()
    order = Order(
        UserId=customer.id,
        ManagerId=old.id,
        country=Country.GEORGIA,
        currencySell="USDT",
        amountSell=300,
        currencyBuy="GEL",
        amountBuy=759.33,
        status=int(status),
        methodGet="qrcode",
        publicNumber="901001",
    )
    conversation = ChatConversation(user_id=customer.id, manager_id=old.id)
    db.add_all([order, conversation])
    await db.commit()
    return order, old, manager, conversation


@pytest.mark.parametrize("target", [OrderStatus.COMPLETED, OrderStatus.CANCELLED])
async def test_current_manager_finishes_order_after_previous_manager_lost_role(db_session, target):
    """Статус и новый владелец сохраняются вместе, старая беседа не передаётся."""
    order, old, manager, conversation = await make_assigned_order(db_session)

    result = await update_order_status(
        db_session,
        order_id=order.id,
        status=target,
        manager_id=manager.id,
    )

    await db_session.refresh(order)
    await db_session.refresh(conversation)
    assert result.status == int(target)
    assert order.ManagerId == manager.id
    assert conversation.manager_id == old.id
    tasks = list(await db_session.scalars(select(OrderTelegramSyncTask)))
    assert {(task.status, task.target) for task in tasks} == {
        (int(target), "user"),
        (int(target), "manager"),
    }
    await update_order_status(
        db_session,
        order_id=order.id,
        status=target,
        manager_id=manager.id,
    )
    assert len(list(await db_session.scalars(select(OrderTelegramSyncTask)))) == 2


@pytest.mark.parametrize("old_role", [UserRole.MANAGER, LEGACY_ADMIN_ROLE])
async def test_other_active_manager_ownership_remains_protected(db_session, old_role):
    """Чужая действующая менеджерская роль по-прежнему приводит к 409."""
    order, old, manager, _ = await make_assigned_order(db_session, old_role)
    with pytest.raises(AntExException) as caught:
        await update_order_status(
            db_session,
            order_id=order.id,
            status=OrderStatus.COMPLETED,
            manager_id=manager.id,
        )
    assert caught.value.status_code == 409
    assert order.status == int(OrderStatus.PROCESSING)
    assert order.ManagerId == old.id
    assert list(await db_session.scalars(select(OrderTelegramSyncTask))) == []


async def test_terminal_order_is_not_reassigned_after_manager_role_change(db_session):
    """История завершённой заявки остаётся за прежним владельцем."""
    order, old, manager, _ = await make_assigned_order(db_session, status=OrderStatus.COMPLETED)
    with pytest.raises(AntExException):
        await update_order_status(
            db_session,
            order_id=order.id,
            status=OrderStatus.COMPLETED,
            manager_id=manager.id,
        )
    assert order.ManagerId == old.id


async def test_telegram_take_reassigns_active_order_without_repeating_handoff(
    db_session, monkeypatch
):
    """Повторное принятие бесхозной активной заявки сохраняет владельца без дублей."""
    order, _, manager, _ = await make_assigned_order(db_session)
    handoff = AsyncMock()
    monkeypatch.setattr("app.services.order_status.send_customer_handoff", handoff)
    result = await take_order_in_work(db_session, order_id=order.id, manager=manager)
    await db_session.refresh(order)
    assert result.order.ManagerId == manager.id
    assert order.status == int(OrderStatus.PROCESSING)
    handoff.assert_not_awaited()
    assert list(await db_session.scalars(select(OrderTelegramSyncTask))) == []
