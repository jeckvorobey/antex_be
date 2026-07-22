"""FastAPI приложение AntEx."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncGenerator, Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routers import (
    admin,
    aex,
    auth,
    broadcasts,
    marketing,
    miniapp,
    orders,
    public,
    referral,
    telegram,
    users,
)
from app.core.config import settings
from app.core.logging import configure_logging
from app.core.security_headers import SecurityHeadersMiddleware
from app.exceptions import AntExException

configure_logging(
    log_dir=settings.log_dir,
    log_level=settings.log_level,
    log_file_max_bytes=settings.log_file_max_bytes,
    log_file_backup_count=settings.log_file_backup_count,
)
logger = logging.getLogger(__name__)


async def _initialize_rates_if_needed(
    db: AsyncSession,
    *,
    fetch_rates: Callable[[AsyncSession], Awaitable[dict[str, float]]] | None = None,
) -> bool:
    """Обновляет курсы на старте, если обязательный набор пар неполон."""
    from app.repositories.rate import RateRepository
    from app.services.rate_fetcher import EXPECTED_RATE_CURRENCIES, fetch_and_save_rates

    if await RateRepository(db).has_all_currencies(EXPECTED_RATE_CURRENCIES):
        logger.info("Полный набор курсов уже есть в БД, стартовый парсинг пропущен")
        return False

    rates = await (fetch_rates or fetch_and_save_rates)(db)
    logger.info("Стартовая инициализация курсов выполнена: %s", rates)
    return True


async def _rate_updater_loop() -> None:
    """Фоновая задача: периодически обновляет курсы из CurrencyBeacon."""
    from app.core.database import async_session
    from app.services.rate_fetcher import fetch_and_save_rates

    while True:
        await asyncio.sleep(settings.rate_cache_ttl_seconds)
        try:
            async with async_session() as db:
                rates = await fetch_and_save_rates(db)
            logger.info("Курсы обновлены: %s", rates)
        except Exception:
            ttl = settings.rate_cache_ttl_seconds
            logger.exception("Ошибка обновления курсов, повтор через %ds", ttl)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator:
    logger.info("Starting AntEx...")
    bot_started = False

    if settings.telegram_bot_token:
        from app.telegram import bot as telegram_bot

        logger.info("Starting Telegram bot in %s mode", settings.telegram_mode)
        await telegram_bot.init_bot()
        if settings.telegram_mode == "polling":
            await telegram_bot.start_polling()
        else:
            await telegram_bot.start_webhook()
        bot_started = True
    else:
        logger.warning("TELEGRAM_BOT_TOKEN is not configured, Telegram bot startup skipped")

    from app.modules.broadcasts.runner import recover_stale_broadcasts_on_startup

    await recover_stale_broadcasts_on_startup()

    from app.core.database import async_session

    try:
        async with async_session() as db:
            await _initialize_rates_if_needed(db)
    except Exception:
        logger.exception("Ошибка стартовой инициализации курсов")

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
app.include_router(aex.router)
app.include_router(aex.admin_router)
app.include_router(referral.router)
app.include_router(broadcasts.router)
app.include_router(marketing.router)
app.include_router(public.router)
app.include_router(telegram.router)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "app": settings.app_name}
