"""Нативная пересылка Telegram; durable источник и delivery lease."""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from uuid import uuid4

from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramNotFound
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chat import ChatConversation, ChatMessage
from app.repositories.chat import ChatRepository
from app.services.chat import TEXT_DELIVERY_LEASE
from app.services.order_notifications import (
    DeliveryOutcome,
    reconcile_telegram_write_access,
)
from app.telegram.bot import sender_bot

logger = logging.getLogger(__name__)


async def forward_manager_message(
    db: AsyncSession,
    *,
    conversation_id: int,
    manager_id: int | None = None,
    client_request_id: str,
    source_message_id: int,
) -> tuple[ChatMessage, ChatConversation, bool]:
    """Сохранить источник и метаданные до внешней отправки; повторить по ключу."""
    repo = ChatRepository(db, manager_id=manager_id)
    conversation = await repo.get_conversation(conversation_id)
    if conversation is None:
        raise LookupError("conversation_not_found")
    message = await repo.get_by_client_request_id(client_request_id)
    if message is not None:
        if message.conversation_id != conversation_id:
            raise LookupError("conversation_not_found")
        if message.forward_source_message_id != source_message_id:
            raise ValueError("client_request_conflict")
        if message.delivery_status == "sent":
            return message, conversation, False
    source = await repo.get_message(source_message_id)
    if source is None:
        raise LookupError("forward_source_not_found")
    if (
        source.delivery_status not in {"received", "sent"}
        or source.telegram_chat_id is None
        or source.telegram_message_id is None
    ):
        raise ValueError("forward_source_unavailable")
    source_chat = await repo.get_conversation(source.conversation_id)
    if source_chat is None:
        raise LookupError("forward_source_not_found")
    if message is None:
        user = source_chat.user
        label = source.forward_source_label or (
            (
                " ".join(part for part in [user.first_name, user.last_name] if part)
                or (f"@{user.username}" if user.username else "Клиент")
            )
            if source.direction == "inbound"
            else "AntEx"
        )
        try:
            async with db.begin_nested():
                message = await repo.create_message(
                    conversation_id=conversation.id,
                    direction="outbound",
                    message_type=source.message_type,
                    text=source.text,
                    caption=source.caption,
                    telegram_chat_id=conversation.user.telegram_id,
                    delivery_status="pending",
                    client_request_id=client_request_id,
                    forward_source_message_id=source.id,
                    forward_source_label=label[:255],
                )
                for attachment in source.attachments:
                    await repo.add_attachment(
                        message,
                        kind=attachment.kind,
                        telegram_file_id=attachment.telegram_file_id,
                        telegram_file_unique_id=attachment.telegram_file_unique_id,
                        filename=attachment.filename,
                        mime_type=attachment.mime_type,
                        size=attachment.size,
                        media_metadata=attachment.media_metadata,
                    )
                await repo.touch_outbound(conversation)
        except IntegrityError:
            # Параллельный запрос уже записал тот же durable ключ.
            return await forward_manager_message(
                db,
                manager_id=manager_id,
                conversation_id=conversation_id,
                client_request_id=client_request_id,
                source_message_id=source_message_id,
            )
        await db.commit()
    claimed_at = datetime.now(UTC)
    claim_token = uuid4().hex
    claimed = await repo.claim_text_delivery(
        message_id=message.id,
        claim_token=claim_token,
        claimed_at=claimed_at,
        expired_before=claimed_at - TEXT_DELIVERY_LEASE,
        forwarding=True,
    )
    await db.commit()
    if not claimed:
        return await repo.get_message(message.id) or message, conversation, False
    outcome = DeliveryOutcome.FAILED
    try:
        if conversation.user.telegram_id is None:
            raise ValueError("forward_target_unavailable")
        async with asyncio.timeout(60), sender_bot() as bot:
            sent = await bot.forward_message(
                chat_id=conversation.user.telegram_id,
                from_chat_id=source.telegram_chat_id,
                message_id=source.telegram_message_id,
            )
        message.telegram_message_id = sent.message_id
        message.delivery_status = "sent"
        outcome = DeliveryOutcome.SENT
    except (TelegramBadRequest, TelegramForbiddenError, TelegramNotFound) as exc:
        # Protected content остаётся failed: никакой подмены forward на copy/send.
        message.delivery_status = "failed"
        if isinstance(exc, TelegramForbiddenError):
            outcome = DeliveryOutcome.INACCESSIBLE
        logger.warning(
            "Manager forward failed: message_id=%s error=%s", message.id, type(exc).__name__
        )
    except Exception as exc:
        message.delivery_status = "failed"
        logger.warning(
            "Manager forward failed: message_id=%s error=%s", message.id, type(exc).__name__
        )
    reconcile_telegram_write_access(conversation.user, outcome, operation="manager_chat_forward")
    await repo.release_text_delivery(message_id=message.id, claim_token=claim_token)
    await db.flush()
    return await repo.get_message(message.id) or message, conversation, True
