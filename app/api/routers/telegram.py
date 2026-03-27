"""Роутер webhook Telegram."""

from __future__ import annotations

import hmac
import logging

from aiogram.types import Update
from fastapi import APIRouter, Header, HTTPException, Request

from app.core.config import settings
from app.telegram import bot as telegram_bot

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/telegram", tags=["telegram"])


@router.post("/webhook")
async def telegram_webhook(
    request: Request,
    x_telegram_bot_api_secret_token: str | None = Header(default=None),
) -> dict:
    if settings.telegram_mode != "webhook":
        logger.warning("Received Telegram webhook while mode is not webhook")
        return {"ok": True}

    if settings.telegram_webhook_secret:
        expected = settings.telegram_webhook_secret
        if not hmac.compare_digest(x_telegram_bot_api_secret_token or "", expected):
            raise HTTPException(status_code=403, detail="Invalid webhook secret")

    if telegram_bot.bot is None or telegram_bot.dp is None:
        raise HTTPException(status_code=503, detail="Bot is not initialized")

    body = await request.json()
    update = Update.model_validate(body)
    await telegram_bot.dp.feed_update(bot=telegram_bot.bot, update=update)
    return {"ok": True}
