"""Совместимость для вызовов уведомлений."""

from __future__ import annotations

from app.services.order_notifications import notify_order_created as notify_order_created_message


async def notify_order_created(order, user, manager, *, notify_user: bool = True) -> None:
    await notify_order_created_message(order, user, manager, notify_user=notify_user)
