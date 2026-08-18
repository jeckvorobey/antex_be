from __future__ import annotations

import asyncio
import logging
from types import SimpleNamespace

import pytest
from aiogram import Router
from aiogram.exceptions import TelegramConflictError
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.methods import GetUpdates
from aiogram.types import Update

from app.telegram import bot as telegram_bot
from app.telegram.exceptions import TelegramCaptureRetryError
from app.telegram.handlers import chat as chat_handler


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


class _AckAwareDispatcher:
    def __init__(self) -> None:
        self.polling_kwargs: dict[str, object] = {}

    def resolve_used_update_types(self) -> list[str]:
        return ["message"]

    async def start_polling(self, *_args, **kwargs) -> None:
        self.polling_kwargs = kwargs
        raise asyncio.CancelledError


class _OffsetAdvanced(BaseException):
    """Останавливает probe, если polling уже запросил следующий offset."""


class _OffsetProbeBot:
    def __init__(self) -> None:
        self.id = 123456
        self.session = SimpleNamespace(timeout=None)
        self.update: Update | None = None
        self.requested_offsets: list[int | None] = []

    async def me(self):
        return SimpleNamespace(username="antex_test_bot", full_name="AntEx Test Bot")

    async def __call__(self, method, **_kwargs):
        self.requested_offsets.append(method.offset)
        if len(self.requested_offsets) == 1:
            assert self.update is not None
            return [self.update]
        raise _OffsetAdvanced


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
async def test_polling_process_propagates_capture_failure_before_offset_ack(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Polling transport не подтверждает update при ошибке manager chat capture."""
    memory_storage = MemoryStorage()
    monkeypatch.setattr(telegram_bot, "storage", memory_storage)
    monkeypatch.setattr(telegram_bot.start, "router", Router())
    monkeypatch.setattr(telegram_bot.exchange, "router", Router())
    monkeypatch.setattr(telegram_bot.operator, "router", Router())
    dispatcher = telegram_bot._create_dispatcher()
    dispatcher.message.register(chat_handler.capture_unhandled_private_message)
    bot = _OffsetProbeBot()

    async def fail_capture(_message, *, edited: bool = False) -> None:
        assert edited is False
        raise RuntimeError("temporary capture outage")

    monkeypatch.setattr(chat_handler, "_capture", fail_capture)
    bot.update = Update.model_validate(
        {
            "update_id": 501,
            "message": {
                "message_id": 41,
                "date": 1_717_871_000,
                "chat": {"id": 777, "type": "private", "first_name": "Tester"},
                "from": {"id": 777, "is_bot": False, "first_name": "Tester"},
                "text": "Привет",
            },
        },
        context={"bot": bot},
    )

    try:
        with pytest.raises(TelegramCaptureRetryError) as exc_info:
            await dispatcher._polling(bot, handle_as_tasks=False)
    finally:
        await memory_storage.close()

    assert isinstance(exc_info.value.__cause__, RuntimeError)
    assert bot.requested_offsets == [None]


@pytest.mark.asyncio
async def test_polling_waits_for_processing_before_requesting_next_offset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Polling обрабатывает update последовательно до подтверждения offset."""
    fake_bot = _FakeBot()
    dispatcher = _AckAwareDispatcher()
    monkeypatch.setattr(telegram_bot, "bot", fake_bot)
    monkeypatch.setattr(telegram_bot, "dp", dispatcher)

    with pytest.raises(asyncio.CancelledError):
        await telegram_bot._run_polling_with_retry()

    assert dispatcher.polling_kwargs["handle_as_tasks"] is False


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
