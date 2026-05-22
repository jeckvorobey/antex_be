"""Инициализация и управление Telegram ботом."""

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

bot: Bot | None = None
dp: Dispatcher | None = None
polling_task: asyncio.Task[None] | None = None


def parse_proxy_value(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        value = value[1:-1].strip()

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


def _create_bot() -> Bot:
    session = None
    if settings.proxy:
        session = AiohttpSession(proxy=parse_proxy_value(settings.proxy))

    return Bot(
        token=settings.telegram_bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
        session=session,
    )


def _create_dispatcher() -> Dispatcher:
    dispatcher = Dispatcher(storage=storage)
    dispatcher.message.middleware(LoggingMiddleware())
    dispatcher.callback_query.middleware(LoggingMiddleware())
    dispatcher.include_router(start.router)
    dispatcher.include_router(exchange.router)
    dispatcher.include_router(operator.router)
    return dispatcher


def _log_polling_task_result(task: asyncio.Task[None]) -> None:
    if task.cancelled():
        return

    try:
        exception = task.exception()
    except asyncio.CancelledError:
        return

    if exception is not None:
        logger.error("Telegram polling task failed", exc_info=exception)


async def init_bot() -> tuple[Bot, Dispatcher]:
    global bot, dp

    if bot is not None and dp is not None:
        return bot, dp

    if not settings.telegram_bot_token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is not configured")

    bot = _create_bot()
    dp = _create_dispatcher()
    return bot, dp


async def start_polling() -> None:
    global polling_task

    if bot is None or dp is None:
        raise RuntimeError("Telegram bot is not initialized")
    if polling_task is not None and not polling_task.done():
        return

    await bot.delete_webhook(drop_pending_updates=False)
    polling_task = asyncio.create_task(
        _run_polling_with_retry(),
        name="telegram-polling",
    )
    polling_task.add_done_callback(_log_polling_task_result)


async def _run_polling_with_retry() -> None:
    if bot is None or dp is None:
        raise RuntimeError("Telegram bot is not initialized")

    delay = DEFAULT_POLLING_RETRY_DELAY

    while True:
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
            await asyncio.sleep(delay)
            delay = min(delay * 2, MAX_POLLING_RETRY_DELAY)


async def start_webhook() -> None:
    if bot is None or dp is None:
        raise RuntimeError("Telegram bot is not initialized")
    if not settings.telegram_webhook_url:
        raise ValueError("TELEGRAM_WEBHOOK_URL is not configured")

    await bot.set_webhook(
        url=settings.telegram_webhook_url,
        secret_token=settings.telegram_webhook_secret,
    )


async def stop_bot() -> None:
    global bot, dp, polling_task

    current_task = polling_task

    if current_task is not None:
        if dp is not None and not current_task.done():
            try:
                await dp.stop_polling()
            except RuntimeError:
                logger.warning("Telegram polling was not running during shutdown")

        if not current_task.done():
            current_task.cancel()

        try:
            await asyncio.wait_for(current_task, timeout=3.0)
        except (TimeoutError, asyncio.CancelledError):
            pass
        except Exception:
            logger.warning("Telegram polling task had already failed before shutdown")

    if settings.telegram_mode == "webhook" and bot is not None:
        await bot.delete_webhook()

    if bot is not None and bot.session is not None:
        await bot.session.close()

    polling_task = None
    dp = None
    bot = None
