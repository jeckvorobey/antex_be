"""Business logic for the single-manager chat workspace."""

from __future__ import annotations

import html
import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramNotFound
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, ReplyParameters, WebAppInfo
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chat import ChatConversation, ChatMessage
from app.models.order import Order
from app.models.user import User
from app.repositories.chat import ChatRepository
from app.repositories.order import OrderRepository
from app.repositories.user import UserRepository
from app.schemas.chat import (
    ChatAttachmentOut,
    ChatConversationOut,
    ChatMessageOut,
    ManagerChatUser,
    ManagerOrderCity,
    ManagerOrderSummary,
)
from app.services.chat_realtime import manager_realtime_hub, trigger_manager_refresh
from app.services.order_notifications import (
    DeliveryOutcome,
    build_manager_workspace_url,
    is_permanent_telegram_delivery_error,
    reconcile_telegram_write_access,
)
from app.telegram.bot import sender_bot
from app.telegram.i18n import get_user_translator

logger = logging.getLogger(__name__)
TEXT_DELIVERY_LEASE = timedelta(minutes=2)


@dataclass(frozen=True, slots=True)
class InboundAttachment:
    kind: str
    file_id: str
    file_unique_id: str | None = None
    filename: str | None = None
    mime_type: str | None = None
    size: int | None = None
    metadata: dict[str, object] | None = None


