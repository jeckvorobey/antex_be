from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from aiogram.exceptions import TelegramBadRequest
from aiogram.methods import SendVideoNote, SendVoice
from sqlalchemy import event
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.base import Base
from app.models.user import User
from app.repositories.chat import ChatRepository
from app.services.chat_attachments import retry_manager_attachment, send_manager_attachment


@pytest.mark.parametrize("kind", ["voice", "video_note"])
@pytest.mark.parametrize("with_reply", [False, True])
@pytest.mark.parametrize(
    "description,reason",
    [
        ("Bad Request: VOICE_MESSAGES_FORBIDDEN", "voice_messages_forbidden"),
        ("Bad Request: message to be replied not found", "reply_message_not_found"),
        ("Bad Request: VIDEO_CONTENT_TYPE_INVALID", "invalid_media"),
        ("Bad Request: file is too big", "file_too_large"),
        ("Bad Request: unknown private detail", "telegram_bad_request"),
    ],
)
async def test_recording_rejection_logs_safe_reason_and_preserves_payload(
    db_session, monkeypatch, caplog, kind, with_reply, description, reason
) -> None:
    """Отказ медиа диагностируется без сырых Telegram details и потери записи."""
    customer = User(telegram_id=820009, telegram_write_access=True)
    db_session.add(customer)
    await db_session.flush()
    repo = ChatRepository(db_session)
    conversation, _ = await repo.get_or_create_conversation(customer.id)
    replied = await repo.create_message(
        conversation_id=conversation.id,
        direction="inbound",
        message_type="text",
        telegram_chat_id=customer.telegram_id,
        telegram_message_id=410,
    )
    message = await repo.create_message(
        conversation_id=conversation.id,
        direction="outbound",
        message_type=kind,
        delivery_status="pending",
        client_request_id="recording-safe-diagnostic",
        reply_to_message_id=replied.id if with_reply else None,
    )
    await repo.add_attachment(
        message,
        kind=kind,
        payload=b"private-recording-payload",
        filename="private-recording-name",
    )
    await db_session.commit()
    attempts = 0

    class FakeBot:
        """Воспроизводит отказ Telegram на границе отправки файла."""

        async def send_voice(self, **kwargs):
            """Имитирует отказ отправки голоса."""
            nonlocal attempts
            attempts += 1
            assert bool(kwargs.get("reply_parameters")) == with_reply
            if with_reply:
                assert kwargs["reply_parameters"].message_id == 410
            raise TelegramBadRequest(method=SendVoice(**kwargs), message=description)

        async def send_video_note(self, **kwargs):
            """Имитирует отказ отправки кружочка."""
            nonlocal attempts
            attempts += 1
            assert bool(kwargs.get("reply_parameters")) == with_reply
            if with_reply:
                assert kwargs["reply_parameters"].message_id == 410
            raise TelegramBadRequest(method=SendVideoNote(**kwargs), message=description)

    @asynccontextmanager
    async def sender():
        """Предоставляет изолированный Telegram transport."""
        yield FakeBot()

    monkeypatch.setattr("app.services.chat_attachments.sender_bot", sender)
    result, _, attempted = await retry_manager_attachment(
        db_session,
        conversation_id=conversation.id,
        client_request_id="recording-safe-diagnostic",
    )
    assert attempted and attempts == 1
    assert result.delivery_status == "failed"
    assert result.attachments[0].payload == b"private-recording-payload"
    assert customer.telegram_write_access is True
    assert f"reason={reason}" in caplog.text
    assert f"has_reply={with_reply}" in caplog.text
    assert result.reply_to_message_id == (replied.id if with_reply else None)
    assert description not in caplog.text
    assert "private-recording" not in caplog.text


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

    message, _conversation, attempted = await send_manager_attachment(
        db_session,
        conversation_id=conversation.id,
        client_request_id="attachment-request-1",
        content=b"pdf-content",
        filename="receipt.pdf",
        mime_type="application/pdf",
        kind="document",
    )
    duplicate, _conversation, duplicate_attempted = await send_manager_attachment(
        db_session,
        conversation_id=conversation.id,
        client_request_id="attachment-request-1",
        content=None,
        filename="receipt.pdf",
        mime_type="application/pdf",
        kind="document",
    )

    assert attempted is True
    assert duplicate_attempted is False
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
        failed, _conversation, attempted = await send_manager_attachment(
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

    assert attempted is True
    assert failed.delivery_status == "failed"
    assert commit_observed_before_send is True
    assert failed.attachments[0].payload == b"durable-pdf"

    async with session_factory() as restarted_session:
        retried, _conversation, retry_attempted = await send_manager_attachment(
            restarted_session,
            conversation_id=conversation.id,
            client_request_id="attachment-restart-1",
            content=None,
            filename="restart.pdf",
            mime_type="application/pdf",
            kind="document",
        )
        await restarted_session.commit()

        assert retry_attempted is True
        assert retried.id == failed.id
        assert retried.delivery_status == "sent"
        assert retried.telegram_message_id == 902
        assert retried.attachments[0].telegram_file_id == "tg-retry-file"
        assert retried.attachments[0].payload is None
    assert calls == 2


async def test_concurrent_pending_retries_claim_one_telegram_delivery(
    tmp_path,
    monkeypatch,
) -> None:
    """Две backend sessions не отправляют один crash-pending payload дважды."""
    database_path = tmp_path / "attachment-claim.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{database_path}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as seed_session:
        customer = User(telegram_id=820003, telegram_write_access=True)
        seed_session.add(customer)
        await seed_session.flush()
        repo = ChatRepository(seed_session)
        conversation, _ = await repo.get_or_create_conversation(customer.id)
        message = await repo.create_message(
            conversation_id=conversation.id,
            direction="outbound",
            message_type="document",
            caption="pending.pdf",
            telegram_chat_id=customer.telegram_id,
            delivery_status="pending",
            client_request_id="attachment-concurrent-1",
        )
        await repo.add_attachment(
            message,
            kind="document",
            telegram_file_id=None,
            filename="pending.pdf",
            mime_type="application/pdf",
            size=15,
            payload=b"pending-payload",
        )
        await seed_session.commit()
        conversation_id = conversation.id

    first_send_started = asyncio.Event()
    release_first_send = asyncio.Event()
    calls = 0

    class FakeBot:
        async def send_document(self, *, chat_id: int, document):
            nonlocal calls
            calls += 1
            assert chat_id == 820003
            assert document.data == b"pending-payload"
            if calls == 1:
                first_send_started.set()
                await release_first_send.wait()
            return SimpleNamespace(
                message_id=910,
                document=SimpleNamespace(file_id="tg-claim", file_unique_id="tg-claim-unique"),
                photo=None,
                video=None,
                voice=None,
            )

    @asynccontextmanager
    async def fake_sender_bot():
        yield FakeBot()

    monkeypatch.setattr("app.services.chat_attachments.sender_bot", fake_sender_bot)

    async def perform_retry(session):
        result = await retry_manager_attachment(
            session,
            conversation_id=conversation_id,
            client_request_id="attachment-concurrent-1",
        )
        await session.commit()
        return result

    try:
        async with session_factory() as first_session, session_factory() as second_session:
            first_retry = asyncio.create_task(perform_retry(first_session))
            await asyncio.wait_for(first_send_started.wait(), timeout=2)
            second_result = await perform_retry(second_session)
            release_first_send.set()
            first_result = await first_retry

        assert calls == 1
        assert sorted((first_result[2], second_result[2])) == [False, True]
    finally:
        release_first_send.set()
        await engine.dispose()


async def test_expired_delivery_claim_recovers_crash_pending(db_session, monkeypatch) -> None:
    """Истёкший claim упавшего instance не блокирует durable retry."""
    customer = User(telegram_id=820004, telegram_write_access=True)
    db_session.add(customer)
    await db_session.flush()
    repo = ChatRepository(db_session)
    conversation, _ = await repo.get_or_create_conversation(customer.id)
    message = await repo.create_message(
        conversation_id=conversation.id,
        direction="outbound",
        message_type="document",
        caption="expired.pdf",
        telegram_chat_id=customer.telegram_id,
        delivery_status="pending",
        client_request_id="attachment-expired-claim-1",
    )
    await repo.add_attachment(
        message,
        kind="document",
        telegram_file_id=None,
        filename="expired.pdf",
        mime_type="application/pdf",
        size=15,
        payload=b"expired-payload",
        delivery_claim_token="crashed-instance",
        delivery_claimed_at=datetime.now(UTC) - timedelta(minutes=10),
    )
    await db_session.commit()
    calls = 0

    class FakeBot:
        async def send_document(self, *, chat_id: int, document):
            nonlocal calls
            calls += 1
            assert chat_id == 820004
            assert document.data == b"expired-payload"
            return SimpleNamespace(
                message_id=911,
                document=SimpleNamespace(file_id="tg-expired", file_unique_id="tg-expired-unique"),
                photo=None,
                video=None,
                voice=None,
            )

    @asynccontextmanager
    async def fake_sender_bot():
        yield FakeBot()

    monkeypatch.setattr("app.services.chat_attachments.sender_bot", fake_sender_bot)

    retried, _conversation, attempted = await retry_manager_attachment(
        db_session,
        conversation_id=conversation.id,
        client_request_id="attachment-expired-claim-1",
    )
    await db_session.commit()

    assert attempted is True
    assert retried.delivery_status == "sent"
    assert retried.telegram_message_id == 911
    assert calls == 1


async def test_video_note_is_normalized_and_sent_with_reply(db_session, monkeypatch):
    from app.services.chat_media import NormalizedRecording

    customer = User(telegram_id=940010)
    db_session.add(customer)
    await db_session.flush()
    repo = ChatRepository(db_session)
    conversation, _ = await repo.get_or_create_conversation(customer.id)
    replied = await repo.create_message(
        conversation_id=conversation.id,
        direction="inbound",
        message_type="text",
        telegram_chat_id=940010,
        telegram_message_id=20,
    )

    async def normalize(content, *, kind):
        assert content == b"browser-webm" and kind == "video_note"
        return NormalizedRecording(
            b"normalized-mp4", "video-note.mp4", "video/mp4", {"duration": 2, "length": 384}
        )

    class Bot:
        async def send_video_note(self, *, chat_id, video_note, reply_parameters):
            assert chat_id == 940010 and video_note.data == b"normalized-mp4"
            assert reply_parameters.message_id == 20
            return SimpleNamespace(
                message_id=21, video_note=SimpleNamespace(file_id="note", file_unique_id="unique")
            )

    @asynccontextmanager
    async def sender():
        yield Bot()

    monkeypatch.setattr("app.services.chat_attachments.normalize_recording", normalize)
    monkeypatch.setattr("app.services.chat_attachments.sender_bot", sender)
    message, _, attempted = await send_manager_attachment(
        db_session,
        conversation_id=conversation.id,
        client_request_id="video-reply-1",
        content=b"browser-webm",
        filename="record.webm",
        mime_type="video/webm",
        kind="video_note",
        reply_to_message_id=replied.id,
    )
    assert attempted and message.delivery_status == "sent"
    assert message.reply_to_message_id == replied.id
    assert message.attachments[0].filename == "video-note.mp4"
    assert message.attachments[0].media_metadata["length"] == 384


async def test_attachment_reply_cannot_target_another_conversation(db_session):
    import pytest

    customer, other = User(telegram_id=940011), User(telegram_id=940012)
    db_session.add_all([customer, other])
    await db_session.flush()
    repo = ChatRepository(db_session)
    conversation, _ = await repo.get_or_create_conversation(customer.id)
    other_chat, _ = await repo.get_or_create_conversation(other.id)
    replied = await repo.create_message(
        conversation_id=other_chat.id, direction="inbound", message_type="text"
    )
    with pytest.raises(LookupError, match="reply_message_not_found"):
        await send_manager_attachment(
            db_session,
            conversation_id=conversation.id,
            client_request_id="cross-reply-1",
            content=b"document",
            filename="file.txt",
            mime_type="text/plain",
            kind="document",
            reply_to_message_id=replied.id,
        )
