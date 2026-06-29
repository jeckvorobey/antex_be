from __future__ import annotations

import asyncio
import logging
from types import SimpleNamespace

import pytest
from aiogram.exceptions import TelegramConflictError
from aiogram.methods import GetUpdates

from app.telegram import bot as telegram_bot


class _FakeSession:
    def __init__(self) -> None:
        self.closed = False

    async def close(self) -> None:
        self.closed = True


class _FakeBot:
    def __init__(self) -> None:
        self.id = 12345
        self.username = "antex_test_bot"
        self.session = _FakeSession()


class _IdentityLookupBot:
    def __init__(self, *, error: Exception | None = None) -> None:
        self.session = _FakeSession()
        self.calls = 0
        self.error = error

    async def get_me(self):
        self.calls += 1
        if self.error is not None:
            raise self.error
        return SimpleNamespace(id=54321, username="loaded_identity_bot")


class _ConflictDispatcher:
    def __init__(self) -> None:
        self.calls = 0

    def resolve_used_update_types(self) -> list[str]:
        return ["message"]

    async def start_polling(self, *_args, **_kwargs) -> None:
        self.calls += 1
        raise TelegramConflictError(
            method=GetUpdates(),
            message="terminated by other getUpdates request",
        )


@pytest.mark.asyncio
async def test_polling_conflict_logs_rolling_update_reason_and_retries(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    fake_bot = _FakeBot()
    dispatcher = _ConflictDispatcher()
    monkeypatch.setattr(telegram_bot, "bot", fake_bot)
    monkeypatch.setattr(telegram_bot, "dp", dispatcher)

    async def _stop_after_first_retry(_delay: float) -> None:
        raise asyncio.CancelledError

    monkeypatch.setattr(telegram_bot.asyncio, "sleep", _stop_after_first_retry)

    with (
        caplog.at_level(logging.WARNING, logger="app.telegram.bot"),
        pytest.raises(asyncio.CancelledError),
    ):
        await telegram_bot._run_polling_with_retry()

    assert dispatcher.calls == 1
    assert "rolling update" in caplog.text
    assert "another active polling client" in caplog.text
    assert "attempt=1" in caplog.text


@pytest.mark.asyncio
async def test_safe_bot_identity_uses_cached_get_me_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_bot = _IdentityLookupBot()
    monkeypatch.setattr(telegram_bot, "bot", fake_bot)
    monkeypatch.setattr(telegram_bot, "_bot_identity_cache", None)

    first = await telegram_bot._get_safe_bot_identity()
    second = await telegram_bot._get_safe_bot_identity()

    assert first == {"id": 54321, "username": "loaded_identity_bot"}
    assert second == first
    assert fake_bot.calls == 1


@pytest.mark.asyncio
async def test_safe_bot_identity_failure_does_not_log_proxy_url(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    error = RuntimeError("proxy http://user:password@example.test:8080 failed")
    fake_bot = _IdentityLookupBot(error=error)
    monkeypatch.setattr(telegram_bot, "bot", fake_bot)
    monkeypatch.setattr(telegram_bot, "_bot_identity_cache", None)

    with caplog.at_level(logging.WARNING, logger="app.telegram.bot"):
        identity = await telegram_bot._get_safe_bot_identity()

    assert identity == {"id": None, "username": None}
    assert "RuntimeError" in caplog.text
    assert "user:password" not in caplog.text
    assert "example.test" not in caplog.text
