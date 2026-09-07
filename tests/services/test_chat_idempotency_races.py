from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest
from sqlalchemy import func, select

from app.models.chat import ChatMessage
from app.models.user import User
from app.repositories.chat import ChatRepository
from app.services.chat import ChatService
from app.services.chat_attachments import send_manager_attachment


@pytest.mark.parametrize("kind", ["text", "document"])
async def test_stale_idempotency_read_recovers_unique_insert(db_session, monkeypatch, kind):
    """Устаревший SELECT перед UNIQUE INSERT возвращает уже созданную запись."""
    user = User(telegram_id=990001)
    db_session.add(user)
    await db_session.flush()
    conversation, _ = await ChatRepository(db_session).get_or_create_conversation(user.id)
    sent_calls = []

    class Bot:
        async def send_message(self, **kwargs):
            sent_calls.append(kwargs)
            return SimpleNamespace(message_id=101)

        async def send_document(self, **kwargs):
            sent_calls.append(kwargs)
            return SimpleNamespace(message_id=101, document=None)

    @asynccontextmanager
    async def sender():
        yield Bot()

    monkeypatch.setattr("app.services.chat.sender_bot", sender)
    monkeypatch.setattr("app.services.chat_attachments.sender_bot", sender)

    async def send():
        if kind == "text":
            return await ChatService(db_session).send_manager_message(
                conversation_id=conversation.id, client_request_id="race-fixture", text="hello"
            )
        return await send_manager_attachment(
            db_session,
            conversation_id=conversation.id,
            client_request_id="race-fixture",
            content=b"fixture",
            filename="fixture.pdf",
            mime_type="application/pdf",
            kind=kind,
        )

    first, _, _ = await send()
    await db_session.commit()
    original_get = ChatRepository.get_by_client_request_id
    reads = 0

    async def stale_get(self, client_request_id):
        nonlocal reads
        reads += 1
        if reads == 1:
            return None
        return await original_get(self, client_request_id)

    monkeypatch.setattr(ChatRepository, "get_by_client_request_id", stale_get)
    repeated, _, attempted = await send()
    assert repeated.id == first.id
    assert not attempted
    assert len(sent_calls) == 1
    assert await db_session.scalar(select(func.count(ChatMessage.id))) == 1
