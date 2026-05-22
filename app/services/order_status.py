"""Единый сервис смены статуса заявки."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.enums.order import OrderStatus
from app.exceptions import AntExException
from app.repositories.order import OrderRepository
from app.repositories.user import UserRepository
from app.services.order_notifications import (
    build_chat_url_for_user,
    notify_order_status_changed,
)


async def update_order_status(
    db: AsyncSession,
    *,
    order_id: int,
    status: OrderStatus | int,
) -> object:
    try:
        target_status = OrderStatus(int(status))
    except ValueError as exc:
        raise ValueError(f"Unsupported status: {status}") from exc

    repo = OrderRepository(db)
    order = await repo.get_one(order_id)
    if order is None:
        raise AntExException("Order not found", code="ORDER_NOT_FOUND", status_code=404)

    if order.status == int(target_status):
        return order

    order = await repo.update_status(order_id, int(target_status))
    await db.commit()
    hydrated = await repo.get_one(order_id)
    if hydrated is None:
        raise AntExException("Order not found", code="ORDER_NOT_FOUND", status_code=404)

    manager = await UserRepository(db).get_manager()
    manager_chat_url = build_chat_url_for_user(manager) if manager is not None else None

    await notify_order_status_changed(hydrated, manager_chat_url=manager_chat_url)
    await db.commit()
    return hydrated
