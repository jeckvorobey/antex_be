"""Инициализация и управление Telegram ботом."""

from __future__ import annotations

import asyncio
import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress
from urllib.parse import quote

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramConflictError, TelegramNetworkError
from aiogram.fsm.storage.redis import RedisStorage
from aiohttp import ClientError

from app.core.config import settings
from app.core.redis import redis_client
from app.telegram.handlers import exchange, operator, start
from app.telegram.middlewares.logging import LoggingMiddleware

logger = logging.getLogger(__name__)
DEFAULT_POLLING_RETRY_DELAY = 1.0
MAX_POLLING_RETRY_DELAY = 30.0
POLLING_LOCK_TTL_SECONDS = 30
POLLING_LOCK_RETRY_DELAY = 5.0

storage = RedisStorage(redis=redis_client)

bot: Bot | None = None
dp: Dispatcher | None = None
polling_task: asyncio.Task[None] | None = None
_bot_identity_cache: dict[str, int | str | None] | None = None
_polling_lock_lost: asyncio.Event | None = None


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
    global bot, dp, _bot_identity_cache

    if bot is not None and dp is not None:
        logger.info("Telegram bot is already initialized")
        return bot, dp

    if not settings.telegram_bot_token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is not configured")

    bot = _create_bot()
    dp = _create_dispatcher()
    _bot_identity_cache = None
    logger.info(
        "Telegram bot initialized: mode=%s, proxy=%s",
        settings.telegram_mode,
        bool(settings.proxy),
    )
    return bot, dp


async def start_polling() -> None:
    global polling_task

    if bot is None or dp is None:
        raise RuntimeError("Telegram bot is not initialized")
    if polling_task is not None and not polling_task.done():
        logger.info("Telegram polling already running")
        return

    identity = await _get_safe_bot_identity()
    logger.info(
        "Starting Telegram bot in polling mode: bot_id=%s username=%s webhook_active=%s",
        identity.get("id"),
        identity.get("username"),
        False,
    )
    _log_local_polling_reload_warning()
    try:
        logger.info("Deleting Telegram webhook before polling start")
        await bot.delete_webhook(drop_pending_updates=False)
        logger.info(
            "Telegram webhook deleted before polling: bot_id=%s username=%s",
            identity.get("id"),
            identity.get("username"),
        )
    except Exception:
        logger.exception(
            "Failed to delete Telegram webhook before polling: bot_id=%s username=%s",
            identity.get("id"),
            identity.get("username"),
        )
        raise
    polling_task = asyncio.create_task(
        _run_polling_singleton(),
        name="telegram-polling",
    )
    polling_task.add_done_callback(_log_polling_task_result)
    logger.info("Telegram polling task created")


async def _run_polling_singleton() -> None:
    global _polling_lock_lost

    if bot is None or dp is None:
        raise RuntimeError("Telegram bot is not initialized")

    identity = await _get_safe_bot_identity()
    owner = _build_polling_lock_owner(identity)

    while True:
        _polling_lock_lost = asyncio.Event()
        acquired = await _acquire_polling_lock(owner)
        if not acquired:
            logger.warning(
                "Telegram polling lock is already owned by another backend process: "
                "bot_id=%s username=%s retry_delay=%s",
                identity.get("id"),
                identity.get("username"),
                POLLING_LOCK_RETRY_DELAY,
            )
            await asyncio.sleep(POLLING_LOCK_RETRY_DELAY)
            continue

        await _renew_polling_lock(owner)
        renew_task = asyncio.create_task(
            _renew_polling_lock_loop(owner),
            name="telegram-polling-lock-renew",
        )
        try:
            await _run_polling_with_retry()
            return
        finally:
            renew_task.cancel()
            with suppress(asyncio.CancelledError):
                await renew_task
            await _release_polling_lock(owner)
            _polling_lock_lost = None


async def _run_polling_with_retry() -> None:
    if bot is None or dp is None:
        raise RuntimeError("Telegram bot is not initialized")

    delay = DEFAULT_POLLING_RETRY_DELAY
    attempt = 0

    while True:
        if _polling_lock_lost is not None and _polling_lock_lost.is_set():
            logger.info("Telegram polling exiting: lock ownership lost")
            return

        try:
            attempt += 1
            allowed_updates = dp.resolve_used_update_types()
            identity = await _get_safe_bot_identity()
            logger.info(
                "Telegram polling loop started: bot_id=%s username=%s attempt=%s "
                "allowed_updates=%s",
                identity.get("id"),
                identity.get("username"),
                attempt,
                allowed_updates,
            )
            await dp.start_polling(
                bot,
                allowed_updates=allowed_updates,
                handle_signals=False,
                close_bot_session=False,
            )
            logger.info("Telegram polling loop stopped")
            return
        except asyncio.CancelledError:
            logger.info("Telegram polling loop cancelled")
            raise
        except TelegramConflictError as exc:
            if _polling_lock_lost is not None and _polling_lock_lost.is_set():
                logger.info("Telegram polling exiting: lock ownership lost during conflict")
                return
            identity = await _get_safe_bot_identity()
            logger.warning(
                "Telegram polling conflict during rolling update or another active polling "
                "client: bot_id=%s username=%s attempt=%s retry_delay=%s error=%s",
                identity.get("id"),
                identity.get("username"),
                attempt,
                delay,
                exc,
            )
            await asyncio.sleep(delay)
            delay = min(delay * 2, MAX_POLLING_RETRY_DELAY)
        except (TelegramNetworkError, ClientError, OSError) as exc:
            if _polling_lock_lost is not None and _polling_lock_lost.is_set():
                logger.info("Telegram polling exiting: lock ownership lost during network error")
                return
            logger.warning("Telegram polling connection failed: %s", exc)
            await bot.session.close()
            await asyncio.sleep(delay)
            delay = min(delay * 2, MAX_POLLING_RETRY_DELAY)


