"""FastAPI приложение AntEx."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

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


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    logger.info("Starting AntEx...")
    if settings.telegram_mode == "polling":
        import asyncio
        from app.telegram.bot import start_polling
        asyncio.create_task(start_polling())
    elif settings.telegram_mode == "webhook":
        from app.telegram.bot import set_webhook
        webhook_url = f"{settings.telegram_webhook_host}{settings.telegram_webhook_path}"
        await set_webhook(webhook_url, settings.telegram_webhook_secret)
        logger.info("Webhook set: %s", webhook_url)

    yield

    logger.info("Shutting down AntEx...")
    if settings.telegram_mode == "webhook":
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
