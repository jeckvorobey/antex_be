# ruff: noqa: RUF002
"""Контракт прямой переписки с ботом без кнопок входа."""

from contextlib import asynccontextmanager
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from aiogram.types import Chat, Message
from aiogram.types import User as TelegramUser
from sqlalchemy import func, select

from app.enums.user import UserRole
from app.models.chat import ChatMessage
from app.models.user import User
from app.services import chat as chat_service
from app.services.order_notifications import build_manager_status_markup
from app.telegram import messages
from app.telegram.handlers import chat as chat_handler
from app.telegram.i18n import get_translator


@pytest.mark.parametrize("online", [False, True])
@pytest.mark.parametrize("realtime_fails", [False, True])
@pytest.mark.parametrize("telegram_fails", [False, True])
async def test_direct_message_is_saved_once_and_notifies_manager(
    db_session, monkeypatch, caplog, online: bool, realtime_fails: bool, telegram_fails: bool
) -> None:
    """Presence/Redis не подавляют доставку, повтор update не создаёт дубль."""
    customer = User(telegram_id=830001, first_name="Клиент", role=UserRole.USER)
    manager = User(telegram_id=830002, role=UserRole.MANAGER, language_code="ru")
    db_session.add_all([customer, manager])
    await db_session.commit()
    sent = []
    operations = []
    original_commit = db_session.commit

    async def tracked_commit():
        """Отмечает завершение настоящего commit, а не только flush."""
        await original_commit()
        operations.append("commit")

    monkeypatch.setattr(db_session, "commit", tracked_commit)

    class FakeBot:
        """Изолирует Telegram, проверяя сохранение до сетевой отправки."""

        async def send_message(self, **kwargs):
            """Фиксирует фактический payload уведомления."""
            operations.append("send")
            assert await db_session.scalar(select(func.count(ChatMessage.id))) == 1
            sent.append(kwargs)
            if telegram_fails:
                raise RuntimeError("Telegram unavailable")
            return SimpleNamespace(message_id=900)

    @asynccontextmanager
    async def fake_sender():
        """Не отправляет сообщения реальным аккаунтам."""
        yield FakeBot()

    @asynccontextmanager
    async def fake_session():
        """Использует реальную изолированную SQLite-сессию."""
        yield db_session

    monkeypatch.setattr(chat_handler, "create_db_session", fake_session)
    monkeypatch.setattr(chat_service, "sender_bot", fake_sender)
    monkeypatch.setattr(
        chat_service.manager_realtime_hub, "is_online", AsyncMock(return_value=online)
    )
    monkeypatch.setattr(
        chat_service.manager_realtime_hub, "is_viewing", AsyncMock(return_value=False)
    )
    monkeypatch.setattr(
        chat_service,
        "trigger_manager_refresh",
        AsyncMock(side_effect=RuntimeError("Redis unavailable") if realtime_fails else None),
    )
    message = Message(
        message_id=77,
        date=datetime.now(UTC),
        chat=Chat(id=830001, type="private"),
        from_user=TelegramUser(id=830001, is_bot=False, first_name="Клиент"),
        text="Вопрос по заявке <test>",
    )

    await chat_handler.capture_unhandled_private_message(message)
    await chat_handler.capture_unhandled_private_message(message)

    stored = (await db_session.scalars(select(ChatMessage))).all()
    assert len(stored) == 1
    assert stored[0].text == "Вопрос по заявке <test>"
    assert stored[0].direction == "inbound"
    assert operations == ["commit", "send", "commit"]
    assert len(sent) == 1
    assert sent[0]["chat_id"] == 830002
    assert "Вопрос по заявке &lt;test&gt;" in sent[0]["text"]
    assert sent[0].get("reply_markup") is None
    assert "Вопрос по заявке" not in caplog.text
    conversation = await chat_service.ChatService(db_session).repo.get_conversation(
        stored[0].conversation_id
    )
    assert conversation.user_id == customer.id
    assert conversation.unread_count == 1


@pytest.mark.parametrize(
    ("status", "callbacks"),
    [
        (1, ["op:cancel:17", "op:take:17"]),
        (2, ["op:cancel:17", "op:close:17"]),
        (3, []),
        (4, []),
    ],
)
def test_manager_status_actions_exclude_chat_entry(monkeypatch, status, callbacks) -> None:
    """Все статусы оставляют только действия заявки, даже при настроенном Mini App."""
    monkeypatch.setattr(
        "app.services.order_notifications.settings.frontend_webapp_url", "https://miniapp.example"
    )
    markup = build_manager_status_markup(SimpleNamespace(id=17, status=status))
    buttons = [button for row in markup.inline_keyboard for button in row]
    assert [button.callback_data for button in buttons] == callbacks
    assert all(button.web_app is None and button.url is None for button in buttons)


@pytest.mark.parametrize("locale", ["ru", "en"])
@pytest.mark.parametrize("offline", [False, True])
def test_order_created_explains_direct_bot_messaging(locale, offline) -> None:
    """В обеих локалях подтверждение заявки объясняет прямую связь с менеджером."""
    text = messages.order_created(
        "123", translator=get_translator(locale), managers_offline=offline
    )
    expected = (
        "просто отправьте сообщение этому боту" if locale == "ru" else "send a message to this bot"
    )
    assert expected in text
