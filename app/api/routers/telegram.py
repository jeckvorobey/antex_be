"""Роутер webhook Telegram."""

from __future__ import annotations

import hashlib
import hmac
import logging

from fastapi import APIRouter, Header, HTTPException, Request

from app.core.config import settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/telegram", tags=["telegram"])


@router.post("/webhook")
async def telegram_webhook(
    request: Request,
    x_telegram_bot_api_secret_token: str | None = Header(default=None),
) -> dict:
    if settings.telegram_webhook_secret:
        expected = hashlib.sha256(settings.telegram_webhook_secret.encode()).hexdigest()
        if not hmac.compare_digest(x_telegram_bot_api_secret_token or "", expected):
            raise HTTPException(status_code=403, detail="Invalid webhook secret")

    from app.telegram.bot import dp, bot
    body = await request.json()
    from aiogram.types import Update
    update = Update.model_validate(body)
    await dp.feed_update(bot=bot, update=update)
    return {"ok": True}
