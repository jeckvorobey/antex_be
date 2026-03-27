"""Инициализация aiogram Bot + Dispatcher."""

from __future__ import annotations

import asyncio
import logging
from urllib.parse import quote

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramNetworkError
from aiogram.fsm.storage.redis import RedisStorage
from aiohttp import ClientError

from app.core.config import settings
from app.core.redis import redis_client
from app.telegram.handlers import exchange, operator, start
from app.telegram.middlewares.logging import LoggingMiddleware

logger = logging.getLogger(__name__)
DEFAULT_POLLING_RETRY_DELAY = 1.0
MAX_POLLING_RETRY_DELAY = 30.0

storage = RedisStorage(redis=redis_client)


def parse_proxy_value(value: str) -> str:
    value = value.strip()
    if "://" in value:
        return value

    parts = value.split(":")
    if len(parts) != 4:
        msg = "PROXY должен быть в формате host:port:user:pass или proxy URL"
        raise ValueError(msg)

    host, port, username, password = parts
    if not all((host, port, username, password)):
        msg = "PROXY содержит пустые части"
        raise ValueError(msg)
    if not port.isdigit():
        msg = "PROXY содержит некорректный порт"
        raise ValueError(msg)

    return f"http://{quote(username, safe='')}:{quote(password, safe='')}@{host}:{port}"


def create_bot() -> Bot:
    session = None
    if settings.proxy:
        session = AiohttpSession(proxy=parse_proxy_value(settings.proxy))

    return Bot(
        token=settings.telegram_bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
        session=session,
    )


bot = create_bot()

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


async def run_polling_supervisor(
    *,
    stop_event: asyncio.Event | None = None,
    retry_delay: float = DEFAULT_POLLING_RETRY_DELAY,
    max_retry_delay: float = MAX_POLLING_RETRY_DELAY,
) -> None:
    delay = retry_delay

    while True:
        if stop_event and stop_event.is_set():
            return
        try:
            await dp.start_polling(
                bot,
                allowed_updates=dp.resolve_used_update_types(),
                handle_signals=False,
                close_bot_session=False,
            )
            return
        except asyncio.CancelledError:
            raise
        except (TelegramNetworkError, ClientError, OSError) as exc:
            logger.warning("Telegram polling connection failed: %s", exc)
            await bot.session.close()
            if stop_event and stop_event.is_set():
                return
            if stop_event:
                try:
                    await asyncio.wait_for(stop_event.wait(), timeout=delay)
                    return
                except TimeoutError:
                    delay = min(delay * 2, max_retry_delay)
                    continue

            await asyncio.sleep(delay)
            delay = min(delay * 2, max_retry_delay)
        except Exception:
            logger.exception("Unexpected Telegram polling error")
            raise


async def set_webhook(url: str, secret: str | None = None) -> None:
    await bot.set_webhook(url=url, secret_token=secret)


async def delete_webhook() -> None:
    await bot.delete_webhook(drop_pending_updates=True)


async def close_bot_session() -> None:
    await bot.session.close()
