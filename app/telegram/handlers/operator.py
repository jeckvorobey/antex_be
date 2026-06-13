"""Обработчики менеджера для жизненного цикла заявки."""
# ruff: noqa: RUF001

from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.types import CallbackQuery

from app.core.database import create_db_session
from app.enums.order import OrderStatus
from app.enums.user import has_operator_access
from app.services.order_notifications import build_chat_url_for_user, build_manager_status_text
from app.services.order_status import update_order_status
from app.telegram import messages
from app.telegram.keyboards import (
    manager_order_chat_only,
    manager_order_close,
)
from app.telegram.services.user_service import check_user

logger = logging.getLogger(__name__)
router = Router(name="operator")


async def _get_db():
    return create_db_session()


@router.callback_query(F.data.startswith("op:take:"))
async def operator_take(callback: CallbackQuery) -> None:
    order_id = int(callback.data.split(":")[2])  # type: ignore[union-attr]
    db = await _get_db()
    async with db:
        user, _ = await check_user(db, callback.from_user)
        if not has_operator_access(user.role):
            await callback.answer("Нет прав", show_alert=True)
            return

        order = await update_order_status(db, order_id=order_id, status=OrderStatus.PROCESSING)
        chat_url = build_chat_url_for_user(getattr(order, "user", None))
        if not chat_url:
            await callback.answer("У пользователя нет Telegram-ссылки", show_alert=True)
            return

    await callback.message.edit_text(  # type: ignore[union-attr]
        build_manager_status_text(order),
        reply_markup=manager_order_close(
            order_id=order.id,
            chat_url=chat_url,
            message_text=messages.manager_chat_open_text(
                order_id=order.publicNumber,
                amount_sell=getattr(order, "amountSell", 0) or 0,
                currency_sell=getattr(order, "currencySell", "—"),
                translator=None,
                locale="ru",
            ),
        ),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("op:cancel:"))
async def operator_cancel(callback: CallbackQuery) -> None:
    order_id = int(callback.data.split(":")[2])  # type: ignore[union-attr]
    db = await _get_db()
    async with db:
        user, _ = await check_user(db, callback.from_user)
        if not has_operator_access(user.role):
            await callback.answer("Нет прав", show_alert=True)
            return

        order = await update_order_status(db, order_id=order_id, status=OrderStatus.CANCELLED)
        chat_url = build_chat_url_for_user(getattr(order, "user", None))

    reply_markup = None
    if chat_url:
        reply_markup = manager_order_chat_only(chat_url=chat_url)

    await callback.message.edit_text(  # type: ignore[union-attr]
        build_manager_status_text(order),
        reply_markup=reply_markup,
    )
    await callback.answer("Заявка отменена", show_alert=True)


@router.callback_query(F.data.startswith("op:open_chat:"))
async def operator_open_chat(callback: CallbackQuery) -> None:
    await callback.answer("Кнопка чата устарела", show_alert=True)


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
        chat_url = build_chat_url_for_user(getattr(order, "user", None))

    reply_markup = None
    if chat_url:
        reply_markup = manager_order_chat_only(chat_url=chat_url)

    await callback.message.edit_text(  # type: ignore[union-attr]
        build_manager_status_text(order),
        reply_markup=reply_markup,
    )
    await callback.answer()
