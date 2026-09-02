"""Outbound and download helpers for manager chat attachments."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from io import BytesIO
from uuid import uuid4

from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramNotFound
from aiogram.types import BufferedInputFile, Message, ReplyParameters
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chat import ChatAttachment, ChatConversation, ChatMessage
from app.repositories.chat import ChatRepository
from app.services.chat_media import normalize_recording
from app.services.order_notifications import (
    DeliveryOutcome,
    is_permanent_telegram_delivery_error,
    reconcile_telegram_write_access,
)
from app.telegram.bot import sender_bot

logger = logging.getLogger(__name__)

ALLOWED_ATTACHMENT_KINDS = frozenset({"photo", "document", "voice", "video", "video_note"})
MAX_MANAGER_ATTACHMENT_BYTES = 20 * 1024 * 1024
ATTACHMENT_DELIVERY_LEASE = timedelta(minutes=2)


def _sent_file(message: Message, kind: str):
    if kind == "photo" and message.photo:
        return message.photo[-1]
    if kind == "video" and message.video:
        return message.video
    if kind == "voice" and message.voice:
        return message.voice
    if kind == "video_note" and message.video_note:
        return message.video_note
    if message.document:
        return message.document
    return None


async def send_manager_attachment(
    db: AsyncSession,
    *,
    conversation_id: int,
    client_request_id: str,
    content: bytes | None,
    filename: str,
    mime_type: str,
    kind: str,
    reply_to_message_id: int | None = None,
) -> tuple[ChatMessage, ChatConversation, bool]:
    repo = ChatRepository(db)
    existing = await repo.get_by_client_request_id(client_request_id)
    if existing is not None:
        conversation = await repo.get_conversation(existing.conversation_id)
        if conversation is None:
            raise RuntimeError("Chat conversation disappeared for idempotent attachment")
        if conversation.id != conversation_id:
            raise LookupError("conversation_not_found")
        if existing.forward_source_message_id is not None or existing.message_type != kind:
            raise ValueError("client_request_conflict")
        if existing.delivery_status == "sent":
            return existing, conversation, False
        return await retry_manager_attachment(
            db,
            conversation_id=conversation_id,
            client_request_id=client_request_id,
        )

    if kind not in ALLOWED_ATTACHMENT_KINDS:
        raise ValueError("unsupported_attachment_kind")
    if not content or len(content) > MAX_MANAGER_ATTACHMENT_BYTES:
        raise ValueError("invalid_attachment_size")

    conversation = await repo.get_conversation(conversation_id)
    if conversation is None:
        raise LookupError("conversation_not_found")
    if reply_to_message_id is not None:
        replied = await repo.get_message(reply_to_message_id)
        if replied is None or replied.conversation_id != conversation.id:
            raise LookupError("reply_message_not_found")
    metadata = None
    if kind in {"voice", "video_note"}:
        normalized = await normalize_recording(content, kind=kind)
        content, filename, mime_type = normalized.content, normalized.filename, normalized.mime_type
        metadata = normalized.metadata
    user = conversation.user
    message = await repo.create_message(
        conversation_id=conversation.id,
        direction="outbound",
        message_type=kind,
        text=None,
        caption=filename,
        telegram_chat_id=user.telegram_id,
        delivery_status="pending",
        client_request_id=client_request_id,
        reply_to_message_id=reply_to_message_id,
    )
    await repo.touch_outbound(conversation)
    attachment = await repo.add_attachment(
        message,
        kind=kind,
        telegram_file_id=None,
        filename=filename,
        mime_type=mime_type,
        size=len(content),
        payload=content,
        media_metadata=metadata,
    )

    # Bytes и metadata должны стать durable до внешнего Telegram side effect.
    await db.commit()
    delivered, attempted = await _attempt_manager_attachment_delivery(
        db,
        repo,
        message,
        conversation,
        attachment,
    )
    return delivered, conversation, attempted


async def retry_manager_attachment(
    db: AsyncSession,
    *,
    conversation_id: int,
    client_request_id: str,
) -> tuple[ChatMessage, ChatConversation, bool]:
    """Повторить failed/pending delivery из сохранённого database payload."""
    repo = ChatRepository(db)
    message = await repo.get_by_client_request_id(client_request_id)
    if message is None or message.conversation_id != conversation_id:
        raise LookupError("attachment_not_found")
    conversation = await repo.get_conversation(conversation_id)
    if conversation is None:
        raise LookupError("conversation_not_found")
    if message.delivery_status == "sent":
        return message, conversation, False
    attachment = message.attachments[0] if message.attachments else None
    if attachment is None or attachment.payload is None:
        raise ValueError("attachment_payload_unavailable")
    delivered, attempted = await _attempt_manager_attachment_delivery(
        db,
        repo,
        message,
        conversation,
        attachment,
    )
    return delivered, conversation, attempted


async def _attempt_manager_attachment_delivery(
    db: AsyncSession,
    repo: ChatRepository,
    message: ChatMessage,
    conversation: ChatConversation,
    attachment: ChatAttachment,
) -> tuple[ChatMessage, bool]:
    """Получить durable lease и выполнить не более одной Telegram attempt."""
    claimed_at = datetime.now(UTC)
    claim_token = uuid4().hex
    claimed = await repo.claim_attachment_delivery(
        attachment_id=attachment.id,
        message_id=message.id,
        claim_token=claim_token,
        claimed_at=claimed_at,
        expired_before=claimed_at - ATTACHMENT_DELIVERY_LEASE,
    )
    if not claimed:
        current = await repo.get_by_client_request_id(message.client_request_id or "")
        return current or message, False

    await db.refresh(message, attribute_names=["delivery_status"])
    delivered = await _deliver_manager_attachment(
        db,
        repo,
        message,
        conversation,
        attachment,
        claim_token=claim_token,
    )
    return delivered, True


async def _deliver_manager_attachment(
    db: AsyncSession,
    repo: ChatRepository,
    message: ChatMessage,
    conversation: ChatConversation,
    attachment: ChatAttachment,
    *,
    claim_token: str,
) -> ChatMessage:
    """Выполнить Telegram delivery ранее сохранённого вложения."""
    user = conversation.user
    kind = attachment.kind

    if user.telegram_id is None:
        message.delivery_status = "failed"
        await repo.release_attachment_delivery(
            attachment_id=attachment.id,
            claim_token=claim_token,
        )
        await db.flush()
        return message

    outcome = DeliveryOutcome.FAILED
    try:
        payload = attachment.payload
        if payload is None:
            raise ValueError("attachment_payload_unavailable")
        filename = attachment.filename or "attachment"
        upload = BufferedInputFile(payload, filename=filename)
        reply_options = {}
        if message.reply_to_message_id is not None:
            replied = await repo.get_message(message.reply_to_message_id)
            if replied is not None and replied.telegram_message_id is not None:
                reply_options["reply_parameters"] = ReplyParameters(
                    message_id=replied.telegram_message_id,
                )
        async with sender_bot() as bot:
            if kind == "photo":
                sent = await bot.send_photo(chat_id=user.telegram_id, photo=upload, **reply_options)
            elif kind == "video":
                sent = await bot.send_video(chat_id=user.telegram_id, video=upload, **reply_options)
            elif kind == "video_note":
                sent = await bot.send_video_note(
                    chat_id=user.telegram_id, video_note=upload, **reply_options
                )
            elif kind == "voice":
                sent = await bot.send_voice(chat_id=user.telegram_id, voice=upload, **reply_options)
            else:
                sent = await bot.send_document(
                    chat_id=user.telegram_id, document=upload, **reply_options
                )
        message.telegram_message_id = sent.message_id
        message.delivery_status = "sent"
        outcome = DeliveryOutcome.SENT
        sent_file = _sent_file(sent, kind)
        if sent_file is not None:
            attachment.telegram_file_id = sent_file.file_id
            attachment.telegram_file_unique_id = sent_file.file_unique_id
        # Telegram подтвердил delivery, поэтому database payload больше не нужен.
        attachment.payload = None
    except (TelegramBadRequest, TelegramForbiddenError, TelegramNotFound) as exc:
        if is_permanent_telegram_delivery_error(exc) or isinstance(
            exc,
            (TelegramForbiddenError, TelegramNotFound),
        ):
            outcome = DeliveryOutcome.INACCESSIBLE
        message.delivery_status = "failed"
        logger.warning(
            "Manager attachment delivery failed: conversation_id=%s kind=%s error=%s",
            conversation.id,
            kind,
            type(exc).__name__,
        )
    except Exception as exc:
        message.delivery_status = "failed"
        logger.warning(
            "Manager attachment delivery failed unexpectedly: conversation_id=%s kind=%s error=%s",
            conversation.id,
            kind,
            type(exc).__name__,
        )

    reconcile_telegram_write_access(user, outcome, operation="manager_chat_attachment")
    await repo.release_attachment_delivery(
        attachment_id=attachment.id,
        claim_token=claim_token,
    )
    await db.flush()
    reloaded = await repo.get_message(message.id)
    return reloaded or message


async def download_manager_attachment(attachment: ChatAttachment) -> bytes:
    """Скачать payload из БД до delivery либо по Telegram file id после него."""
    if attachment.payload is not None:
        return attachment.payload
    if attachment.telegram_file_id is None:
        raise FileNotFoundError("Telegram file id is unavailable")
    async with sender_bot() as bot:
        telegram_file = await bot.get_file(attachment.telegram_file_id)
        if not telegram_file.file_path:
            raise FileNotFoundError("Telegram file path is unavailable")
        downloaded = await bot.download_file(telegram_file.file_path)
    if downloaded is None:
        raise FileNotFoundError("Telegram file download returned no content")
    if isinstance(downloaded, BytesIO):
        return downloaded.getvalue()
    downloaded.seek(0)
    return downloaded.read()
