"""Инициализация aiogram Bot + Dispatcher."""

from __future__ import annotations

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.redis import RedisStorage

from app.core.config import settings
from app.core.redis import redis_client
from app.telegram.handlers import exchange, operator, start
from app.telegram.middlewares.logging import LoggingMiddleware

storage = RedisStorage(redis=redis_client)

bot = Bot(
    token=settings.telegram_bot_token,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML),
)

dp = Dispatcher(storage=storage)

# Регистрация middleware
dp.message.middleware(LoggingMiddleware())
dp.callback_query.middleware(LoggingMiddleware())

# Регистрация роутеров
dp.include_router(start.router)
dp.include_router(exchange.router)
dp.include_router(operator.router)


async def start_polling() -> None:
    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())


async def set_webhook(url: str, secret: str | None = None) -> None:
    await bot.set_webhook(url=url, secret_token=secret)


async def delete_webhook() -> None:
    await bot.delete_webhook(drop_pending_updates=True)
