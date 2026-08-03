"""Обработчики менеджера для жизненного цикла заявки."""

from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.types import CallbackQuery

from app.core.database import create_db_session
from app.enums.order import OrderStatus
from app.enums.user import has_operator_access
from app.repositories.order import OrderRepository
from app.repositories.user import UserRepository
from app.services.order_notifications import (
    DeliveryOutcome,
    build_chat_url_for_user,
    edit_manager_order_card,
    send_customer_reminder,
)
from app.services.order_status import take_order_in_work, update_order_status
from app.telegram import messages
from app.telegram.keyboards import (
    manager_order_cancel_confirm,
    manager_order_chat_only,
    manager_order_close,
    manager_order_open_chat,
)
from app.telegram.services.user_service import check_user

logger = logging.getLogger(__name__)
router = Router(name="operator")


async def _get_db():
    return create_db_session()


def _manager_chat_draft_text(order) -> str:
    return messages.manager_chat_open_text(
        order_id=order.publicNumber,
        amount_sell=getattr(order, "amountSell", 0) or 0,
        currency_sell=getattr(order, "currencySell", "—"),
        translator=None,
        locale="ru",
    )


def _build_active_order_markup(order):
    if int(getattr(order, "status", 0)) == int(OrderStatus.PROCESSING):
        chat_url = build_chat_url_for_user(getattr(order, "user", None))
        if not chat_url:
            return manager_order_open_chat(order_id=order.id)
        return manager_order_close(
            order_id=order.id,
            chat_url=chat_url,
            message_text=_manager_chat_draft_text(order),
        )

    return manager_order_open_chat(order_id=order.id)


@router.callback_query(F.data.startswith("op:take:"))
async def operator_take(callback: CallbackQuery) -> None:
    order_id = int(callback.data.split(":")[2])  # type: ignore[union-attr]
    db = await _get_db()
    async with db:
        user, _ = await check_user(db, callback.from_user)
        if not has_operator_access(user.role):
            await callback.answer(messages.manager_alert("access-denied"), show_alert=True)
            return

        current = await OrderRepository(db).get_one(order_id)
        if current is None:
            await callback.answer(messages.manager_alert("order-not-found"), show_alert=True)
            return
        if int(current.status) != int(OrderStatus.CREATED):
            await callback.answer(messages.manager_alert("status-changed"), show_alert=True)
            return

        result = await take_order_in_work(db, order_id=order_id)
        order = result.order
        chat_url = build_chat_url_for_user(getattr(order, "user", None))
        if not chat_url:
            await callback.answer(messages.manager_alert("client-link-missing"), show_alert=True)
            return

    card_delivery = await edit_manager_order_card(
        message=callback.message,
        order=order,
        reply_markup=manager_order_close(
            order_id=order.id,
            chat_url=chat_url,
            message_text=_manager_chat_draft_text(order),
        ),
        customer_notified=result.delivery != DeliveryOutcome.FAILED,
    )
    if card_delivery == DeliveryOutcome.FAILED:
        await callback.answer(messages.manager_alert("card-update-failed"), show_alert=True)
        return
    if result.delivery == DeliveryOutcome.FAILED:
        await callback.answer(messages.manager_alert("handoff-failed"), show_alert=True)
        return
    await callback.answer()


@router.callback_query(F.data.startswith("op:remind:"))
async def operator_remind(callback: CallbackQuery) -> None:
    order_id = int(callback.data.split(":")[2])  # type: ignore[union-attr]
    db = await _get_db()
    async with db:
        user, _ = await check_user(db, callback.from_user)
        if not has_operator_access(user.role):
            await callback.answer(messages.manager_alert("access-denied"), show_alert=True)
            return

        order = await OrderRepository(db).get_one(order_id)
        if order is None:
            await callback.answer(messages.manager_alert("order-not-found"), show_alert=True)
            return
        if int(order.status) != int(OrderStatus.PROCESSING):
            await callback.answer(
                messages.manager_alert("reminder-processing-only"),
                show_alert=True,
            )
            return
        manager = await UserRepository(db).get_manager()
        delivery = await send_customer_reminder(order, manager)

    if delivery == DeliveryOutcome.FAILED:
        await callback.answer(messages.manager_alert("reminder-failed"), show_alert=True)
        return
    await callback.answer(messages.manager_alert("reminder-sent"), show_alert=False)


