"""Тесты start handler."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.enums.user import UserRole
from app.telegram.handlers import start


class DummySession:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        del exc_type, exc, tb

    async def commit(self) -> None:
        return None


@pytest.mark.asyncio
async def test_cmd_start_shows_disabled_message(
    monkeypatch: pytest.MonkeyPatch,
    mock_message,
) -> None:
    async def fake_get_db():
        return DummySession()

    class DummyConfigRepo:
        def __init__(self, db) -> None:
            del db

        async def get_or_create(self):
            return SimpleNamespace(enabled=False)

    async def fake_check_user(db, from_user):
        del db, from_user
        return SimpleNamespace(role=UserRole.USER), False

    monkeypatch.setattr(start, "_get_db", fake_get_db)
    monkeypatch.setattr(start, "ConfigRepository", DummyConfigRepo)
    monkeypatch.setattr(start, "check_user", fake_check_user)

    await start.cmd_start(mock_message)

    assert mock_message.bot.last_message is not None
    text = mock_message.bot.last_message.text.lower()
    assert "bot" in text or "бот" in text


@pytest.mark.asyncio
async def test_cmd_start_user_gets_home_keyboard(
    monkeypatch: pytest.MonkeyPatch,
    mock_message,
) -> None:
    async def fake_get_db():
        return DummySession()

    class DummyConfigRepo:
        def __init__(self, db) -> None:
            del db

        async def get_or_create(self):
            return SimpleNamespace(enabled=True)

    async def fake_check_user(db, from_user):
        del db, from_user
        return SimpleNamespace(role=UserRole.USER), False

    monkeypatch.setattr(start, "_get_db", fake_get_db)
    monkeypatch.setattr(start, "ConfigRepository", DummyConfigRepo)
    monkeypatch.setattr(start, "check_user", fake_check_user)

    await start.cmd_start(mock_message)

    sent = mock_message.bot.last_message
    assert sent is not None
    callbacks = [
        btn.callback_data
        for row in sent.reply_markup.inline_keyboard
        for btn in row
    ]
    assert "menu:exchange" in callbacks


@pytest.mark.asyncio
async def test_cmd_start_operator_gets_operator_keyboard(
    monkeypatch: pytest.MonkeyPatch,
    mock_message,
) -> None:
    async def fake_get_db():
        return DummySession()

    class DummyConfigRepo:
        def __init__(self, db) -> None:
            del db

        async def get_or_create(self):
            return SimpleNamespace(enabled=True)

    async def fake_check_user(db, from_user):
        del db, from_user
        return SimpleNamespace(role=UserRole.OPERATOR), False

    monkeypatch.setattr(start, "_get_db", fake_get_db)
    monkeypatch.setattr(start, "ConfigRepository", DummyConfigRepo)
    monkeypatch.setattr(start, "check_user", fake_check_user)

    await start.cmd_start(mock_message)

    sent = mock_message.bot.last_message
    assert sent is not None
    callbacks = [
        btn.callback_data
        for row in sent.reply_markup.inline_keyboard
        for btn in row
    ]
    assert "menu:orders" in callbacks


@pytest.mark.asyncio
async def test_cmd_on_toggles_for_admin(
    monkeypatch: pytest.MonkeyPatch,
    mock_message,
) -> None:
    async def fake_get_db():
        return DummySession()

    class DummyConfigRepo:
        def __init__(self, db) -> None:
            del db
            self.toggled = False

        async def get_or_create(self):
            return SimpleNamespace(enabled=False)

        async def toggle_enabled(self):
            self.toggled = True
            return SimpleNamespace(enabled=True)

    async def fake_check_user(db, from_user):
        del db, from_user
        return SimpleNamespace(role=UserRole.ADMIN), False

    monkeypatch.setattr(start, "_get_db", fake_get_db)
    monkeypatch.setattr(start, "ConfigRepository", DummyConfigRepo)
    monkeypatch.setattr(start, "check_user", fake_check_user)

    await start.cmd_on(mock_message)

    assert mock_message.bot.last_message is not None


@pytest.mark.asyncio
async def test_cmd_off_toggles_for_admin(
    monkeypatch: pytest.MonkeyPatch,
    mock_message,
) -> None:
    async def fake_get_db():
        return DummySession()

    class DummyConfigRepo:
        def __init__(self, db) -> None:
            del db
            self.toggled = False

        async def get_or_create(self):
            return SimpleNamespace(enabled=True)

        async def toggle_enabled(self):
            self.toggled = True
            return SimpleNamespace(enabled=False)

    async def fake_check_user(db, from_user):
        del db, from_user
        return SimpleNamespace(role=UserRole.ADMIN), False

    monkeypatch.setattr(start, "_get_db", fake_get_db)
    monkeypatch.setattr(start, "ConfigRepository", DummyConfigRepo)
    monkeypatch.setattr(start, "check_user", fake_check_user)

    await start.cmd_off(mock_message)

    assert mock_message.bot.last_message is not None
