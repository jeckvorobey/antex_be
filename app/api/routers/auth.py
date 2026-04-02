"""Роутер аутентификации Telegram."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import DbDep
from app.schemas.auth import TelegramAuthRequest, TokenResponse
from app.services.auth import telegram_auth

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/telegram", response_model=TokenResponse)
async def auth_telegram(body: TelegramAuthRequest, db: DbDep) -> TokenResponse:
    token = await telegram_auth(db, body.init_data)
    await db.commit()
    return token
