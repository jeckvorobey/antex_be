from __future__ import annotations

from contextlib import asynccontextmanager
from types import SimpleNamespace

from sqlalchemy import func, select

from app.models.chat import ChatMessage, ChatMessageRevision
from app.models.user import User
from app.services.chat import ChatService


async def test_capture_inbound_is_idempotent(db_session) -> None:
    user = User(telegram_id=810001, username="customer")
    db_session.add(user)
    await db_session.flush()
    service = ChatService(db_session)

    first, conversation, created = await service.capture_inbound(
        user=user,
        telegram_chat_id=810001,
        telegram_message_id=44,
        message_type="text",
        text="Привет",
        caption=None,
    )
    duplicate, duplicate_conversation, duplicate_created = await service.capture_inbound(
        user=user,
        telegram_chat_id=810001,
        telegram_message_id=44,
        message_type="text",
        text="Привет",
        caption=None,
    )

    count = await db_session.scalar(select(func.count(ChatMessage.id)))
    assert created is True
    assert duplicate_created is False
    assert duplicate.id == first.id
    assert duplicate_conversation.id == conversation.id
    assert conversation.unread_count == 1
    assert count == 1


async def test_capture_edit_preserves_revision(db_session) -> None:
    user = User(telegram_id=810002)
    db_session.add(user)
    await db_session.flush()
    service = ChatService(db_session)
    message, _conversation, _ = await service.capture_inbound(
        user=user,
        telegram_chat_id=810002,
        telegram_message_id=45,
        message_type="text",
        text="до",
        caption=None,
    )

    edited = await service.capture_edit(
        telegram_chat_id=810002,
        telegram_message_id=45,
        text="после",
        caption=None,
        telegram_edit_date=None,
    )

    assert edited is not None
    assert edited.id == message.id
    assert edited.text == "после"
    revision = await db_session.scalar(select(ChatMessageRevision))
    assert revision is not None
    assert revision.old_text == "до"
    assert revision.new_text == "после"


async def test_manager_send_is_idempotent(db_session, monkeypatch) -> None:
    customer = User(telegram_id=810003, telegram_write_access=True)
    db_session.add(customer)
    await db_session.flush()
    service = ChatService(db_session)
    conversation, _ = await service.repo.get_or_create_conversation(customer.id)

    calls = 0

    class FakeBot:
        async def send_message(self, *, chat_id: int, text: str):
            nonlocal calls
            calls += 1
            assert chat_id == 810003
            assert text == "Ответ менеджера"
            return SimpleNamespace(message_id=777)

    @asynccontextmanager
    async def fake_sender_bot():
        yield FakeBot()

    monkeypatch.setattr("app.services.chat.sender_bot", fake_sender_bot)

    first, _conversation, created = await service.send_manager_message(
        conversation_id=conversation.id,
        client_request_id="request-123456",
        text="Ответ менеджера",
    )
    duplicate, _conversation, duplicate_created = await service.send_manager_message(
        conversation_id=conversation.id,
        client_request_id="request-123456",
        text="Ответ менеджера",
    )

    assert created is True
    assert duplicate_created is False
    assert first.id == duplicate.id
    assert first.delivery_status == "sent"
    assert first.telegram_message_id == 777
    assert calls == 1
