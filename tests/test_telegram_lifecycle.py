"""Тесты Telegram lifecycle и proxy-конфига."""

from __future__ import annotations

import asyncio
from unittest.mock import Mock

import pytest
from aiogram.exceptions import TelegramNetworkError

from app import main as app_main
from app.telegram import bot as telegram_bot


def test_parse_proxy_value_from_compact_format() -> None:
    proxy = telegram_bot.parse_proxy_value("135.106.25.252:63488:jhtD1E2e:jUWKgx2U")

    assert proxy == "http://jhtD1E2e:jUWKgx2U@135.106.25.252:63488"


def test_parse_proxy_value_rejects_invalid_format() -> None:
    with pytest.raises(ValueError, match="PROXY"):
        telegram_bot.parse_proxy_value("bad-proxy-value")


@pytest.mark.asyncio
async def test_run_polling_supervisor_retries_after_network_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, object]] = []
    close_calls = 0

    async def fake_start_polling(*_args, **kwargs):
        calls.append(kwargs)
        if len(calls) == 1:
            raise TelegramNetworkError(method=Mock(), message="network down")

    async def fake_close() -> None:
        nonlocal close_calls
        close_calls += 1

    async def fake_sleep(_delay: float) -> None:
        return None

    monkeypatch.setattr(telegram_bot.dp, "start_polling", fake_start_polling)
    monkeypatch.setattr(telegram_bot.bot.session, "close", fake_close)
    monkeypatch.setattr(telegram_bot.asyncio, "sleep", fake_sleep)

    await telegram_bot.run_polling_supervisor(retry_delay=0.1, max_retry_delay=0.1)

    assert len(calls) == 2
    assert calls[0]["handle_signals"] is False
    assert calls[0]["close_bot_session"] is False
    assert close_calls == 1


@pytest.mark.asyncio
async def test_lifespan_tracks_and_stops_polling_task(monkeypatch: pytest.MonkeyPatch) -> None:
    original_mode = app_main.settings.telegram_mode
    seen_stop_events: list[asyncio.Event] = []

    async def fake_polling_supervisor(*, stop_event: asyncio.Event, **_kwargs) -> None:
        seen_stop_events.append(stop_event)
        await stop_event.wait()

    monkeypatch.setattr(app_main.settings, "telegram_mode", "polling")
    monkeypatch.setattr(telegram_bot, "run_polling_supervisor", fake_polling_supervisor)

    try:
        async with app_main.lifespan(app_main.app):
            task = app_main.app.state.telegram_polling_task
            stop_event = app_main.app.state.telegram_polling_stop_event
            await asyncio.sleep(0)

            assert task.done() is False
            assert stop_event.is_set() is False
            assert seen_stop_events == [stop_event]

        assert task.done() is True
        assert stop_event.is_set() is True
    finally:
        monkeypatch.setattr(app_main.settings, "telegram_mode", original_mode)


@pytest.mark.asyncio
async def test_lifespan_shutdown_closes_bot_session_after_polling_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_mode = app_main.settings.telegram_mode
    close_calls = 0

    async def failing_polling_supervisor(*, stop_event: asyncio.Event, **_kwargs) -> None:
        del stop_event
        raise RuntimeError("polling failed")

    async def fake_close_bot_session() -> None:
        nonlocal close_calls
        close_calls += 1

    monkeypatch.setattr(app_main.settings, "telegram_mode", "polling")
    monkeypatch.setattr(telegram_bot, "run_polling_supervisor", failing_polling_supervisor)
    monkeypatch.setattr(telegram_bot, "close_bot_session", fake_close_bot_session)

    try:
        async with app_main.lifespan(app_main.app):
            await asyncio.sleep(0)

        assert close_calls == 1
    finally:
        monkeypatch.setattr(app_main.settings, "telegram_mode", original_mode)
