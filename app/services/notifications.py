"""Совместимость для вызовов уведомлений."""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.services.order_notifications import notify_order_created as notify_order_created_message

if TYPE_CHECKING:
    from app.services.order_notifications import OrderCreatedDelivery


async def notify_order_created(
    order,
    user,
    manager,
    *,
    notify_user: bool = True,
) -> OrderCreatedDelivery:
    return await notify_order_created_message(order, user, manager, notify_user=notify_user)
