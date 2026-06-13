"""Start and basic menu handlers."""

from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import create_db_session
from app.enums.order import OrderStatus
from app.enums.user import has_admin_access, has_operator_access
from app.repositories.config import ConfigRepository
from app.repositories.order import OrderRepository
from app.services.order_notifications import build_chat_url_for_user, build_manager_status_text
from app.telegram import messages
from app.telegram.handlers.exchange import ExchangeState
from app.telegram.i18n import get_user_translator
from app.telegram.keyboards import (
    choose_country,
    manager_home,
    manager_new_orders_list,
    manager_order_open_chat,
)
from app.telegram.services.user_service import check_user

logger = logging.getLogger(__name__)
router = Router(name="start")


async def _get_db() -> AsyncSession:
    return create_db_session()


async def _safe_edit_text(message, text: str, *, reply_markup) -> None:
    try:
        await message.edit_text(text, reply_markup=reply_markup)
    except TelegramBadRequest as exc:
        if "message is not modified" not in str(exc).lower():
            raise


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext) -> None:
    translate = get_user_translator(message.from_user)
    logger.info(
        "Запустили /start: telegram_id=%s, username=%s",
        message.from_user.id,
        message.from_user.username,
    )
    db = await _get_db()
    async with db:
        config_repo = ConfigRepository(db)
        config = await config_repo.get_or_create()
        user, _ = await check_user(db, message.from_user)
        await db.commit()
    logger.info(
        "Авторизован /start user: telegram_id=%s, user_id=%s, role=%s, bot_enabled=%s",
        message.from_user.id,
        getattr(user, "id", None),
        user.role,
        config.enabled,
    )
    if not config.enabled:
        await message.answer(messages.bot_disabled(translator=translate))
        logger.info(
            "Отправлено bot-disabled сообщение для /start: telegram_id=%s",
            message.from_user.id,
        )
        return

    menu_type = "manager" if has_operator_access(user.role) else "user"
    try:
        if menu_type == "manager":
            await message.answer(
                messages.welcome(message.from_user.first_name, translator=translate),
                reply_markup=manager_home(translate),
            )
        else:
            await state.clear()
            await state.set_state(ExchangeState.choosing_country)
            await message.answer(
                messages.exchange_start_welcome(message.from_user.first_name, translator=translate),
                reply_markup=choose_country(translate),
            )
    except Exception:
        logger.exception(
            "Ошибка при отправке /start сообщения: telegram_id=%s",
            message.from_user.id,
        )
        raise
    logger.info(
        "Отправлено /start сообщение: telegram_id=%s, menu=%s",
        message.from_user.id,
        menu_type,
    )


@router.callback_query(F.data == "manager:new_orders")
async def manager_new_orders(callback: CallbackQuery) -> None:
    translate = get_user_translator(callback.from_user)
    db = await _get_db()
    async with db:
        user, created = await check_user(db, callback.from_user)
        if created:
            await db.commit()
        if not has_operator_access(user.role):
            await callback.answer(translate("manager-access-denied"), show_alert=True)
            return
        orders = await OrderRepository(db).list_by_status(OrderStatus.CREATED, limit=10)

    if not orders:
        await _safe_edit_text(
            callback.message,
            translate("manager-new-orders-empty"),
            reply_markup=manager_home(translate),
        )
    else:
        await _safe_edit_text(
            callback.message,
            translate("manager-new-orders-header"),
            reply_markup=manager_new_orders_list(translate, orders),
        )
    await callback.answer()


@router.callback_query(F.data.startswith("manager:order:"))
async def manager_order_detail(callback: CallbackQuery) -> None:
    translate = get_user_translator(callback.from_user)
    order_id = int(callback.data.rsplit(":", 1)[-1])  # type: ignore[union-attr]
    db = await _get_db()
    async with db:
        user, created = await check_user(db, callback.from_user)
        if created:
            await db.commit()
        if not has_operator_access(user.role):
            await callback.answer(translate("manager-access-denied"), show_alert=True)
            return
        order = await OrderRepository(db).get_one(order_id)

    if order is None or order.status != int(OrderStatus.CREATED):
        await callback.answer(translate("manager-new-orders-empty"), show_alert=True)
        return

    chat_url = build_chat_url_for_user(order.user)
    await _safe_edit_text(
        callback.message,
        build_manager_status_text(order),
        reply_markup=manager_order_open_chat(order_id=order.id, chat_url=chat_url),
    )
    await callback.answer()


@router.message(Command("on"))
async def cmd_on(message: Message) -> None:
    translate = get_user_translator(message.from_user)
    db = await _get_db()
    async with db:
        user, _ = await check_user(db, message.from_user)
        if not has_admin_access(user.role):
            return
        repo = ConfigRepository(db)
        config = await repo.get_or_create()
        if not config.enabled:
            await repo.toggle_enabled()
            await db.commit()
    await message.answer(messages.bot_turned_on(translator=translate))


@router.message(Command("off"))
async def cmd_off(message: Message) -> None:
    translate = get_user_translator(message.from_user)
    db = await _get_db()
    async with db:
        user, _ = await check_user(db, message.from_user)
        if not has_admin_access(user.role):
            return
        repo = ConfigRepository(db)
        config = await repo.get_or_create()
        if config.enabled:
            await repo.toggle_enabled()
            await db.commit()
    await message.answer(messages.bot_turned_off(translator=translate))
