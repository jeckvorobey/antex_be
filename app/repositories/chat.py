"""Repository for durable manager chat state."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import desc, func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.chat import ChatAttachment, ChatConversation, ChatMessage, ChatMessageRevision
from app.models.order import Order
from app.models.user import User
from app.repositories.base import BaseRepository


class ChatRepository(BaseRepository[ChatConversation]):
    """Ограничивает менеджерские выборки владельцем; без scope обслуживает ingestion."""

    model = ChatConversation

    def __init__(self, session: AsyncSession, *, manager_id: int | None = None) -> None:
        """Принимает проверенный user ID менеджера от сервисного/API слоя."""
        super().__init__(session)
        self.manager_id = manager_id

    async def get_or_create_conversation(self, user_id: int) -> tuple[ChatConversation, bool]:
        """Возвращает только пару владелец-клиент, включая отдельную беседу без владельца."""
        existing = await self.get_conversation_by_user(user_id)
        if existing is not None:
            return existing, False

        conversation = ChatConversation(user_id=user_id, manager_id=self.manager_id)
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
        """Ищет беседу по обоим участникам, без переназначения старой истории."""
        result = await self.session.execute(
            select(ChatConversation)
            .where(
                ChatConversation.user_id == user_id,
                ChatConversation.manager_id == self.manager_id,
            )
            .options(selectinload(ChatConversation.user))
        )
        return result.scalar_one_or_none()

    async def get_conversation(self, conversation_id: int) -> ChatConversation | None:
        """Для менеджерского scope скрывает чужие и неатрибутированные беседы."""
        statement = select(ChatConversation).where(ChatConversation.id == conversation_id)
        if self.manager_id is not None:
            statement = statement.where(ChatConversation.manager_id == self.manager_id)
        result = await self.session.execute(statement.options(selectinload(ChatConversation.user)))
        return result.scalar_one_or_none()

    async def list_conversations(
        self,
        *,
        unread_only: bool = False,
        query: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[ChatConversation], int]:
        """Возвращает страницу и total только для выбранного владельца."""
        statement = (
            select(ChatConversation)
            .join(User, User.id == ChatConversation.user_id)
            .where(ChatConversation.manager_id == self.manager_id)
        )
        count_statement = (
            select(func.count(ChatConversation.id))
            .select_from(ChatConversation)
            .join(User, User.id == ChatConversation.user_id)
            .where(ChatConversation.manager_id == self.manager_id)
        )
        if unread_only:
            statement = statement.where(ChatConversation.unread_count > 0)
            count_statement = count_statement.where(ChatConversation.unread_count > 0)
        if query:
            normalized_query = query.strip()
            pattern = f"%{normalized_query}%"
            order_query = normalized_query.removeprefix("#")
            search_conditions = [
                User.username.ilike(pattern),
                User.first_name.ilike(pattern),
                User.last_name.ilike(pattern),
            ]
            if order_query:
                latest_order_public_number = (
                    select(Order.publicNumber)
                    .where(Order.UserId == User.id, Order.destroyTime.is_(None))
                    .order_by(desc(Order.createdAt), desc(Order.id))
                    .limit(1)
                    .correlate(User)
                    .scalar_subquery()
                )
                search_conditions.append(latest_order_public_number.ilike(f"%{order_query}%"))
            conditions = or_(*search_conditions)
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
        """Считает непрочитанные сообщения только в беседах выбранного владельца."""
        total = await self.session.scalar(
            select(func.coalesce(func.sum(ChatConversation.unread_count), 0)).where(
                ChatConversation.manager_id == self.manager_id
            )
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

    async def latest_messages_by_conversation(
        self,
        conversation_ids: list[int],
    ) -> dict[int, ChatMessage]:
        """Загрузить последние сообщения страницы бесед одним bulk-запросом."""
        if not conversation_ids:
            return {}
        latest_ids = (
            select(func.max(ChatMessage.id))
            .where(ChatMessage.conversation_id.in_(conversation_ids))
            .group_by(ChatMessage.conversation_id)
        )
        result = await self.session.execute(
            select(ChatMessage)
            .where(ChatMessage.id.in_(latest_ids))
            .options(selectinload(ChatMessage.attachments))
        )
        return {message.conversation_id: message for message in result.scalars().all()}

    async def get_message(self, message_id: int) -> ChatMessage | None:
        """Проверяет владельца сообщения перед ответом или пересылкой."""
        statement = select(ChatMessage).where(ChatMessage.id == message_id)
        if self.manager_id is not None:
            statement = statement.join(ChatConversation).where(
                ChatConversation.manager_id == self.manager_id,
            )
        result = await self.session.execute(
            statement.options(selectinload(ChatMessage.attachments))
        )
        return result.scalar_one_or_none()

    async def get_attachment(self, attachment_id: int) -> ChatAttachment | None:
        """Проверяет владельца через сообщение до доступа к payload либо Telegram."""
        result = await self.session.execute(
            select(ChatAttachment)
            .join(ChatMessage)
            .join(ChatConversation)
            .where(
                ChatAttachment.id == attachment_id,
                ChatConversation.manager_id == self.manager_id,
            )
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

    async def claim_text_delivery(
        self,
        *,
        message_id: int,
        claim_token: str,
        claimed_at: datetime,
        expired_before: datetime,
        forwarding: bool = False,
    ) -> bool:
        result = await self.session.execute(
            update(ChatMessage)
            .where(
                ChatMessage.id == message_id,
                (
                    ChatMessage.forward_source_message_id.is_not(None)
                    if forwarding
                    else (ChatMessage.message_type == "text")
                    & ChatMessage.forward_source_message_id.is_(None)
                ),
                ChatMessage.delivery_status != "sent",
                or_(
                    ChatMessage.delivery_claim_token.is_(None),
                    ChatMessage.delivery_claimed_at.is_(None),
                    ChatMessage.delivery_claimed_at <= expired_before,
                ),
            )
            .values(
                delivery_status="pending",
                delivery_claim_token=claim_token,
                delivery_claimed_at=claimed_at,
            )
            .execution_options(synchronize_session=False)
        )
        return result.rowcount == 1

    async def release_text_delivery(self, *, message_id: int, claim_token: str) -> None:
        await self.session.execute(
            update(ChatMessage)
            .where(
                ChatMessage.id == message_id,
                ChatMessage.delivery_claim_token == claim_token,
            )
            .values(delivery_claim_token=None, delivery_claimed_at=None)
            .execution_options(synchronize_session=False)
        )

    async def add_attachment(self, message: ChatMessage, **values: object) -> ChatAttachment:
        attachment = ChatAttachment(message=message, **values)
        self.session.add(attachment)
        await self.session.flush()
        return attachment

    async def claim_attachment_delivery(
        self,
        *,
        attachment_id: int,
        message_id: int,
        claim_token: str,
        claimed_at: datetime,
        expired_before: datetime,
    ) -> bool:
        """Атомарно занять durable payload для одной Telegram delivery attempt."""
        result = await self.session.execute(
            update(ChatAttachment)
            .where(
                ChatAttachment.id == attachment_id,
                ChatAttachment.payload.is_not(None),
                or_(
                    ChatAttachment.delivery_claim_token.is_(None),
                    ChatAttachment.delivery_claimed_at.is_(None),
                    ChatAttachment.delivery_claimed_at <= expired_before,
                ),
            )
            .values(
                delivery_claim_token=claim_token,
                delivery_claimed_at=claimed_at,
            )
            .execution_options(synchronize_session=False)
        )
        claimed = result.rowcount == 1
        if claimed:
            await self.session.execute(
                update(ChatMessage)
                .where(ChatMessage.id == message_id)
                .values(delivery_status="pending")
                .execution_options(synchronize_session=False)
            )
        # Claim должен быть видим другим backend instances до внешнего Telegram I/O.
        await self.session.commit()
        return claimed

    async def release_attachment_delivery(
        self,
        *,
        attachment_id: int,
        claim_token: str,
    ) -> None:
        """Освободить только claim текущей delivery attempt."""
        await self.session.execute(
            update(ChatAttachment)
            .where(
                ChatAttachment.id == attachment_id,
                ChatAttachment.delivery_claim_token == claim_token,
            )
            .values(delivery_claim_token=None, delivery_claimed_at=None)
            .execution_options(synchronize_session=False)
        )

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

    async def touch_inbound(
        self, conversation: ChatConversation, *, increment_unread: bool
    ) -> None:
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
            update(ChatConversation).where(ChatConversation.id == conversation.id).values(**values)
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
