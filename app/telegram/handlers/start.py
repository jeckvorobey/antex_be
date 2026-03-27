"""Обработчик /start и основного меню."""

from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command, CommandStart
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.repositories.config import ConfigRepository
from app.telegram import messages
from app.telegram.keyboards import home, menu_operator
from app.telegram.services.user_service import check_user

router = Router(name="start")


async def _get_db() -> AsyncSession:
    async for session in get_db_session():
        return session


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    db = await _get_db()
    async with db:
        config_repo = ConfigRepository(db)
        config = await config_repo.get_or_create()

        user, _ = await check_user(db, message.from_user)
        await db.commit()

    if not config.enabled:
        await message.answer(messages.bot_disabled())
        return

    from app.enums.user import UserRole
    kb = menu_operator() if user.role >= UserRole.OPERATOR else home()
    await message.answer(messages.welcome(message.from_user.first_name), reply_markup=kb)


@router.message(Command("on"))
async def cmd_on(message: Message) -> None:
    db = await _get_db()
    async with db:
        from app.enums.user import UserRole
        user, _ = await check_user(db, message.from_user)
        if user.role < UserRole.ADMIN:
            return
        repo = ConfigRepository(db)
        config = await repo.get_or_create()
        if not config.enabled:
            await repo.toggle_enabled()
            await db.commit()
    await message.answer("✅ Бот включён.")


@router.message(Command("off"))
async def cmd_off(message: Message) -> None:
    db = await _get_db()
    async with db:
        from app.enums.user import UserRole
        user, _ = await check_user(db, message.from_user)
        if user.role < UserRole.ADMIN:
            return
        repo = ConfigRepository(db)
        config = await repo.get_or_create()
        if config.enabled:
            await repo.toggle_enabled()
            await db.commit()
    await message.answer("🔴 Бот выключен.")