class ChatService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.repo = ChatRepository(db)
        self.user_repo = UserRepository(db)
        self.order_repo = OrderRepository(db)

    async def capture_inbound(
        self,
        *,
        user: User,
        telegram_chat_id: int,
        telegram_message_id: int,
        message_type: str,
        text: str | None,
        caption: str | None,
        reply_to_telegram_message_id: int | None = None,
        telegram_edit_date: datetime | None = None,
        attachments: list[InboundAttachment] | None = None,
        forward_source_label: str | None = None,
    ) -> tuple[ChatMessage, ChatConversation, bool]:
        existing = await self.repo.get_by_telegram_identity(
            telegram_chat_id,
            telegram_message_id,
        )
        if existing is not None:
            conversation = await self.repo.get_conversation(existing.conversation_id)
            if conversation is None:
                raise RuntimeError("Chat conversation disappeared for stored message")
            return existing, conversation, False

        conversation, created_conversation = await self.repo.get_or_create_conversation(user.id)
        if created_conversation:
            conversation.user = user

        reply_to_id: int | None = None
        if reply_to_telegram_message_id is not None:
            replied = await self.repo.get_by_telegram_identity(
                telegram_chat_id,
                reply_to_telegram_message_id,
            )
            if replied is not None:
                reply_to_id = replied.id

        message = await self.repo.create_message(
            conversation_id=conversation.id,
            direction="inbound",
            message_type=message_type,
            text=text,
            caption=caption,
            telegram_chat_id=telegram_chat_id,
            telegram_message_id=telegram_message_id,
            telegram_edit_date=telegram_edit_date,
            delivery_status="received",
            reply_to_message_id=reply_to_id,
            forward_source_label=forward_source_label,
        )
        for attachment in attachments or []:
            await self.repo.add_attachment(
                message,
                kind=attachment.kind,
                telegram_file_id=attachment.file_id,
                telegram_file_unique_id=attachment.file_unique_id,
                filename=attachment.filename,
                mime_type=attachment.mime_type,
                size=attachment.size,
                media_metadata=attachment.metadata,
            )

        increment_unread = True
        manager = await self.user_repo.get_manager()
        if manager is not None:
            try:
                increment_unread = not await manager_realtime_hub.is_viewing(
                    manager.id,
                    conversation.id,
                )
            except Exception:
                logger.exception("Failed to read manager viewing state; counting message unread")

        await self.repo.touch_inbound(conversation, increment_unread=increment_unread)
        return message, conversation, True

    async def capture_edit(
        self,
        *,
        telegram_chat_id: int,
        telegram_message_id: int,
        text: str | None,
        caption: str | None,
        telegram_edit_date: datetime | None,
    ) -> ChatMessage | None:
        message = await self.repo.get_by_telegram_identity(
            telegram_chat_id,
            telegram_message_id,
        )
        if message is None:
            return None
        old_rendered = message.text if message.text is not None else message.caption
        new_rendered = text if text is not None else caption
        if old_rendered == new_rendered:
            message.telegram_edit_date = telegram_edit_date
            await self.db.flush()
            return message

        await self.repo.add_revision(
            message,
            old_text=old_rendered,
            new_text=new_rendered,
            telegram_edit_date=telegram_edit_date,
        )
        message.text = text
        message.caption = caption
        message.telegram_edit_date = telegram_edit_date
        await self.db.flush()
        return message

    async def send_manager_message(
        self,
        *,
        conversation_id: int,
        client_request_id: str,
        text: str,
        reply_to_message_id: int | None = None,
    ) -> tuple[ChatMessage, ChatConversation, bool]:
        existing = await self.repo.get_by_client_request_id(client_request_id)
        if existing is not None:
            conversation = await self.repo.get_conversation(existing.conversation_id)
            if conversation is None:
                raise RuntimeError("Chat conversation disappeared for idempotent message")
            if conversation.id != conversation_id:
                raise LookupError("conversation_not_found")
            if existing.forward_source_message_id is not None or existing.message_type != "text":
                raise ValueError("client_request_conflict")
            if existing.delivery_status == "sent":
                return existing, conversation, False
            delivered, attempted = await self._attempt_text_delivery(existing, conversation)
            return delivered, conversation, attempted

        conversation = await self.repo.get_conversation(conversation_id)
        if conversation is None:
            raise LookupError("conversation_not_found")
        user = conversation.user
        if reply_to_message_id is not None:
            replied = await self.repo.get_message(reply_to_message_id)
            if replied is None or replied.conversation_id != conversation.id:
                raise LookupError("reply_message_not_found")

        message = await self.repo.create_message(
            conversation_id=conversation.id,
            direction="outbound",
            message_type="text",
            text=text,
            telegram_chat_id=user.telegram_id,
            delivery_status="pending",
            client_request_id=client_request_id,
            reply_to_message_id=reply_to_message_id,
        )
        await self.repo.touch_outbound(conversation)

        # Idempotency key должен стать durable до внешнего Telegram side effect.
        # После успешной доставки повтор запроса увидит pending-запись и не
        # отправит тот же текст второй раз при остановке процесса до финального commit.
        await self.db.commit()

        delivered, attempted = await self._attempt_text_delivery(message, conversation)
        return delivered, conversation, attempted

    async def _attempt_text_delivery(
        self,
        message: ChatMessage,
        conversation: ChatConversation,
    ) -> tuple[ChatMessage, bool]:
        claimed_at = datetime.now(UTC)
        claim_token = uuid4().hex
        claimed = await self.repo.claim_text_delivery(
            message_id=message.id,
            claim_token=claim_token,
            claimed_at=claimed_at,
            expired_before=claimed_at - TEXT_DELIVERY_LEASE,
        )
        if not claimed:
            current = await self.repo.get_message(message.id)
            return current or message, False
        await self.db.commit()
        await self.db.refresh(message)
        delivered = await self._deliver_text_message(
            message,
            conversation,
            claim_token=claim_token,
        )
        return delivered, True

    async def _deliver_text_message(
        self,
        message: ChatMessage,
        conversation: ChatConversation,
        *,
        claim_token: str,
    ) -> ChatMessage:
        user = conversation.user

        if user.telegram_id is None:
            message.delivery_status = "failed"
            await self.repo.release_text_delivery(
                message_id=message.id,
                claim_token=claim_token,
            )
            await self.db.flush()
            return message

        telegram_reply_message_id: int | None = None
        if message.reply_to_message_id is not None:
            replied = await self.repo.get_message(message.reply_to_message_id)
            if replied is not None:
                telegram_reply_message_id = replied.telegram_message_id

        outcome = DeliveryOutcome.FAILED
        try:
            async with sender_bot() as bot:
                if telegram_reply_message_id is None:
                    sent = await bot.send_message(chat_id=user.telegram_id, text=message.text or "")
                else:
                    sent = await bot.send_message(
                        chat_id=user.telegram_id,
                        text=message.text or "",
                        reply_parameters=ReplyParameters(message_id=telegram_reply_message_id),
                    )
            message.telegram_message_id = sent.message_id
            message.delivery_status = "sent"
            outcome = DeliveryOutcome.SENT
        except (TelegramBadRequest, TelegramForbiddenError, TelegramNotFound) as exc:
            if is_permanent_telegram_delivery_error(exc) or isinstance(
                exc,
                (TelegramForbiddenError, TelegramNotFound),
            ):
                outcome = DeliveryOutcome.INACCESSIBLE
            logger.warning(
                "Manager chat delivery failed: conversation_id=%s user_id=%s error=%s",
                conversation.id,
                user.id,
                type(exc).__name__,
            )
            message.delivery_status = "failed"
        except Exception:
            logger.exception(
                "Manager chat delivery failed unexpectedly: conversation_id=%s user_id=%s",
                conversation.id,
                user.id,
            )
            message.delivery_status = "failed"

        reconcile_telegram_write_access(user, outcome, operation="manager_chat_reply")
        await self.repo.release_text_delivery(
            message_id=message.id,
            claim_token=claim_token,
        )
        await self.db.flush()
        return message

    async def mark_read(self, conversation_id: int) -> ChatConversation:
        conversation = await self.repo.get_conversation(conversation_id)
        if conversation is None:
            raise LookupError("conversation_not_found")
        await self.repo.mark_read(conversation)
        return conversation

    async def close_conversation(self, conversation_id: int) -> ChatConversation:
        conversation = await self.repo.get_conversation(conversation_id)
        if conversation is None:
            raise LookupError("conversation_not_found")
        await self.repo.close(conversation)
        return conversation

    async def conversation_out(self, conversation: ChatConversation) -> ChatConversationOut:
        """Сериализовать одну беседу через общий bulk-контракт обогащения."""
        return (await self.conversations_out([conversation]))[0]

    async def conversations_out(
        self,
        conversations: list[ChatConversation],
    ) -> list[ChatConversationOut]:
        """Сериализовать страницу бесед без запросов внутри item-loop."""
        latest_messages = await self.repo.latest_messages_by_conversation(
            [conversation.id for conversation in conversations]
        )
        latest_orders = await self.order_repo.latest_by_user_ids(
            [conversation.user_id for conversation in conversations]
        )
        return [
            ChatConversationOut(
                id=conversation.id,
                status=conversation.status,
                unreadCount=conversation.unread_count,
                lastMessageAt=conversation.last_message_at,
                user=self.user_out(conversation.user),
                lastMessage=(
                    self.message_out(latest_messages[conversation.id])
                    if conversation.id in latest_messages
                    else None
                ),
                latestOrder=(
                    self.order_out(latest_orders[conversation.user_id])
                    if conversation.user_id in latest_orders
                    else None
                ),
            )
            for conversation in conversations
        ]

    @staticmethod
    def user_out(user: User) -> ManagerChatUser:
        return ManagerChatUser(
            id=user.id,
            telegramId=user.telegram_id,
            username=user.username,
            firstName=user.first_name,
            lastName=user.last_name,
            photoUrl=user.photo_url,
        )

    @staticmethod
    def message_out(message: ChatMessage) -> ChatMessageOut:
        return ChatMessageOut(
            id=message.id,
            conversationId=message.conversation_id,
            direction=message.direction,
            messageType=message.message_type,
            text=message.text,
            caption=message.caption,
            deliveryStatus=message.delivery_status,
            telegramMessageId=message.telegram_message_id,
            replyToMessageId=message.reply_to_message_id,
            forwardSourceLabel=message.forward_source_label,
            edited=message.telegram_edit_date is not None,
            createdAt=message.createdAt,
            updatedAt=message.updatedAt,
            attachments=[
                ChatAttachmentOut(
                    id=attachment.id,
                    kind=attachment.kind,
                    fileId=attachment.telegram_file_id,
                    fileUniqueId=attachment.telegram_file_unique_id,
                    filename=attachment.filename,
                    mimeType=attachment.mime_type,
                    size=attachment.size,
                    metadata=attachment.media_metadata or {},
                )
                for attachment in message.__dict__.get("attachments", [])
            ],
        )

    @staticmethod
    def order_out(order: Order) -> ManagerOrderSummary:
        from app.services.order_rate import build_order_rate_presentation

        city = getattr(order, "city", None)
        rate_presentation = build_order_rate_presentation(order)
        return ManagerOrderSummary(
            id=order.id,
            publicNumber=order.publicNumber,
            currencySell=order.currencySell,
            amountSell=order.amountSell,
            currencyBuy=order.currencyBuy,
            amountBuy=order.amountBuy,
            rate=rate_presentation.value if rate_presentation else None,
            rateDisplay=rate_presentation.value_display if rate_presentation else None,
            rateText=rate_presentation.text if rate_presentation else None,
            country=order.country,
            city=(
                ManagerOrderCity(
                    id=city.id,
                    name=city.name,
                    country=city.country,
                    countryRuName=city.country.ru_name,
                    countryCode=city.country.code,
                    countryFlag=city.country.flag,
                )
                if city is not None
                else None
            ),
            status=order.status,
            methodGet=order.methodGet,
            createdAt=order.createdAt,
        )

    async def publish_message_created(
        self,
        message: ChatMessage,
        conversation: ChatConversation,
    ) -> None:
        await trigger_manager_refresh(await self.user_repo.get_manager(), "chat.message.created")
        await self._notify_manager_if_offline(message, conversation)

    async def publish_message_updated(self, message: ChatMessage) -> None:
        await trigger_manager_refresh(await self.user_repo.get_manager(), "chat.message.updated")

    async def publish_outbound(self, message: ChatMessage, conversation: ChatConversation) -> None:
        del message, conversation
        await trigger_manager_refresh(await self.user_repo.get_manager(), "chat.message.updated")

    async def publish_read(self, conversation: ChatConversation) -> None:
        unread_total = await self.repo.unread_total()
        payload = {
            "conversationId": conversation.id,
            "unreadCount": conversation.unread_count,
            "unreadTotal": unread_total,
        }
        await manager_realtime_hub.publish("chat.read.updated", payload)
        await manager_realtime_hub.publish("chat.unread.updated", payload)

    async def _notify_manager_if_offline(
        self,
        message: ChatMessage,
        conversation: ChatConversation,
    ) -> None:
        manager = await self.user_repo.get_manager()
        if manager is None or manager.telegram_id is None:
            return
        try:
            if await manager_realtime_hub.is_online(manager.id):
                return
        except Exception:
            logger.exception("Failed to read manager presence; sending Telegram fallback")

        customer = conversation.user
        translate = get_user_translator(manager)
        display_name = " ".join(
            part for part in [customer.first_name, customer.last_name] if part
        ).strip() or (
            f"@{customer.username}"
            if customer.username
            else translate("manager-chat-fallback-anonymous", user_id=customer.id)
        )
        preview = (
            message.text
            or message.caption
            or translate(
                "manager-chat-fallback-media",
                media_type=message.message_type,
            )
        )
        if len(preview) > 300:
            preview = f"{preview[:297]}…"
        text = (
            f"<b>{html.escape(translate('manager-chat-fallback-title'))}</b>\n\n"
            f"<b>{html.escape(display_name)}</b>\n"
            f"{html.escape(preview)}"
        )
        reply_markup: InlineKeyboardMarkup | None = None
        manager_app_url = build_manager_workspace_url(conversation_id=conversation.id)
        if manager_app_url:
            reply_markup = InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text=translate("manager-chat-fallback-open"),
                            web_app=WebAppInfo(url=manager_app_url),
                        )
                    ]
                ]
            )
        try:
            async with sender_bot() as bot:
                await bot.send_message(
                    chat_id=manager.telegram_id,
                    text=text,
                    reply_markup=reply_markup,
                )
        except Exception:
            logger.exception(
                "Failed to send manager chat fallback notification: manager_id=%s",
                manager.id,
            )
