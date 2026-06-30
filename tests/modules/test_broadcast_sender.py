from __future__ import annotations

import pytest

from app.modules.broadcasts.sender import AiogramBroadcastSender
from app.telegram import bot as telegram_bot


class _FakeSession:
    def __init__(self) -> None:
        self.closed = False

    async def close(self) -> None:
        self.closed = True


class _FakeBot:
    def __init__(self) -> None:
        self.session = _FakeSession()
        self.sent_messages: list[dict[str, object]] = []

    async def send_message(self, **kwargs) -> None:
        self.sent_messages.append(kwargs)


@pytest.mark.asyncio
async def test_broadcast_sender_closes_temporary_bot_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_bot = _FakeBot()
    monkeypatch.setattr(telegram_bot, "bot", None)
    monkeypatch.setattr(telegram_bot, "dp", None)
    monkeypatch.setattr(telegram_bot, "_create_bot", lambda: fake_bot)

    await AiogramBroadcastSender().send_message(
        chat_id=101,
        text="Новости AntEx",
        button_text=None,
        button_url=None,
        allow_paid_broadcast=False,
    )

    assert fake_bot.sent_messages[0]["chat_id"] == 101
    assert fake_bot.session.closed is True
    assert telegram_bot.bot is None


@pytest.mark.asyncio
async def test_broadcast_sender_reuses_initialized_bot_without_closing_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_bot = _FakeBot()
    monkeypatch.setattr(telegram_bot, "bot", fake_bot)

    await AiogramBroadcastSender().send_message(
        chat_id=202,
        text="Новости AntEx",
        button_text="Открыть",
        button_url="https://example.test",
        allow_paid_broadcast=True,
    )

    assert fake_bot.sent_messages[0]["chat_id"] == 202
    assert fake_bot.session.closed is False
