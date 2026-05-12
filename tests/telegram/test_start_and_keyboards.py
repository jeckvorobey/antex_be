from __future__ import annotations

import os
from types import SimpleNamespace

from aiogram.types import User as TgUser

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")

from app.telegram.handlers import start as start_handler
from app.telegram.i18n import get_translator
from app.telegram.keyboards import home


class _FakeDbSession:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def commit(self) -> None:
        return None


class _FakeConfigRepo:
    def __init__(self, db) -> None:  # noqa: ANN001
        self.db = db

    async def get_or_create(self):
        return SimpleNamespace(enabled=True)


class _FakeMessage:
    def __init__(self, user: TgUser) -> None:
        self.from_user = user
        self.answers: list[dict[str, object]] = []

    async def answer(self, text: str, reply_markup=None) -> None:  # noqa: ANN001
        self.answers.append({"text": text, "reply_markup": reply_markup})


async def test_home_keyboard_without_webapp_url(monkeypatch) -> None:
    monkeypatch.setattr("app.telegram.keyboards.settings.frontend_webapp_url", None)

    kb = home(get_translator("ru"))

    assert len(kb.inline_keyboard) == 1
    assert len(kb.inline_keyboard[0]) == 2
    assert kb.inline_keyboard[0][0].callback_data == "menu:exchange"
    assert kb.inline_keyboard[0][1].callback_data == "menu:orders"


async def test_home_keyboard_with_webapp_url(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.telegram.keyboards.settings.frontend_webapp_url",
        "https://example.com/miniapp",
    )

    kb = home(get_translator("ru"))

    assert len(kb.inline_keyboard) == 2
    assert len(kb.inline_keyboard[1]) == 1
    assert kb.inline_keyboard[1][0].web_app is not None
    assert kb.inline_keyboard[1][0].web_app.url == "https://example.com/miniapp"


async def test_start_always_uses_home_keyboard(monkeypatch) -> None:
    user = TgUser(
        id=777,
        is_bot=False,
        first_name="Tester",
        last_name="User",
        username="tester",
        language_code="ru",
        is_premium=False,
    )
    message = _FakeMessage(user)

    fake_db = _FakeDbSession()

    async def _fake_get_db():
        return fake_db

    async def _fake_check_user(db, tg_user):  # noqa: ANN001
        return (SimpleNamespace(role=3), False)

    monkeypatch.setattr(start_handler, "_get_db", _fake_get_db)
    monkeypatch.setattr(start_handler, "ConfigRepository", _FakeConfigRepo)
    monkeypatch.setattr(start_handler, "check_user", _fake_check_user)
    monkeypatch.setattr("app.telegram.keyboards.settings.frontend_webapp_url", "https://example.com/app")

    await start_handler.cmd_start(message)

    assert len(message.answers) == 1
    reply_markup = message.answers[0]["reply_markup"]
    assert reply_markup is not None
    assert len(reply_markup.inline_keyboard) == 2
    assert reply_markup.inline_keyboard[0][0].callback_data == "menu:exchange"
    assert reply_markup.inline_keyboard[0][1].callback_data == "menu:orders"
    assert reply_markup.inline_keyboard[1][0].web_app is not None
    assert reply_markup.inline_keyboard[1][0].web_app.url == "https://example.com/app"