@router.callback_query(F.data.startswith("op:cancel:"))
async def operator_cancel(callback: CallbackQuery) -> None:
    order_id = int(callback.data.split(":")[2])  # type: ignore[union-attr]
    db = await _get_db()
    async with db:
        user, _ = await check_user(db, callback.from_user)
        if not has_operator_access(user.role):
            await callback.answer(messages.manager_alert("access-denied"), show_alert=True)
            return

    await callback.message.edit_reply_markup(  # type: ignore[union-attr]
        reply_markup=manager_order_cancel_confirm(order_id=order_id)
    )
    await callback.answer()


@router.callback_query(F.data.startswith("op:cancel_confirm:"))
async def operator_cancel_confirm(callback: CallbackQuery) -> None:
    order_id = int(callback.data.split(":")[2])  # type: ignore[union-attr]
    db = await _get_db()
    async with db:
        user, _ = await check_user(db, callback.from_user)
        if not has_operator_access(user.role):
            await callback.answer(messages.manager_alert("access-denied"), show_alert=True)
            return

        order = await update_order_status(db, order_id=order_id, status=OrderStatus.CANCELLED)
        chat_url = build_chat_url_for_user(getattr(order, "user", None))

    reply_markup = None
    if chat_url:
        reply_markup = manager_order_chat_only(chat_url=chat_url)

    card_delivery = await edit_manager_order_card(
        message=callback.message,
        order=order,
        reply_markup=reply_markup,
    )
    if card_delivery == DeliveryOutcome.FAILED:
        await callback.answer(messages.manager_alert("card-update-failed"), show_alert=True)
        return
    await callback.answer(messages.manager_alert("cancelled"), show_alert=True)


@router.callback_query(F.data.startswith("op:cancel_keep:"))
async def operator_cancel_keep(callback: CallbackQuery) -> None:
    order_id = int(callback.data.split(":")[2])  # type: ignore[union-attr]
    db = await _get_db()
    async with db:
        user, _ = await check_user(db, callback.from_user)
        if not has_operator_access(user.role):
            await callback.answer(messages.manager_alert("access-denied"), show_alert=True)
            return

        order = await OrderRepository(db).get_one(order_id)
        if order is None:
            await callback.answer(messages.manager_alert("order-not-found"), show_alert=True)
            return

    await callback.message.edit_reply_markup(  # type: ignore[union-attr]
        reply_markup=_build_active_order_markup(order)
    )
    await callback.answer()


@router.callback_query(F.data.startswith("op:open_chat:"))
async def operator_open_chat(callback: CallbackQuery) -> None:
    await callback.answer(messages.manager_alert("chat-stale"), show_alert=True)


@router.callback_query(F.data.startswith("op:close:"))
async def operator_close(callback: CallbackQuery) -> None:
    order_id = int(callback.data.split(":")[2])  # type: ignore[union-attr]
    db = await _get_db()
    async with db:
        user, _ = await check_user(db, callback.from_user)
        if not has_operator_access(user.role):
            await callback.answer(messages.manager_alert("access-denied"), show_alert=True)
            return

        order = await update_order_status(db, order_id=order_id, status=OrderStatus.COMPLETED)
        chat_url = build_chat_url_for_user(getattr(order, "user", None))

    reply_markup = None
    if chat_url:
        reply_markup = manager_order_chat_only(chat_url=chat_url)

    card_delivery = await edit_manager_order_card(
        message=callback.message,
        order=order,
        reply_markup=reply_markup,
    )
    if card_delivery == DeliveryOutcome.FAILED:
        await callback.answer(messages.manager_alert("card-update-failed"), show_alert=True)
        return
    await callback.answer()
