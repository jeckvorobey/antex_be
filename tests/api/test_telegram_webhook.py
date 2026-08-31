from __future__ import annotations

import asyncio
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from aiogram import Bot, Dispatcher
from httpx import ASGITransport, AsyncClient

from app.core.config import settings
from app.main import app
from app.telegram import bot as telegram_bot


@pytest.fixture(autouse=True)
def reset_telegram_bot(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(telegram_bot, "bot", None)
    monkeypatch.setattr(telegram_bot, "dp", None)
    monkeypatch.setattr(telegram_bot, "polling_task", None)


@pytest.mark.asyncio
async def test_start_webhook_sets_url_and_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    bot = SimpleNamespace(set_webhook=AsyncMock())
    monkeypatch.setattr(telegram_bot, "bot", bot)
    monkeypatch.setattr(telegram_bot, "dp", object())
    monkeypatch.setattr(settings, "telegram_webhook_host", "https://example.com")
    monkeypatch.setattr(settings, "telegram_webhook_path", "/telegram/webhook")
    monkeypatch.setattr(settings, "telegram_webhook_secret", "secret-token")

    await telegram_bot.start_webhook()

    bot.set_webhook.assert_awaited_once_with(
        url="https://example.com/telegram/webhook",
        secret_token="secret-token",
    )


@pytest.mark.asyncio
async def test_telegram_webhook_rejects_invalid_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "telegram_mode", "webhook")
    monkeypatch.setattr(settings, "telegram_webhook_secret", "secret-token")
    monkeypatch.setattr(telegram_bot, "bot", object())
    monkeypatch.setattr(telegram_bot, "dp", SimpleNamespace(feed_webhook_update=AsyncMock()))

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/telegram/webhook",
            headers={"X-Telegram-Bot-Api-Secret-Token": "wrong-token"},
            json={"update_id": 1},
        )

    assert response.status_code == 403
    telegram_bot.dp.feed_webhook_update.assert_not_awaited()


@pytest.mark.asyncio
async def test_telegram_webhook_rejects_missing_secret_even_with_initialized_bot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Webhook никогда не принимает update без настроенного секрета."""
    feed_webhook_update = AsyncMock()
    monkeypatch.setattr(settings, "telegram_mode", "webhook")
    monkeypatch.setattr(settings, "telegram_webhook_secret", None)
    monkeypatch.setattr(telegram_bot, "bot", object())
    monkeypatch.setattr(
        telegram_bot,
        "dp",
        SimpleNamespace(feed_webhook_update=feed_webhook_update),
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/telegram/webhook", json={"update_id": 1})

    assert response.status_code == 503
    feed_webhook_update.assert_not_awaited()


@pytest.mark.asyncio
async def test_telegram_webhook_feeds_webhook_update_with_valid_secret(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    feed_update = AsyncMock()
    bot = object()
    monkeypatch.setattr(settings, "telegram_mode", "webhook")
    monkeypatch.setattr(settings, "telegram_webhook_secret", "secret-token")
    monkeypatch.setattr(telegram_bot, "bot", bot)
    monkeypatch.setattr(
        telegram_bot,
        "dp",
        SimpleNamespace(feed_update=feed_update),
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/telegram/webhook",
            headers={"X-Telegram-Bot-Api-Secret-Token": "secret-token"},
            json={"update_id": 1},
        )

    assert response.status_code == 200
    feed_update.assert_awaited_once()
    assert feed_update.await_args.kwargs["bot"] is bot
    assert feed_update.await_args.kwargs["update"].update_id == 1


@pytest.mark.asyncio
@pytest.mark.filterwarnings("ignore:Detected slow response into webhook.:RuntimeWarning")
async def test_telegram_webhook_waits_for_slow_dispatcher_before_ack(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    handler_started = asyncio.Event()
    bot = Bot("123456:test-token")
    dispatcher = Dispatcher()

    @dispatcher.message()
    async def _slow_handler(message) -> None:
        handler_started.set()
        await asyncio.sleep(0.2)

    monkeypatch.setattr(settings, "telegram_mode", "webhook")
    monkeypatch.setattr(settings, "telegram_webhook_secret", "secret-token")
    monkeypatch.setattr(telegram_bot, "bot", bot)
    monkeypatch.setattr(telegram_bot, "dp", dispatcher)

    transport = ASGITransport(app=app)
    started_at = time.perf_counter()
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/telegram/webhook",
                headers={"X-Telegram-Bot-Api-Secret-Token": "secret-token"},
                json={
                    "update_id": 1,
                    "message": {
                        "message_id": 10,
                        "date": 1_717_871_000,
                        "chat": {"id": 777, "type": "private", "first_name": "Tester"},
                        "from": {
                            "id": 777,
                            "is_bot": False,
                            "first_name": "Tester",
                            "username": "tester",
                        },
                        "text": "/start",
                    },
                },
            )
        duration = time.perf_counter() - started_at
        await asyncio.wait_for(handler_started.wait(), timeout=0.1)
    finally:
        await bot.session.close()

    assert response.status_code == 200
    assert duration >= 0.18


@pytest.mark.asyncio
async def test_telegram_webhook_returns_error_after_slow_capture_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Webhook не отвечает 200, пока manager chat capture не завершён успешно."""
    from app.telegram.handlers import chat as chat_handler

    bot = Bot("123456:test-token")
    dispatcher = Dispatcher(disable_fsm=True)
    dispatcher.message.register(chat_handler.capture_unhandled_private_message)

    async def fail_capture(_message, *, edited: bool = False) -> None:
        assert edited is False
        await asyncio.sleep(0.02)
        raise RuntimeError("temporary capture outage")

    monkeypatch.setattr(chat_handler, "_capture", fail_capture)
    monkeypatch.setattr(settings, "telegram_mode", "webhook")
    monkeypatch.setattr(settings, "telegram_webhook_secret", "secret-token")
    monkeypatch.setattr(telegram_bot, "bot", bot)
    monkeypatch.setattr(telegram_bot, "dp", dispatcher)

    transport = ASGITransport(app=app, raise_app_exceptions=False)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/telegram/webhook",
                headers={"X-Telegram-Bot-Api-Secret-Token": "secret-token"},
                json={
                    "update_id": 502,
                    "message": {
                        "message_id": 42,
                        "date": 1_717_871_000,
                        "chat": {"id": 778, "type": "private", "first_name": "Tester"},
                        "from": {"id": 778, "is_bot": False, "first_name": "Tester"},
                        "text": "Привет",
                    },
                },
            )
            await asyncio.sleep(0.03)
    finally:
        await bot.session.close()

    assert response.status_code == 500


