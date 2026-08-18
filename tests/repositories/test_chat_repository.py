from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.models.chat import ChatMessageRevision
from app.models.user import User
from app.repositories.chat import ChatRepository


async def test_chat_repository_get_or_create_and_unread(db_session) -> None:
    user = User(telegram_id=700001, username="chat_user")
    db_session.add(user)
    await db_session.flush()

    repo = ChatRepository(db_session)
    conversation, created = await repo.get_or_create_conversation(user.id)
    same, created_again = await repo.get_or_create_conversation(user.id)

    assert created is True
    assert created_again is False
    assert same.id == conversation.id

    message = await repo.create_message(
        conversation_id=conversation.id,
        direction="inbound",
        message_type="text",
        text="hello",
        telegram_chat_id=700001,
        telegram_message_id=11,
        delivery_status="received",
    )
    await repo.touch_inbound(conversation, increment_unread=True)

    duplicate = await repo.get_by_telegram_identity(700001, 11)
    assert duplicate is not None
    assert duplicate.id == message.id
    assert conversation.unread_count == 1
    assert await repo.unread_total() == 1

    await repo.mark_read(conversation)
    assert conversation.unread_count == 0
    assert await repo.unread_total() == 0


async def test_chat_repository_preserves_edit_revision(db_session) -> None:
    user = User(telegram_id=700002)
    db_session.add(user)
    await db_session.flush()
    repo = ChatRepository(db_session)
    conversation, _ = await repo.get_or_create_conversation(user.id)
    message = await repo.create_message(
        conversation_id=conversation.id,
        direction="inbound",
        message_type="text",
        text="before",
        telegram_chat_id=700002,
        telegram_message_id=12,
        delivery_status="received",
    )

    revision = await repo.add_revision(
        message,
        old_text="before",
        new_text="after",
        telegram_edit_date=None,
    )
    count = await db_session.scalar(select(func.count(ChatMessageRevision.id)))

    assert revision.revision == 1
    assert revision.old_text == "before"
    assert revision.new_text == "after"
    assert count == 1


async def test_concurrent_unread_increments_are_not_lost(db_session) -> None:
    """Два запроса со stale snapshot должны атомарно увеличить unread до двух."""
    user = User(telegram_id=700003)
    db_session.add(user)
    await db_session.flush()
    conversation, _ = await ChatRepository(db_session).get_or_create_conversation(user.id)
    conversation_id = conversation.id
    await db_session.commit()

    session_factory = async_sessionmaker(db_session.bind, expire_on_commit=False)
    async with session_factory() as first_session, session_factory() as second_session:
        first = await ChatRepository(first_session).get_conversation(conversation_id)
        second = await ChatRepository(second_session).get_conversation(conversation_id)
        assert first is not None
        assert second is not None
        assert first.unread_count == second.unread_count == 0

        await ChatRepository(first_session).touch_inbound(first, increment_unread=True)
        await first_session.commit()
        await ChatRepository(second_session).touch_inbound(second, increment_unread=True)
        await second_session.commit()

    async with session_factory() as verification_session:
        stored = await ChatRepository(verification_session).get_conversation(conversation_id)
        assert stored is not None
        assert stored.unread_count == 2
