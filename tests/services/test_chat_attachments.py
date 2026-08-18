from __future__ import annotations

from contextlib import asynccontextmanager
from types import SimpleNamespace

from sqlalchemy import event
from sqlalchemy.ext.asyncio import async_sessionmaker

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
        content=None,
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


async def test_failed_attachment_survives_restart_and_retries_from_database(
    db_session,
    monkeypatch,
) -> None:
    """Failed delivery повторяется из durable bytes без нового сообщения и upload."""
    customer = User(telegram_id=820002, telegram_write_access=True)
    db_session.add(customer)
    await db_session.flush()
    repo = ChatRepository(db_session)
    conversation, _ = await repo.get_or_create_conversation(customer.id)
    assert db_session.bind is not None
    session_factory = async_sessionmaker(db_session.bind, expire_on_commit=False)
    calls = 0
    commits = 0
    commit_observed_before_send = False

    def count_commit(_connection) -> None:
        nonlocal commits
        commits += 1

    class FakeBot:
        async def send_document(self, *, chat_id: int, document):
            nonlocal calls, commit_observed_before_send
            calls += 1
            assert chat_id == 820002
            assert document.filename == "restart.pdf"
            assert document.data == b"durable-pdf"
            if calls == 1:
                commit_observed_before_send = commits > 0
                raise RuntimeError("temporary Telegram outage")
            return SimpleNamespace(
                message_id=902,
                document=SimpleNamespace(
                    file_id="tg-retry-file",
                    file_unique_id="tg-retry-unique",
                ),
                photo=None,
                video=None,
                voice=None,
            )

    @asynccontextmanager
    async def fake_sender_bot():
        yield FakeBot()

    monkeypatch.setattr("app.services.chat_attachments.sender_bot", fake_sender_bot)

    event.listen(db_session.bind.sync_engine, "commit", count_commit)
    try:
        failed, _conversation, created = await send_manager_attachment(
            db_session,
            conversation_id=conversation.id,
            client_request_id="attachment-restart-1",
            content=b"durable-pdf",
            filename="restart.pdf",
            mime_type="application/pdf",
            kind="document",
        )
    finally:
        event.remove(db_session.bind.sync_engine, "commit", count_commit)
    await db_session.commit()

    assert created is True
    assert failed.delivery_status == "failed"
    assert commit_observed_before_send is True
    assert failed.attachments[0].payload == b"durable-pdf"

    async with session_factory() as restarted_session:
        retried, _conversation, retry_created = await send_manager_attachment(
            restarted_session,
            conversation_id=conversation.id,
            client_request_id="attachment-restart-1",
            content=None,
            filename="restart.pdf",
            mime_type="application/pdf",
            kind="document",
        )
        await restarted_session.commit()

        assert retry_created is False
        assert retried.id == failed.id
        assert retried.delivery_status == "sent"
        assert retried.telegram_message_id == 902
        assert retried.attachments[0].telegram_file_id == "tg-retry-file"
        assert retried.attachments[0].payload is None
    assert calls == 2