def _polling_lock_key() -> str:
    """Возвращает Redis key, который ограничивает polling одним владельцем."""
    return "antex:telegram:polling:lock"


def _build_polling_lock_owner(identity: dict[str, int | str | None]) -> str:
    """Формирует безопасный идентификатор владельца polling lock."""
    bot_id = identity.get("id") or "unknown"
    return f"{bot_id}:{os.getpid()}:{id(bot)}"


async def _acquire_polling_lock(owner: str) -> bool:
    """Пытается занять Redis-lock для polling без блокировки event loop."""
    return bool(
        await redis_client.set(
            _polling_lock_key(),
            owner,
            ex=POLLING_LOCK_TTL_SECONDS,
            nx=True,
        )
    )


async def _renew_polling_lock(owner: str) -> bool:
    """Продлевает polling lock, только если текущий процесс остается владельцем."""
    if await redis_client.get(_polling_lock_key()) != owner:
        return False
    return bool(await redis_client.expire(_polling_lock_key(), POLLING_LOCK_TTL_SECONDS))


async def _renew_polling_lock_loop(owner: str) -> None:
    """Периодически продлевает polling lock во время активного getUpdates."""
    delay = max(POLLING_LOCK_TTL_SECONDS / 3, 1)
    while True:
        await asyncio.sleep(delay)
        renewed = await _renew_polling_lock(owner)
        if not renewed:
            logger.warning("Telegram polling lock ownership was lost; polling will stop")
            if _polling_lock_lost is not None:
                _polling_lock_lost.set()
            if dp is not None:
                await dp.stop_polling()
            return


async def _release_polling_lock(owner: str) -> None:
    """Освобождает polling lock, если он все еще принадлежит текущему процессу."""
    if await redis_client.get(_polling_lock_key()) == owner:
        await redis_client.delete(_polling_lock_key())


async def start_webhook() -> None:
    if bot is None or dp is None:
        raise RuntimeError("Telegram bot is not initialized")
    if not settings.telegram_webhook_url:
        raise ValueError("TELEGRAM_WEBHOOK_URL is not configured")

    logger.info("Setting Telegram webhook: url=%s", settings.telegram_webhook_url)
    await bot.set_webhook(
        url=settings.telegram_webhook_url,
        secret_token=settings.telegram_webhook_secret,
    )
    logger.info("Telegram webhook set")


async def stop_bot() -> None:
    global bot, dp, polling_task, _bot_identity_cache, _polling_lock_lost

    if _polling_lock_lost is not None:
        _polling_lock_lost.set()

    current_task = polling_task

    if current_task is not None:
        logger.info("Stopping Telegram polling task")
        if dp is not None and not current_task.done():
            try:
                await dp.stop_polling()
            except RuntimeError:
                logger.warning("Telegram polling was not running during shutdown")

        if not current_task.done():
            logger.info("Cancelling Telegram polling task")
            current_task.cancel()

        try:
            await asyncio.wait_for(current_task, timeout=3.0)
        except (TimeoutError, asyncio.CancelledError):
            pass
        except Exception:
            logger.warning("Telegram polling task had already failed before shutdown")

    if bot is not None and bot.session is not None:
        logger.info("Closing Telegram bot session")
        await bot.session.close()

    polling_task = None
    dp = None
    bot = None
    _bot_identity_cache = None
    logger.info("Telegram bot stopped")


@asynccontextmanager
async def sender_bot() -> AsyncIterator[Bot]:
    """Возвращает bot для разовой отправки и закрывает временную session."""
    if bot is not None:
        yield bot
        return

    temporary_bot = _create_bot()
    try:
        yield temporary_bot
    finally:
        if temporary_bot.session is not None:
            await temporary_bot.session.close()


def _log_local_polling_reload_warning() -> None:
    """Логирует локальный риск двойного polling при автоперезагрузке."""
    if settings.app_env == "production":
        return
    if os.environ.get("ANTEX_UVICORN_RELOAD") != "1":
        return
    logger.warning(
        "Telegram polling is running with local reload enabled; only one active process per "
        "bot token can poll Telegram. Use `uv run python run.py --no-reload` for local polling "
        "or switch to a webhook-safe setup."
    )


async def _get_safe_bot_identity() -> dict[str, int | str | None]:
    """Возвращает безопасные идентификаторы бота без token и proxy data."""
    global _bot_identity_cache

    if _bot_identity_cache is not None:
        return _bot_identity_cache

    if bot is None:
        return {"id": None, "username": None}

    bot_id = getattr(bot, "id", None)
    username = getattr(bot, "username", None)
    if bot_id is not None or username is not None:
        _bot_identity_cache = {"id": bot_id, "username": username}
        return _bot_identity_cache

    try:
        me = await bot.get_me()
    except Exception as exc:
        logger.warning(
            "Failed to load Telegram bot identity: error_type=%s",
            type(exc).__name__,
        )
        return {"id": None, "username": None}

    _bot_identity_cache = {"id": getattr(me, "id", None), "username": getattr(me, "username", None)}
    return _bot_identity_cache
