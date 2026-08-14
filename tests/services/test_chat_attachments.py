from __future__ import annotations

from contextlib import asynccontextmanager
from types import SimpleNamespace

from app.models.user import User
from app.repositories.chat import ChatRepository
from app.services.chat_attachments import send_manager_attachment


async def test_manager_document_send_persists_telegram_attachment(db_session, monkeypatch) -> None:
    customer = User(telegram_id=820001, telegram_write_access=True)
    db_session.add(customer)
    await db_session.flush()
    repo = ChatRepository(db_session)
    conversation, _ = await repo.get_or_create_conversation(customer.id)
    calls = 0

    class FakeBot:
        async def send_document(self, *, chat_id: int, document):
            nonlocal calls
            calls += 1
            assert chat_id == 820001
            assert document.filename == "receipt.pdf"
            return SimpleNamespace(
                message_id=901,
                document=SimpleNamespace(
                    file_id="tg-file",
                    file_unique_id="tg-unique",
                ),
                photo=None,
                video=None,
                voice=None,
            )

    @asynccontextmanager
    async def fake_sender_bot():
        yield FakeBot()

    monkeypatch.setattr("app.services.chat_attachments.sender_bot", fake_sender_bot)

    message, _conversation, created = await send_manager_attachment(
        db_session,
        conversation_id=conversation.id,
        client_request_id="attachment-request-1",
        content=b"pdf-content",
        filename="receipt.pdf",
        mime_type="application/pdf",
        kind="document",
    )
    duplicate, _conversation, duplicate_created = await send_manager_attachment(
        db_session,
        conversation_id=conversation.id,
        client_request_id="attachment-request-1",
        content=b"pdf-content",
        filename="receipt.pdf",
        mime_type="application/pdf",
        kind="document",
    )

    assert created is True
    assert duplicate_created is False
    assert duplicate.id == message.id
    assert message.delivery_status == "sent"
    assert message.telegram_message_id == 901
    assert len(message.attachments) == 1
    assert message.attachments[0].telegram_file_id == "tg-file"
    assert calls == 1
