"""Роутер webhook Telegram."""

from __future__ import annotations

import hmac
import logging
import time

from aiogram.types import Update
from fastapi import APIRouter, Header, HTTPException, Request

from app.core.config import settings
from app.telegram import bot as telegram_bot

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/telegram", tags=["telegram"])
WEBHOOK_DISPATCH_TIMEOUT_SECONDS = 1.0


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
            logger.warning("Rejected Telegram webhook: invalid secret")
            raise HTTPException(status_code=403, detail="Invalid webhook secret")

    if telegram_bot.bot is None or telegram_bot.dp is None:
        logger.error("Telegram webhook received before bot initialization")
        raise HTTPException(status_code=503, detail="Bot is not initialized")

    received_at = time.perf_counter()
    body = await request.json()
    update_id = body.get("update_id")
    logger.info("Telegram webhook received: update_id=%s", update_id)
    update = Update.model_validate(body)
    dispatch_started_at = time.perf_counter()
    await telegram_bot.dp.feed_webhook_update(
        bot=telegram_bot.bot,
        update=update,
        _timeout=WEBHOOK_DISPATCH_TIMEOUT_SECONDS,
    )
    dispatch_duration_ms = (time.perf_counter() - dispatch_started_at) * 1000
    ack_duration_ms = (time.perf_counter() - received_at) * 1000
    logger.info(
        "Telegram webhook dispatched: update_id=%s, dispatch_duration_ms=%.2f, "
        "ack_duration_ms=%.2f",
        update.update_id,
        dispatch_duration_ms,
        ack_duration_ms,
    )
    return {"ok": True}