@pytest.mark.asyncio
async def test_telegram_webhook_acknowledges_unrelated_handler_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Обычная ошибка handler не превращается в бесконечный webhook redelivery."""
    bot = Bot("123456:test-token")
    dispatcher = Dispatcher(disable_fsm=True)

    @dispatcher.message()
    async def fail_unrelated_handler(_message) -> None:
        raise RuntimeError("unrelated handler failure")

    monkeypatch.setattr(settings, "telegram_mode", "webhook")
    monkeypatch.setattr(settings, "telegram_webhook_secret", "secret-token")
    monkeypatch.setattr(telegram_bot, "bot", bot)
    monkeypatch.setattr(telegram_bot, "dp", dispatcher)

    transport = ASGITransport(app=app, raise_app_exceptions=False)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/telegram/webhook",
                headers={"X-Telegram-Bot-Api-Secret-Token": "secret-token"},
                json={
                    "update_id": 503,
                    "message": {
                        "message_id": 43,
                        "date": 1_717_871_000,
                        "chat": {"id": 779, "type": "private", "first_name": "Tester"},
                        "from": {"id": 779, "is_bot": False, "first_name": "Tester"},
                        "text": "/unrelated",
                    },
                },
            )
    finally:
        await bot.session.close()

    assert response.status_code == 200
    assert response.json() == {"ok": True}


@pytest.mark.asyncio
async def test_stop_bot_closes_session_without_deleting_webhook(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = SimpleNamespace(close=AsyncMock())
    bot = SimpleNamespace(delete_webhook=AsyncMock(), session=session)
    monkeypatch.setattr(settings, "telegram_mode", "webhook")
    monkeypatch.setattr(telegram_bot, "bot", bot)
    monkeypatch.setattr(telegram_bot, "dp", object())
    monkeypatch.setattr(telegram_bot, "polling_task", None)

    await telegram_bot.stop_bot()

    bot.delete_webhook.assert_not_awaited()
    session.close.assert_awaited_once()
