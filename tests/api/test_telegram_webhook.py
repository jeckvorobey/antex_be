from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
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
    monkeypatch.setattr(telegram_bot, "dp", SimpleNamespace(feed_update=AsyncMock()))

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/telegram/webhook",
            headers={"X-Telegram-Bot-Api-Secret-Token": "wrong-token"},
            json={"update_id": 1},
        )

    assert response.status_code == 403
    telegram_bot.dp.feed_update.assert_not_awaited()


@pytest.mark.asyncio
async def test_telegram_webhook_feeds_update_with_valid_secret(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    feed_update = AsyncMock()
    bot = object()
    monkeypatch.setattr(settings, "telegram_mode", "webhook")
    monkeypatch.setattr(settings, "telegram_webhook_secret", "secret-token")
    monkeypatch.setattr(telegram_bot, "bot", bot)
    monkeypatch.setattr(telegram_bot, "dp", SimpleNamespace(feed_update=feed_update))

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
