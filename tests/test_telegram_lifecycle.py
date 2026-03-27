"""Тесты Telegram lifecycle и proxy-конфига."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from aiogram.exceptions import TelegramNetworkError
from fastapi import HTTPException

from app import main as app_main
from app.api.routers import telegram as telegram_router
from app.telegram import bot as telegram_bot


def test_parse_proxy_value_from_compact_format() -> None:
    proxy = telegram_bot.parse_proxy_value("135.106.25.252:63488:jhtD1E2e:jUWKgx2U")

    assert proxy == "http://jhtD1E2e:jUWKgx2U@135.106.25.252:63488"


def test_parse_proxy_value_rejects_invalid_format() -> None:
    with pytest.raises(ValueError, match="PROXY"):
        telegram_bot.parse_proxy_value("bad-proxy-value")


@pytest.mark.asyncio
async def test_start_polling_creates_background_task(monkeypatch: pytest.MonkeyPatch) -> None:
    delete_calls: list[bool] = []
    started = asyncio.Event()
    release = asyncio.Event()

    class DummyDispatcher:
        def resolve_used_update_types(self) -> list[str]:
            return ["message"]

        async def start_polling(self, *args, **kwargs) -> None:
            del args, kwargs
            started.set()
            await release.wait()

        async def stop_polling(self) -> None:
            release.set()

    class DummySession:
        async def close(self) -> None:
            return None

    class DummyBot:
        def __init__(self) -> None:
            self.session = DummySession()

        async def delete_webhook(self, *, drop_pending_updates: bool = False) -> None:
            delete_calls.append(drop_pending_updates)

    monkeypatch.setattr(telegram_bot, "dp", DummyDispatcher())
    monkeypatch.setattr(telegram_bot, "bot", DummyBot())
    monkeypatch.setattr(telegram_bot, "polling_task", None)

    await telegram_bot.start_polling()
    await started.wait()

    assert telegram_bot.polling_task is not None
    assert telegram_bot.polling_task.done() is False
    assert delete_calls == [False]

    await telegram_bot.stop_bot()

    assert telegram_bot.polling_task is None
    assert telegram_bot.bot is None
    assert telegram_bot.dp is None


@pytest.mark.asyncio
async def test_start_polling_retries_after_network_error(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, object]] = []
    close_calls = 0
    sleep_delays: list[float] = []
    release = asyncio.Event()

    class DummyDispatcher:
        def resolve_used_update_types(self) -> list[str]:
            return ["message"]

        async def start_polling(self, *args, **kwargs) -> None:
            del args
            calls.append(kwargs)
            if len(calls) == 1:
                raise TelegramNetworkError(method=Mock(), message="network down")
            await release.wait()

        async def stop_polling(self) -> None:
            release.set()

    class DummySession:
        async def close(self) -> None:
            nonlocal close_calls
            close_calls += 1

    class DummyBot:
        def __init__(self) -> None:
            self.session = DummySession()

        async def delete_webhook(self, *, drop_pending_updates: bool = False) -> None:
            del drop_pending_updates

    original_sleep = telegram_bot.asyncio.sleep

    async def fake_sleep(delay: float) -> None:
        sleep_delays.append(delay)
        await original_sleep(0)

    monkeypatch.setattr(telegram_bot, "dp", DummyDispatcher())
    monkeypatch.setattr(telegram_bot, "bot", DummyBot())
    monkeypatch.setattr(telegram_bot, "polling_task", None)
    monkeypatch.setattr(telegram_bot.asyncio, "sleep", fake_sleep)

    await telegram_bot.start_polling()
    await original_sleep(0)
    await original_sleep(0)

    assert telegram_bot.polling_task is not None
    assert telegram_bot.polling_task.done() is False
    assert len(calls) == 2
    assert calls[0]["handle_signals"] is False
    assert calls[0]["close_bot_session"] is False
    assert sleep_delays == [telegram_bot.DEFAULT_POLLING_RETRY_DELAY]
    assert close_calls == 1

    await telegram_bot.stop_bot()


@pytest.mark.asyncio
async def test_lifespan_uses_init_start_stop_flow(monkeypatch: pytest.MonkeyPatch) -> None:
    original_mode = app_main.settings.telegram_mode
    original_token = app_main.settings.telegram_bot_token
    calls: list[str] = []

    async def fake_init_bot() -> tuple[object, object]:
        calls.append("init")
        return object(), object()

    async def fake_start_polling() -> None:
        calls.append("start_polling")

    async def fake_start_webhook() -> None:
        calls.append("start_webhook")

    async def fake_stop_bot() -> None:
        calls.append("stop")

    monkeypatch.setattr(app_main.settings, "telegram_mode", "polling")
    monkeypatch.setattr(app_main.settings, "telegram_bot_token", "test-token")
    monkeypatch.setattr(telegram_bot, "init_bot", fake_init_bot)
    monkeypatch.setattr(telegram_bot, "start_polling", fake_start_polling)
    monkeypatch.setattr(telegram_bot, "start_webhook", fake_start_webhook)
    monkeypatch.setattr(telegram_bot, "stop_bot", fake_stop_bot)

    try:
        async with app_main.lifespan(app_main.app):
            assert calls == ["init", "start_polling"]

        assert calls == ["init", "start_polling", "stop"]
    finally:
        monkeypatch.setattr(app_main.settings, "telegram_mode", original_mode)
        monkeypatch.setattr(app_main.settings, "telegram_bot_token", original_token)


@pytest.mark.asyncio
async def test_lifespan_skips_bot_start_without_token(monkeypatch: pytest.MonkeyPatch) -> None:
    original_mode = app_main.settings.telegram_mode
    original_token = app_main.settings.telegram_bot_token

    async def fail_init_bot() -> tuple[object, object]:
        raise AssertionError("init_bot must not be called without token")

    async def fail_start_polling() -> None:
        raise AssertionError("start_polling must not be called without token")

    async def fail_stop_bot() -> None:
        raise AssertionError("stop_bot must not be called without token")

    monkeypatch.setattr(app_main.settings, "telegram_mode", "polling")
    monkeypatch.setattr(app_main.settings, "telegram_bot_token", None)
    monkeypatch.setattr(telegram_bot, "init_bot", fail_init_bot)
    monkeypatch.setattr(telegram_bot, "start_polling", fail_start_polling)
    monkeypatch.setattr(telegram_bot, "stop_bot", fail_stop_bot)

    try:
        async with app_main.lifespan(app_main.app):
            pass
    finally:
        monkeypatch.setattr(app_main.settings, "telegram_mode", original_mode)
        monkeypatch.setattr(app_main.settings, "telegram_bot_token", original_token)


@pytest.mark.asyncio
async def test_webhook_accepts_raw_secret_token(monkeypatch: pytest.MonkeyPatch) -> None:
    feed_calls: list[tuple[object, object]] = []
    original_mode = telegram_router.settings.telegram_mode
    original_secret = telegram_router.settings.telegram_webhook_secret

    class DummyRequest:
        async def json(self) -> dict[str, object]:
            return {"update_id": 1}

    class DummyUpdate:
        @classmethod
        def model_validate(cls, payload: dict[str, object]) -> object:
            return payload

    async def fake_feed_update(*, bot: object, update: object) -> None:
        feed_calls.append((bot, update))

    monkeypatch.setattr(telegram_router.settings, "telegram_mode", "webhook")
    monkeypatch.setattr(telegram_router.settings, "telegram_webhook_secret", "plain-secret")
    monkeypatch.setattr(telegram_router, "Update", DummyUpdate)
    monkeypatch.setattr(telegram_bot, "bot", object())
    monkeypatch.setattr(telegram_bot, "dp", SimpleNamespace(feed_update=fake_feed_update))

    try:
        response = await telegram_router.telegram_webhook(
            DummyRequest(),
            x_telegram_bot_api_secret_token="plain-secret",
        )
    finally:
        monkeypatch.setattr(telegram_router.settings, "telegram_mode", original_mode)
        monkeypatch.setattr(telegram_router.settings, "telegram_webhook_secret", original_secret)

    assert response == {"ok": True}
    assert len(feed_calls) == 1


@pytest.mark.asyncio
async def test_webhook_requires_initialized_bot(monkeypatch: pytest.MonkeyPatch) -> None:
    original_mode = telegram_router.settings.telegram_mode
    original_secret = telegram_router.settings.telegram_webhook_secret

    class DummyRequest:
        async def json(self) -> dict[str, object]:
            return {"update_id": 1}

    monkeypatch.setattr(telegram_router.settings, "telegram_mode", "webhook")
    monkeypatch.setattr(telegram_router.settings, "telegram_webhook_secret", None)
    monkeypatch.setattr(telegram_bot, "bot", None)
    monkeypatch.setattr(telegram_bot, "dp", None)

    try:
        with pytest.raises(HTTPException, match="Bot is not initialized"):
            await telegram_router.telegram_webhook(
                DummyRequest(),
                x_telegram_bot_api_secret_token=None,
            )
    finally:
        monkeypatch.setattr(telegram_router.settings, "telegram_mode", original_mode)
        monkeypatch.setattr(telegram_router.settings, "telegram_webhook_secret", original_secret)
