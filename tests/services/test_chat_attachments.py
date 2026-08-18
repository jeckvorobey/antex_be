from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from sqlalchemy import event
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.base import Base
from app.models.user import User
from app.repositories.chat import ChatRepository
from app.services.chat_attachments import retry_manager_attachment, send_manager_attachment


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
