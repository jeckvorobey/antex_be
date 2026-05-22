"""Обработчики менеджера для жизненного цикла заявки."""
# ruff: noqa: RUF001

from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.types import CallbackQuery

from app.core.database import get_db_session
from app.enums.order import OrderStatus
from app.enums.user import has_operator_access
from app.repositories.order import OrderRepository
from app.services.order_notifications import build_manager_chat_url
from app.services.order_status import update_order_status
from app.telegram.keyboards import manager_order_close
from app.telegram.services.user_service import check_user

logger = logging.getLogger(__name__)
router = Router(name="operator")


async def _get_db():
    async for session in get_db_session():
        return session
    raise RuntimeError("Database session is unavailable")


@router.callback_query(F.data.startswith("op:open_chat:"))
async def operator_open_chat(callback: CallbackQuery) -> None:
    order_id = int(callback.data.split(":")[2])  # type: ignore[union-attr]
    db = await _get_db()
    async with db:
        user, _ = await check_user(db, callback.from_user)
        if not has_operator_access(user.role):
            await callback.answer("Нет прав", show_alert=True)
            return

        order = await OrderRepository(db).get_one(order_id)
        if not order:
            await callback.answer("Заявка не найдена", show_alert=True)
            return

        chat_url = build_manager_chat_url(order)
        if not chat_url:
            await callback.answer("У пользователя нет Telegram-ссылки", show_alert=True)
            return

        order = await update_order_status(db, order_id=order_id, status=OrderStatus.PROCESSING)

    await callback.message.edit_text(  # type: ignore[union-attr]
        _build_manager_status_text(order),
        reply_markup=manager_order_close(order_id=order.id),
    )
    await callback.answer(url=chat_url)


@router.callback_query(F.data.startswith("op:close:"))
async def operator_close(callback: CallbackQuery) -> None:
    order_id = int(callback.data.split(":")[2])  # type: ignore[union-attr]
    db = await _get_db()
    async with db:
        user, _ = await check_user(db, callback.from_user)
        if not has_operator_access(user.role):
            await callback.answer("Нет прав", show_alert=True)
            return

        order = await update_order_status(db, order_id=order_id, status=OrderStatus.COMPLETED)

    await callback.message.edit_text(  # type: ignore[union-attr]
        _build_manager_status_text(order),
        reply_markup=None,
    )
    await callback.answer()


def _build_manager_status_text(order) -> str:
    city_name = order.city.name if getattr(order, "city", None) else "—"
    return "\n".join(
        [
            f"Заявка #{order.publicNumber}",
            f"Статус: {_status_label(order.status)}",
            f"Город: {city_name}",
            f"Пара: {order.currencySell} -> {order.currencyBuy}",
            f"Сумма: {order.amountSell} {order.currencySell}",
        ]
    )


def _status_label(status: int) -> str:
    return {
        int(OrderStatus.CREATED): "Новая",
        int(OrderStatus.PROCESSING): "В работе",
        int(OrderStatus.COMPLETED): "Завершена",
        int(OrderStatus.CANCELLED): "Отменена",
    }.get(status, f"Статус {status}")
