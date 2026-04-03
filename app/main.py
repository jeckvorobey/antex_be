"""FastAPI приложение AntEx."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routers import (
    admin,
    auth,
    miniapp,
    orders,
    public,
    telegram,
    users,
)
from app.core.config import settings
from app.core.security_headers import SecurityHeadersMiddleware
from app.exceptions import AntExException

logging.basicConfig(level=settings.log_level.upper())
logger = logging.getLogger(__name__)


async def _rate_updater_loop() -> None:
    """Фоновая задача: периодически обновляет курсы из CoinGecko."""
    from app.core.database import async_session
    from app.services.rate_fetcher import fetch_and_save_rates

    while True:
        try:
            async with async_session() as db:
                rates = await fetch_and_save_rates(db)
            logger.info("Курсы обновлены: %s", rates)
        except Exception:
            ttl = settings.rate_cache_ttl_seconds
            logger.exception("Ошибка обновления курсов, повтор через %ds", ttl)
        await asyncio.sleep(settings.rate_cache_ttl_seconds)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator:
    logger.info("Starting AntEx...")
    bot_started = False

    if settings.telegram_bot_token:
        from app.telegram import bot as telegram_bot

        await telegram_bot.init_bot()
        if settings.telegram_mode == "polling":
            await telegram_bot.start_polling()
        else:
            await telegram_bot.start_webhook()
        bot_started = True
    else:
        logger.warning("TELEGRAM_BOT_TOKEN is not configured, Telegram bot startup skipped")

    rate_task = asyncio.create_task(_rate_updater_loop())

    try:
        yield
    finally:
        rate_task.cancel()
        logger.info("Shutting down AntEx...")
        if bot_started:
            from app.telegram import bot as telegram_bot

            try:
                await telegram_bot.stop_bot()
            except Exception:
                logger.exception("Failed to stop Telegram bot cleanly")


app = FastAPI(
    title=settings.app_name,
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs" if settings.app_env != "production" else None,
    redoc_url="/redoc" if settings.app_env != "production" else None,
)

# Security headers
app.add_middleware(
    SecurityHeadersMiddleware,
    enable_hsts=settings.app_env == "production",
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.backend_cors_origins,
    allow_credentials=settings.cors_allow_credentials,
    allow_methods=settings.cors_allow_methods,
    allow_headers=settings.cors_allow_headers,
)


# Exception handler
@app.exception_handler(AntExException)
async def antex_exception_handler(request: Request, exc: AntExException) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"code": exc.code, "message": exc.message, "params": exc.params},
    )


# Routers
app.include_router(auth.router)
app.include_router(users.router)
app.include_router(orders.router)
app.include_router(miniapp.router)
app.include_router(admin.router)
app.include_router(public.router)
app.include_router(telegram.router)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "app": settings.app_name}
