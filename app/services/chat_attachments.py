"""Outbound and download helpers for manager chat attachments."""

from __future__ import annotations

import logging
from io import BytesIO

from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramNotFound
from aiogram.types import BufferedInputFile, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chat import ChatAttachment, ChatConversation, ChatMessage
from app.repositories.chat import ChatRepository
from app.services.order_notifications import (
    DeliveryOutcome,
    is_permanent_telegram_delivery_error,
    reconcile_telegram_write_access,
)
from app.telegram.bot import sender_bot

logger = logging.getLogger(__name__)

ALLOWED_ATTACHMENT_KINDS = frozenset({"photo", "document", "voice", "video"})
MAX_MANAGER_ATTACHMENT_BYTES = 20 * 1024 * 1024


def _sent_file(message: Message, kind: str):
    if kind == "photo" and message.photo:
        return message.photo[-1]
    if kind == "video" and message.video:
        return message.video
    if kind == "voice" and message.voice:
        return message.voice
    if message.document:
        return message.document
    return None


async def send_manager_attachment(
    db: AsyncSession,
    *,
    conversation_id: int,
    client_request_id: str,
    content: bytes,
    filename: str,
    mime_type: str,
    kind: str,
) -> tuple[ChatMessage, ChatConversation, bool]:
    if kind not in ALLOWED_ATTACHMENT_KINDS:
        raise ValueError("unsupported_attachment_kind")
    if not content or len(content) > MAX_MANAGER_ATTACHMENT_BYTES:
        raise ValueError("invalid_attachment_size")

    repo = ChatRepository(db)
    existing = await repo.get_by_client_request_id(client_request_id)
    if existing is not None:
        conversation = await repo.get_conversation(existing.conversation_id)
        if conversation is None:
            raise RuntimeError("Chat conversation disappeared for idempotent attachment")
        return existing, conversation, False

    conversation = await repo.get_conversation(conversation_id)
    if conversation is None:
        raise LookupError("conversation_not_found")
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
    )
    await repo.touch_outbound(conversation)

    if user.telegram_id is None:
        message.delivery_status = "failed"
        await db.flush()
        return message, conversation, True

    outcome = DeliveryOutcome.FAILED
    try:
        upload = BufferedInputFile(content, filename=filename)
        async with sender_bot() as bot:
            if kind == "photo":
                sent = await bot.send_photo(chat_id=user.telegram_id, photo=upload)
            elif kind == "video":
                sent = await bot.send_video(chat_id=user.telegram_id, video=upload)
            elif kind == "voice":
                sent = await bot.send_voice(chat_id=user.telegram_id, voice=upload)
            else:
                sent = await bot.send_document(chat_id=user.telegram_id, document=upload)
        message.telegram_message_id = sent.message_id
        message.delivery_status = "sent"
        outcome = DeliveryOutcome.SENT
        sent_file = _sent_file(sent, kind)
        if sent_file is not None:
            await repo.add_attachment(
                message,
                kind=kind,
                telegram_file_id=sent_file.file_id,
                telegram_file_unique_id=sent_file.file_unique_id,
                filename=filename,
                mime_type=mime_type,
                size=len(content),
            )
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
    except Exception:
        message.delivery_status = "failed"
        logger.exception(
            "Manager attachment delivery failed unexpectedly: conversation_id=%s kind=%s",
            conversation.id,
            kind,
        )

    reconcile_telegram_write_access(user, outcome, operation="manager_chat_attachment")
    await db.flush()
    reloaded = await repo.get_message(message.id)
    return reloaded or message, conversation, True


async def download_manager_attachment(attachment: ChatAttachment) -> bytes:
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
