"""Start and basic menu handlers."""

from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command, CommandStart
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.enums.user import has_admin_access, has_operator_access
from app.repositories.config import ConfigRepository
from app.telegram import messages
from app.telegram.i18n import get_user_translator
from app.telegram.keyboards import home, menu_operator
from app.telegram.services.user_service import check_user

router = Router(name="start")


async def _get_db() -> AsyncSession:
    async for session in get_db_session():
        return session


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

    kb = menu_operator(translate) if has_operator_access(user.role) else home(translate)
    await message.answer(
        messages.welcome(message.from_user.first_name, translator=translate),
        reply_markup=kb,
    )


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
