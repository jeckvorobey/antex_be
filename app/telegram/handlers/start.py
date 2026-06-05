"""Start and basic menu handlers."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandStart
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import create_db_session
from app.enums.user import has_admin_access, has_operator_access
from app.repositories.config import ConfigRepository
from app.repositories.site_lead import SiteLeadRepository
from app.services.site_lead_notifications import build_site_lead_manager_text
from app.telegram import messages
from app.telegram.i18n import get_user_translator
from app.telegram.keyboards import home, manager_home, manager_site_leads_list
from app.telegram.services.user_service import check_user

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
async def cmd_start(message: Message) -> None:
    translate = get_user_translator(message.from_user)
    db = await _get_db()
    async with db:
        config_repo = ConfigRepository(db)
        config = await config_repo.get_or_create()

        user, _ = await check_user(db, message.from_user)
        await db.commit()

    if not config.enabled:
        await message.answer(messages.bot_disabled(translator=translate))
        return

    reply_markup = manager_home(translate) if has_operator_access(user.role) else home(translate)
    await message.answer(
        messages.welcome(message.from_user.first_name, translator=translate),
        reply_markup=reply_markup,
    )


@router.callback_query(F.data == "manager:site_leads")
async def manager_site_leads(callback: CallbackQuery) -> None:
    translate = get_user_translator(callback.from_user)
    db = await _get_db()
    async with db:
        user, created = await check_user(db, callback.from_user)
        if created:
            await db.commit()
        if not has_operator_access(user.role):
            await callback.answer(translate("manager-access-denied"), show_alert=True)
            return
        leads = await SiteLeadRepository(db).list_recent(limit=10)

    if not leads:
        await _safe_edit_text(
            callback.message,
            translate("manager-site-leads-empty"),
            reply_markup=manager_home(translate),
        )
    else:
        await _safe_edit_text(
            callback.message,
            translate("manager-site-leads-header"),
            reply_markup=manager_site_leads_list(translate, leads),
        )
    await callback.answer()


@router.callback_query(F.data.startswith("manager:site_lead:"))
async def manager_site_lead_detail(callback: CallbackQuery) -> None:
    translate = get_user_translator(callback.from_user)
    lead_id = int(callback.data.rsplit(":", 1)[-1])  # type: ignore[union-attr]
    db = await _get_db()
    async with db:
        user, created = await check_user(db, callback.from_user)
        if created:
            await db.commit()
        if not has_operator_access(user.role):
            await callback.answer(translate("manager-access-denied"), show_alert=True)
            return
        lead = await SiteLeadRepository(db).get_by_id(lead_id)

    if lead is None:
        await callback.answer(translate("manager-site-leads-empty"), show_alert=True)
        return

    await _safe_edit_text(
        callback.message,
        build_site_lead_manager_text(lead),
        reply_markup=manager_site_leads_list(translate, [lead]),
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
