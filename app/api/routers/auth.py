"""Роутер аутентификации Telegram."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import CurrentUser, DbDep
from app.schemas.auth import (
    TelegramAuthRequest,
    TokenResponse,
    TrustedContactResponse,
    TrustedContactUpdate,
)
from app.services.auth import resolve_trusted_contact, save_trusted_phone, telegram_auth

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/telegram", response_model=TokenResponse)
async def auth_telegram(body: TelegramAuthRequest, db: DbDep) -> TokenResponse:
    token = await telegram_auth(db, body.init_data)
    await db.commit()
    return token


@router.get("/contact", response_model=TrustedContactResponse)
async def get_trusted_contact(user: CurrentUser) -> TrustedContactResponse:
    return resolve_trusted_contact(user)


@router.put("/contact", response_model=TrustedContactResponse)
async def update_trusted_contact(
    body: TrustedContactUpdate,
    user: CurrentUser,
    db: DbDep,
) -> TrustedContactResponse:
    trusted_contact = await save_trusted_phone(db, user.id, body.phone)
    await db.commit()
    return trusted_contact
