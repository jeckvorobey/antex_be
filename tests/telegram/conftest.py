"""Фикстуры для Telegram TDD тестов."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage
from fluent.runtime import FluentBundle, FluentResource


@dataclass
class SentMessage:
    """Сообщение, отправленное тестовым bot/message double."""

    text: str
    reply_markup: Any | None = None
    from_exchange_flow: bool = True


class MockBot:
    """Минимальный bot double c историей отправок."""

    def __init__(self) -> None:
        self.sent_messages: list[SentMessage] = []
        self.last_message: SentMessage | None = None

    async def send_message(
        self,
        chat_id: int,
        text: str,
        reply_markup: Any | None = None,
        **_: Any,
    ) -> SentMessage:
        del chat_id
        sent = SentMessage(text=text, reply_markup=reply_markup)
        self.sent_messages.append(sent)
        self.last_message = sent
        return sent


class MockMessage:
    """Минимальная aiogram-like message заглушка."""

    def __init__(self, *, text: str | None = None, bot: MockBot | None = None) -> None:
        self.text = text
        self.bot = bot or MockBot()
        self.from_user = SimpleNamespace(
            id=1,
            username="tester",
            first_name="Serg",
            last_name=None,
            language_code="ru",
            is_bot=False,
            is_premium=False,
        )
        self.message_id = 1
        self.chat = SimpleNamespace(id=1)

    async def answer(
        self,
        text: str,
        reply_markup: Any | None = None,
        **_: Any,
    ) -> SentMessage:
        return await self.bot.send_message(self.chat.id, text, reply_markup=reply_markup)

    async def edit_text(
        self,
        text: str,
        reply_markup: Any | None = None,
        **_: Any,
    ) -> SentMessage:
        return await self.bot.send_message(self.chat.id, text, reply_markup=reply_markup)


class MockCallbackQuery:
    """Минимальная callback query заглушка."""

    def __init__(
        self,
        *,
        data: str,
        message: MockMessage,
        bot: MockBot | None = None,
    ) -> None:
        self.data = data
        self.message = message
        self.bot = bot or message.bot
        self.from_user = message.from_user
        self.answers: list[dict[str, Any]] = []

    async def answer(self, text: str | None = None, show_alert: bool = False) -> None:
        self.answers.append({"text": text, "show_alert": show_alert})


@pytest.fixture
def mock_i18n():
    """Возвращает callable, который эхо-вернёт ключ перевода."""

    def _(key: str, **kwargs: Any) -> str:
        del kwargs
        return key

    return _


@pytest.fixture
def make_i18n():
    """Фабрика locale-aware i18n callables на основе Fluent."""

    def factory(locale: str):
        ftl_path = Path(__file__).parents[2] / "locale" / locale / "bot.ftl"
        resource = FluentResource(ftl_path.read_text(encoding="utf-8"))
        bundle = FluentBundle([locale])
        bundle.add_resource(resource)

        def translate(key: str, **kwargs: Any) -> str:
            value, errors = bundle.format_pattern(bundle.get_message(key).value, kwargs)
            if errors:
                raise AssertionError(f"Fluent formatting errors for {key}: {errors}")
            return value

        return translate

    return factory


@pytest.fixture
def mock_bot() -> MockBot:
    return MockBot()


@pytest.fixture
def mock_message(mock_bot: MockBot) -> MockMessage:
    return MockMessage(bot=mock_bot)


@pytest.fixture
def mock_callback(mock_message: MockMessage) -> MockCallbackQuery:
    return MockCallbackQuery(data="noop", message=mock_message)


@pytest.fixture
async def mock_state() -> FSMContext:
    storage = MemoryStorage()
    key = StorageKey(bot_id=1, chat_id=1, user_id=1)
    state = FSMContext(storage=storage, key=key)
    yield state
    await storage.close()
