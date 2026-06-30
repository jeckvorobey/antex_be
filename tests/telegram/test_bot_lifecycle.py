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
        self.delete_webhook_called = False

    async def delete_webhook(self, *, drop_pending_updates: bool) -> None:
        del drop_pending_updates
        self.delete_webhook_called = True


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


class _IdleDispatcher:
    def __init__(self) -> None:
        self.polling_calls = 0
        self.stopped = False

    def resolve_used_update_types(self) -> list[str]:
        return ["message"]

    async def start_polling(self, *_args, **_kwargs) -> None:
        self.polling_calls += 1

    async def stop_polling(self) -> None:
        self.stopped = True


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
async def test_start_polling_warns_about_local_reload_risk(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    fake_bot = _FakeBot()
    created_tasks: list[asyncio.Task] = []
    monkeypatch.setattr(telegram_bot, "bot", fake_bot)
    monkeypatch.setattr(telegram_bot, "dp", _IdleDispatcher())
    monkeypatch.setattr(telegram_bot, "polling_task", None)
    monkeypatch.setenv("ANTEX_UVICORN_RELOAD", "1")

    async def _run_forever() -> None:
        await asyncio.Event().wait()

    monkeypatch.setattr(telegram_bot, "_run_polling_singleton", _run_forever)

    with caplog.at_level(logging.WARNING, logger="app.telegram.bot"):
        await telegram_bot.start_polling()

    task = telegram_bot.polling_task
    assert task is not None
    created_tasks.append(task)
    assert "polling" in caplog.text
    assert "reload" in caplog.text
    assert "--no-reload" in caplog.text

    for created_task in created_tasks:
        created_task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await created_task
    monkeypatch.setattr(telegram_bot, "polling_task", None)


@pytest.mark.asyncio
async def test_polling_waits_without_get_updates_when_redis_lock_is_busy(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    fake_bot = _FakeBot()
    dispatcher = _IdleDispatcher()
    monkeypatch.setattr(telegram_bot, "bot", fake_bot)
    monkeypatch.setattr(telegram_bot, "dp", dispatcher)

    async def _lock_busy(_owner: str) -> bool:
        return False

    async def _stop_after_wait(_delay: float) -> None:
        del _delay
        raise asyncio.CancelledError

    monkeypatch.setattr(telegram_bot, "_acquire_polling_lock", _lock_busy)
    monkeypatch.setattr(telegram_bot.asyncio, "sleep", _stop_after_wait)

    with (
        caplog.at_level(logging.WARNING, logger="app.telegram.bot"),
        pytest.raises(asyncio.CancelledError),
    ):
        await telegram_bot._run_polling_singleton()

    assert dispatcher.polling_calls == 0
    assert "polling lock" in caplog.text


@pytest.mark.asyncio
async def test_polling_lock_is_renewed_and_released_by_owner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_bot = _FakeBot()
    dispatcher = _IdleDispatcher()
    renewed: list[str] = []
    released: list[str] = []
    monkeypatch.setattr(telegram_bot, "bot", fake_bot)
    monkeypatch.setattr(telegram_bot, "dp", dispatcher)

    async def _lock_acquired(owner: str) -> bool:
        return True

    async def _renew(owner: str) -> bool:
        renewed.append(owner)
        return True

    async def _release(owner: str) -> None:
        released.append(owner)

    async def _stop_after_renew(_delay: float) -> None:
        del _delay
        raise asyncio.CancelledError

    monkeypatch.setattr(telegram_bot, "_acquire_polling_lock", _lock_acquired)
    monkeypatch.setattr(telegram_bot, "_renew_polling_lock", _renew)
    monkeypatch.setattr(telegram_bot, "_release_polling_lock", _release)
    monkeypatch.setattr(telegram_bot.asyncio, "sleep", _stop_after_renew)

    await telegram_bot._run_polling_singleton()

    assert dispatcher.polling_calls == 1
    assert renewed
    assert released == renewed[:1]


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
