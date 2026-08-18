"""Repository for durable manager chat state."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import desc, func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload

from app.models.chat import ChatAttachment, ChatConversation, ChatMessage, ChatMessageRevision
from app.models.user import User
from app.repositories.base import BaseRepository


class ChatRepository(BaseRepository[ChatConversation]):
    model = ChatConversation

    async def get_or_create_conversation(self, user_id: int) -> tuple[ChatConversation, bool]:
        existing = await self.get_conversation_by_user(user_id)
        if existing is not None:
            return existing, False

        conversation = ChatConversation(user_id=user_id)
        try:
            async with self.session.begin_nested():
                self.session.add(conversation)
                await self.session.flush()
        except IntegrityError:
            existing = await self.get_conversation_by_user(user_id)
            if existing is None:
                raise
            return existing, False
        return conversation, True

    async def get_conversation_by_user(self, user_id: int) -> ChatConversation | None:
        result = await self.session.execute(
            select(ChatConversation)
            .where(ChatConversation.user_id == user_id)
            .options(selectinload(ChatConversation.user))
        )
        return result.scalar_one_or_none()

    async def get_conversation(self, conversation_id: int) -> ChatConversation | None:
        result = await self.session.execute(
            select(ChatConversation)
            .where(ChatConversation.id == conversation_id)
            .options(selectinload(ChatConversation.user))
        )
        return result.scalar_one_or_none()

    async def list_conversations(
        self,
        *,
        unread_only: bool = False,
        query: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[ChatConversation], int]:
        statement = select(ChatConversation).join(User, User.id == ChatConversation.user_id)
        count_statement = (
            select(func.count(ChatConversation.id))
            .select_from(ChatConversation)
            .join(User, User.id == ChatConversation.user_id)
        )
        if unread_only:
            statement = statement.where(ChatConversation.unread_count > 0)
            count_statement = count_statement.where(ChatConversation.unread_count > 0)
        if query:
            pattern = f"%{query.strip()}%"
            conditions = or_(
                User.username.ilike(pattern),
                User.first_name.ilike(pattern),
                User.last_name.ilike(pattern),
            )
            statement = statement.where(conditions)
            count_statement = count_statement.where(conditions)

        result = await self.session.execute(
            statement.options(selectinload(ChatConversation.user))
            .order_by(desc(ChatConversation.last_message_at), desc(ChatConversation.id))
            .limit(limit)
            .offset(offset)
        )
        total = await self.session.scalar(count_statement)
        return list(result.scalars().all()), int(total or 0)

    async def unread_total(self) -> int:
        total = await self.session.scalar(
            select(func.coalesce(func.sum(ChatConversation.unread_count), 0))
        )
        return int(total or 0)

    async def list_messages(
        self,
        conversation_id: int,
        *,
        limit: int = 50,
        before_id: int | None = None,
    ) -> tuple[list[ChatMessage], bool]:
        statement = (
            select(ChatMessage)
            .where(ChatMessage.conversation_id == conversation_id)
            .options(selectinload(ChatMessage.attachments))
            .order_by(ChatMessage.id.desc())
        )
        if before_id is not None:
            statement = statement.where(ChatMessage.id < before_id)
        result = await self.session.execute(statement.limit(limit + 1))
        rows = list(result.scalars().all())
        has_more = len(rows) > limit
        rows = rows[:limit]
        rows.reverse()
        return rows, has_more

    async def get_message(self, message_id: int) -> ChatMessage | None:
        result = await self.session.execute(
            select(ChatMessage)
            .where(ChatMessage.id == message_id)
            .options(selectinload(ChatMessage.attachments))
        )
        return result.scalar_one_or_none()

    async def get_by_telegram_identity(
        self,
        telegram_chat_id: int,
        telegram_message_id: int,
    ) -> ChatMessage | None:
        result = await self.session.execute(
            select(ChatMessage)
            .where(
                ChatMessage.telegram_chat_id == telegram_chat_id,
                ChatMessage.telegram_message_id == telegram_message_id,
            )
            .options(selectinload(ChatMessage.attachments))
        )
        return result.scalar_one_or_none()

    async def get_by_client_request_id(self, client_request_id: str) -> ChatMessage | None:
        result = await self.session.execute(
            select(ChatMessage)
            .where(ChatMessage.client_request_id == client_request_id)
            .options(selectinload(ChatMessage.attachments))
        )
        return result.scalar_one_or_none()

    async def create_message(self, **values: object) -> ChatMessage:
        message = ChatMessage(**values)
        self.session.add(message)
        await self.session.flush()
        return message

    async def add_attachment(self, message: ChatMessage, **values: object) -> ChatAttachment:
        attachment = ChatAttachment(message=message, **values)
        self.session.add(attachment)
        await self.session.flush()
        return attachment

    async def add_revision(
        self,
        message: ChatMessage,
        *,
        old_text: str | None,
        new_text: str | None,
        telegram_edit_date: datetime | None,
    ) -> ChatMessageRevision:
        next_revision = await self.session.scalar(
            select(func.coalesce(func.max(ChatMessageRevision.revision), 0) + 1).where(
                ChatMessageRevision.message_id == message.id
            )
        )
        revision = ChatMessageRevision(
            message_id=message.id,
            revision=int(next_revision or 1),
            old_text=old_text,
            new_text=new_text,
            telegram_edit_date=telegram_edit_date,
        )
        self.session.add(revision)
        await self.session.flush()
        return revision

    async def touch_inbound(self, conversation: ChatConversation, *, increment_unread: bool) -> None:
        """Атомарно обновляет входящую активность и счётчик непрочитанных."""
        now = datetime.now(UTC)
        values: dict[str, object] = {
            "last_message_at": now,
            "last_inbound_at": now,
            "status": "open",
        }
        if increment_unread:
            values["unread_count"] = ChatConversation.unread_count + 1
        await self.session.execute(
            update(ChatConversation)
            .where(ChatConversation.id == conversation.id)
            .values(**values)
        )
        await self.session.refresh(conversation)

    async def touch_outbound(self, conversation: ChatConversation) -> None:
        now = datetime.now(UTC)
        conversation.last_message_at = now
        conversation.last_outbound_at = now
        conversation.status = "open"
        await self.session.flush()

    async def mark_read(self, conversation: ChatConversation) -> None:
        conversation.unread_count = 0
        conversation.last_read_at = datetime.now(UTC)
        await self.session.flush()

    async def close(self, conversation: ChatConversation) -> None:
        conversation.status = "closed"
        await self.session.flush()
