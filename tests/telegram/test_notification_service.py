"""Тесты notification service."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from aiogram.exceptions import TelegramForbiddenError

from app.telegram.services import notification_service


@pytest.mark.asyncio
async def test_notify_operator_skips_without_chat_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(notification_service.settings, "operator_chat_id", None)
    bot = AsyncMock()

    await notification_service.notify_operator(bot, 1, 2, 3, "RUB", 4, "THB", "cash")

    bot.send_message.assert_not_called()


@pytest.mark.asyncio
async def test_notify_operator_sends_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(notification_service.settings, "operator_chat_id", 100)
    bot = AsyncMock()

    await notification_service.notify_operator(bot, 1, 2, 3, "RUB", 4, "THB", "cash")

    bot.send_message.assert_awaited_once()


@pytest.mark.asyncio
async def test_notify_user_handles_forbidden(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class DummyBot:
        async def send_message(self, chat_id: int, text: str):
            del chat_id, text
            raise TelegramForbiddenError(method=AsyncMock(), message="blocked")

    await notification_service.notify_user(DummyBot(), 1, "text")
