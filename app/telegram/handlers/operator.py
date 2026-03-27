"""Обработчики оператора."""

from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.types import CallbackQuery

from app.core.database import get_db_session
from app.enums.user import UserRole
from app.repositories.order import OrderRepository
from app.telegram import messages
from app.telegram.services.notification_service import notify_user
from app.telegram.services.user_service import check_user

logger = logging.getLogger(__name__)
router = Router(name="operator")


@router.callback_query(F.data.startswith("op:confirm:"))
async def operator_confirm(callback: CallbackQuery) -> None:
    order_id = int(callback.data.split(":")[2])  # type: ignore[union-attr]
    db_gen = get_db_session()
    db = await db_gen.__anext__()
    async with db:
        user, _ = await check_user(db, callback.from_user)
        if user.role < UserRole.OPERATOR:
            await callback.answer("Нет прав", show_alert=True)
            return

        repo = OrderRepository(db)
        order = await repo.get_one(order_id)
        if not order:
            await callback.answer("Заявка не найдена", show_alert=True)
            return
        await repo.update_status(order_id, 2)
        await db.commit()

    await notify_user(callback.bot, order.UserId, messages.order_confirmed(order_id))
    await callback.answer("✅ Подтверждено")
    await callback.message.edit_text(  # type: ignore[union-attr]
        callback.message.text + "\n\n✅ <b>Подтверждено</b>"  # type: ignore[operator]
    )


@router.callback_query(F.data.startswith("op:cancel:"))
async def operator_cancel(callback: CallbackQuery) -> None:
    order_id = int(callback.data.split(":")[2])  # type: ignore[union-attr]
    db_gen = get_db_session()
    db = await db_gen.__anext__()
    async with db:
        user, _ = await check_user(db, callback.from_user)
        if user.role < UserRole.OPERATOR:
            await callback.answer("Нет прав", show_alert=True)
            return

        repo = OrderRepository(db)
        order = await repo.get_one(order_id)
        if not order:
            await callback.answer("Заявка не найдена", show_alert=True)
            return
        await repo.cancel(order_id)
        await db.commit()

    await notify_user(callback.bot, order.UserId, messages.order_cancelled(order_id))
    await callback.answer("❌ Отменено")
    await callback.message.edit_text(  # type: ignore[union-attr]
        callback.message.text + "\n\n❌ <b>Отменено</b>"  # type: ignore[operator]
    )
