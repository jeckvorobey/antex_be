"""Единый модуль уведомлений."""

from __future__ import annotations

from app.telegram.services.notification_service import (
    NotificationMessage,
    send_order_created_to_manager,
    send_order_created_to_user,
)


async def notify_order_created(order, user, manager) -> None:
    user_message = NotificationMessage(
        chat_id=user.chatId or user.telegram_id,
        text=(
            f"Заявка #{order.id} создана.\n"
            f"Город: {order.city.name}\n"
            f"Пара: {order.currencySell} -> {order.currencyBuy}\n"
            f"Сумма: {order.amountSell}"
        ),
    )
    manager_message = NotificationMessage(
        chat_id=manager.chatId or manager.telegram_id,
        text=(
            f"Новая заявка #{order.id}\n"
            f"Город: {order.city.name}\n"
            f"Пользователь: {user.id}\n"
            f"Пара: {order.currencySell} -> {order.currencyBuy}\n"
            f"Сумма: {order.amountSell}\n"
            f"Контакт: {order.contactTelegram or '-'}"
        ),
    )

    await send_order_created_to_user(user_message)
    await send_order_created_to_manager(manager_message)
