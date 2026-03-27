"""FastAPI приложение AntEx."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.api.routers import admin, auth, banks, cards, exchange, public, telegram, users
from app.core.config import settings
from app.core.rate_limit import limiter
from app.core.security_headers import SecurityHeadersMiddleware
from app.exceptions import AntExException

logging.basicConfig(level=settings.log_level.upper())
logger = logging.getLogger(__name__)


def _log_background_task_result(task: asyncio.Task[None]) -> None:
    if task.cancelled():
        return

    try:
        exception = task.exception()
    except asyncio.CancelledError:
        return

    if exception is not None:
        logger.error("Telegram polling task failed", exc_info=exception)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator:
    logger.info("Starting AntEx...")
    app.state.telegram_polling_task = None
    app.state.telegram_polling_stop_event = None

    if settings.telegram_mode == "polling":
        from app.telegram.bot import run_polling_supervisor

        stop_event = asyncio.Event()
        task = asyncio.create_task(
            run_polling_supervisor(stop_event=stop_event),
            name="telegram-polling",
        )
        task.add_done_callback(_log_background_task_result)
        app.state.telegram_polling_stop_event = stop_event
        app.state.telegram_polling_task = task
    elif settings.telegram_mode == "webhook":
        from app.telegram.bot import set_webhook

        webhook_url = f"{settings.telegram_webhook_host}{settings.telegram_webhook_path}"
        await set_webhook(webhook_url, settings.telegram_webhook_secret)
        logger.info("Webhook set: %s", webhook_url)

    yield

    logger.info("Shutting down AntEx...")
    if settings.telegram_mode == "polling":
        from app.telegram.bot import close_bot_session

        stop_event = app.state.telegram_polling_stop_event
        task = app.state.telegram_polling_task
        if stop_event is not None:
            stop_event.set()
        if task is not None:
            try:
                await asyncio.wait_for(task, timeout=5)
            except (TimeoutError, asyncio.CancelledError):
                pass
            except Exception:
                logger.warning("Telegram polling task had already failed before shutdown")
            if not task.done():
                task.cancel()
                with suppress(asyncio.CancelledError):
                    await task
        await close_bot_session()
    elif settings.telegram_mode == "webhook":
        from app.telegram.bot import delete_webhook

        await delete_webhook()


app = FastAPI(
    title=settings.app_name,
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs" if settings.app_env != "production" else None,
    redoc_url="/redoc" if settings.app_env != "production" else None,
)

# Rate limiting
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

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
app.include_router(exchange.router)
app.include_router(cards.router)
app.include_router(banks.router)
app.include_router(admin.router)
app.include_router(public.router)
app.include_router(telegram.router)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "app": settings.app_name}
