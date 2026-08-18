"""Обработчики менеджера для жизненного цикла заявки."""

from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.types import CallbackQuery
from sqlalchemy.exc import SQLAlchemyError

from app.core.database import create_db_session
from app.enums.order import OrderStatus
from app.enums.user import has_operator_access
from app.repositories.order import OrderRepository
from app.services.order_notifications import (
    build_manager_workspace_url,
    edit_manager_order_card,
    is_delivery_success,
    reconcile_telegram_write_access,
    send_customer_reminder,
)
from app.services.order_status import take_order_in_work, update_order_status
from app.telegram.i18n import get_translator, normalize_locale
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


def _operator_translate(callback: CallbackQuery):
    """Выбрать Fluent translator по языку Telegram-оператора."""
    return get_translator(normalize_locale(callback.from_user.language_code))


def _build_active_order_markup(order):
    if int(getattr(order, "status", 0)) == int(OrderStatus.PROCESSING):
        return manager_order_close(
            order_id=order.id,
            manager_app_url=build_manager_workspace_url(order_id=order.id),
        )

    return manager_order_open_chat(order_id=order.id)


@router.callback_query(F.data.startswith("op:take:"))
async def operator_take(callback: CallbackQuery) -> None:
    translate = _operator_translate(callback)
    order_id = int(callback.data.split(":")[2])  # type: ignore[union-attr]
    db = await _get_db()
    async with db:
        user, _ = await check_user(db, callback.from_user)
        if not has_operator_access(user.role):
            await callback.answer(translate("manager-access-denied"), show_alert=True)
            return

        current = await OrderRepository(db).get_one(order_id)
        if current is None:
            await callback.answer(translate("operator-order-not-found"), show_alert=True)
            return
        if int(current.status) != int(OrderStatus.CREATED):
            await callback.answer(translate("operator-order-status-changed"), show_alert=True)
            return

        result = await take_order_in_work(db, order_id=order_id)
        order = result.order

    card_delivery = await edit_manager_order_card(
        message=callback.message,
        order=order,
        reply_markup=manager_order_close(
            order_id=order.id,
            manager_app_url=build_manager_workspace_url(order_id=order.id),
        ),
        customer_notified=is_delivery_success(result.delivery),
    )
    if not is_delivery_success(card_delivery):
        await callback.answer(translate("operator-card-update-failed"), show_alert=True)
        return
    if not is_delivery_success(result.delivery):
        await callback.answer(translate("operator-handoff-delivery-failed"), show_alert=True)
        return
    await callback.answer()


@router.callback_query(F.data.startswith("op:remind:"))
async def operator_remind(callback: CallbackQuery) -> None:
    translate = _operator_translate(callback)
    order_id = int(callback.data.split(":")[2])  # type: ignore[union-attr]
    db = await _get_db()
    async with db:
        user, _ = await check_user(db, callback.from_user)
        if not has_operator_access(user.role):
            await callback.answer(translate("manager-access-denied"), show_alert=True)
            return

        order = await OrderRepository(db).get_one(order_id)
        if order is None:
            await callback.answer(translate("operator-order-not-found"), show_alert=True)
            return
        if int(order.status) != int(OrderStatus.PROCESSING):
            await callback.answer(translate("operator-reminder-processing-only"), show_alert=True)
            return
        delivery = await send_customer_reminder(order, None)
        if reconcile_telegram_write_access(
            getattr(order, "user", None),
            delivery,
            operation="customer_reminder",
        ):
            try:
                await db.commit()
            except SQLAlchemyError:
                await db.rollback()
                logger.exception(
                    "Failed to persist reminder write access outcome: order_id=%s outcome=%s",
                    order_id,
                    delivery,
                )

    if not is_delivery_success(delivery):
        await callback.answer(translate("operator-reminder-failed"), show_alert=True)
        return
    await callback.answer(translate("operator-reminder-sent"), show_alert=False)


@router.callback_query(F.data.startswith("op:cancel:"))
async def operator_cancel(callback: CallbackQuery) -> None:
    translate = _operator_translate(callback)
    order_id = int(callback.data.split(":")[2])  # type: ignore[union-attr]
    db = await _get_db()
    async with db:
        user, _ = await check_user(db, callback.from_user)
        if not has_operator_access(user.role):
            await callback.answer(translate("manager-access-denied"), show_alert=True)
            return

    await callback.message.edit_reply_markup(  # type: ignore[union-attr]
        reply_markup=manager_order_cancel_confirm(order_id=order_id)
    )
    await callback.answer()


@router.callback_query(F.data.startswith("op:cancel_confirm:"))
async def operator_cancel_confirm(callback: CallbackQuery) -> None:
    translate = _operator_translate(callback)
    order_id = int(callback.data.split(":")[2])  # type: ignore[union-attr]
    db = await _get_db()
    async with db:
        user, _ = await check_user(db, callback.from_user)
        if not has_operator_access(user.role):
            await callback.answer(translate("manager-access-denied"), show_alert=True)
            return

        order = await update_order_status(db, order_id=order_id, status=OrderStatus.CANCELLED)
        manager_app_url = build_manager_workspace_url(order_id=order.id)

    reply_markup = None
    if manager_app_url:
        reply_markup = manager_order_chat_only(manager_app_url=manager_app_url)

    card_delivery = await edit_manager_order_card(
        message=callback.message,
        order=order,
        reply_markup=reply_markup,
    )
    if not is_delivery_success(card_delivery):
        await callback.answer(translate("operator-card-update-failed"), show_alert=True)
        return
    await callback.answer(translate("operator-order-cancelled"), show_alert=True)


@router.callback_query(F.data.startswith("op:cancel_keep:"))
async def operator_cancel_keep(callback: CallbackQuery) -> None:
    translate = _operator_translate(callback)
    order_id = int(callback.data.split(":")[2])  # type: ignore[union-attr]
    db = await _get_db()
    async with db:
        user, _ = await check_user(db, callback.from_user)
        if not has_operator_access(user.role):
            await callback.answer(translate("manager-access-denied"), show_alert=True)
            return

        order = await OrderRepository(db).get_one(order_id)
        if order is None:
            await callback.answer(translate("operator-order-not-found"), show_alert=True)
            return

    await callback.message.edit_reply_markup(  # type: ignore[union-attr]
        reply_markup=_build_active_order_markup(order)
    )
    await callback.answer()


@router.callback_query(F.data.startswith("op:open_chat:"))
async def operator_open_chat(callback: CallbackQuery) -> None:
    await callback.answer(
        _operator_translate(callback)("operator-chat-button-obsolete"),
        show_alert=True,
    )


@router.callback_query(F.data.startswith("op:close:"))
async def operator_close(callback: CallbackQuery) -> None:
    translate = _operator_translate(callback)
    order_id = int(callback.data.split(":")[2])  # type: ignore[union-attr]
    db = await _get_db()
    async with db:
        user, _ = await check_user(db, callback.from_user)
        if not has_operator_access(user.role):
            await callback.answer(translate("manager-access-denied"), show_alert=True)
            return

        order = await update_order_status(db, order_id=order_id, status=OrderStatus.COMPLETED)
        manager_app_url = build_manager_workspace_url(order_id=order.id)

    reply_markup = None
    if manager_app_url:
        reply_markup = manager_order_chat_only(manager_app_url=manager_app_url)

    card_delivery = await edit_manager_order_card(
        message=callback.message,
        order=order,
        reply_markup=reply_markup,
    )
    if not is_delivery_success(card_delivery):
        await callback.answer(translate("operator-card-update-failed"), show_alert=True)
        return
    await callback.answer()
