"""Роутер пользователей."""

from __future__ import annotations

import logging

from fastapi import APIRouter
from sqlalchemy import select

from app.api.deps import CurrentUser, DbDep
from app.models.attribution import UserAcquisition
from app.repositories.user import UserRepository
from app.schemas.user import (
    TelegramWriteAccessRequest,
    TelegramWriteAccessResponse,
    UserOut,
    build_user_out,
)

router = APIRouter(prefix="/api/users", tags=["users"])
logger = logging.getLogger(__name__)


@router.get("/me", response_model=UserOut)
async def get_me(user: CurrentUser, db: DbDep) -> UserOut:
    referred_by: int | None = None
    acquisition = await db.scalar(
        select(UserAcquisition.referrer_user_id).where(
            UserAcquisition.user_id == user.id,
            UserAcquisition.source_type == "referral",
        )
    )
    if acquisition is not None:
        referred_by = acquisition
    return build_user_out(user, referred_by=referred_by)


@router.post("/me/telegram-write-access", response_model=TelegramWriteAccessResponse)
async def update_telegram_write_access(
    body: TelegramWriteAccessRequest,
    user: CurrentUser,
    db: DbDep,
) -> TelegramWriteAccessResponse:
    """Сохраняет native write-access outcome только для текущего bearer-пользователя."""
    allowed = body.status == "allowed"
    await UserRepository(db).set_telegram_write_access(user.id, allowed)
    await db.commit()
    logger.info(
        "Telegram write access outcome: user_id=%s telegram_id=%s status=%s "
        "telegram_write_access=%s",
        user.id,
        user.telegram_id,
        body.status,
        allowed,
    )
    return TelegramWriteAccessResponse(telegram_write_access=allowed)
