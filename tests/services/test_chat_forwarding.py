from __future__ import annotations

from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest
from aiogram.exceptions import TelegramBadRequest
from aiogram.methods import ForwardMessage

from app.models.user import User
from app.repositories.chat import ChatRepository
from app.services.chat import ChatService
from app.services.chat_forwarding import forward_manager_message


async def seed(db):
    customer, target = User(telegram_id=940001, first_name="Клиент"), User(telegram_id=940002)
    db.add_all([customer, target])
    await db.flush()
    repo = ChatRepository(db)
    source_chat, _ = await repo.get_or_create_conversation(customer.id)
    target_chat, _ = await repo.get_or_create_conversation(target.id)
    source = await repo.create_message(
        conversation_id=source_chat.id,
        direction="inbound",
        message_type="video_note",
        telegram_chat_id=940001,
        telegram_message_id=43,
        delivery_status="received",
    )
    await repo.add_attachment(
        source,
        kind="video_note",
        telegram_file_id="file",
        filename="video.mp4",
        mime_type="video/mp4",
    )
    await db.commit()
    return source, target_chat


async def test_forward_preserves_content_and_is_idempotent(db_session, monkeypatch):
    source, target = await seed(db_session)
    calls = []

    class Bot:
        async def forward_message(self, **kwargs):
            calls.append(kwargs)
            return SimpleNamespace(message_id=55)

    @asynccontextmanager
    async def sender():
        yield Bot()

    monkeypatch.setattr("app.services.chat_forwarding.sender_bot", sender)
    message, _, attempted = await forward_manager_message(
        db_session,
        conversation_id=target.id,
        client_request_id="forward-123",
        source_message_id=source.id,
    )
    await db_session.commit()
    duplicate, _, repeated = await forward_manager_message(
        db_session,
        conversation_id=target.id,
        client_request_id="forward-123",
        source_message_id=source.id,
    )
    assert attempted and not repeated
    assert duplicate.id == message.id
    assert calls == [{"chat_id": 940002, "from_chat_id": 940001, "message_id": 43}]
    assert message.message_type == "video_note"
    assert message.attachments[0].telegram_file_id == "file"
    assert message.forward_source_message_id == source.id
    assert ChatService.message_out(message).forwardSourceLabel == "Клиент"


@pytest.mark.parametrize("status", ["failed", "pending"])
async def test_forward_rejects_undelivered_source(db_session, status):
    source, target = await seed(db_session)
    source.delivery_status = status
    await db_session.commit()
    with pytest.raises(ValueError, match="forward_source_unavailable"):
        await forward_manager_message(
            db_session,
            conversation_id=target.id,
            client_request_id="forward-bad",
            source_message_id=source.id,
        )


async def test_forward_protected_content_fails_without_copy(db_session, monkeypatch):
    source, target = await seed(db_session)

    class Bot:
        async def forward_message(self, **kwargs):
            raise TelegramBadRequest(
                method=ForwardMessage(**kwargs), message="message can't be forwarded SECRET"
            )

    @asynccontextmanager
    async def sender():
        yield Bot()

    monkeypatch.setattr("app.services.chat_forwarding.sender_bot", sender)
    message, _, attempted = await forward_manager_message(
        db_session,
        conversation_id=target.id,
        client_request_id="forward-protected",
        source_message_id=source.id,
    )
    assert attempted and message.delivery_status == "failed"


async def test_forward_missing_source(db_session):
    _, target = await seed(db_session)
    with pytest.raises(LookupError, match="forward_source_not_found"):
        await forward_manager_message(
            db_session,
            conversation_id=target.id,
            client_request_id="forward-missing",
            source_message_id=999999,
        )
