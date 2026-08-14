"""Capture unhandled private Telegram messages for the manager workspace."""

from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.types import Message

from app.core.database import create_db_session
from app.enums.user import has_operator_access
from app.services.chat import ChatService, InboundAttachment
from app.telegram.services.user_service import check_user

logger = logging.getLogger(__name__)
router = Router(name="manager-chat-capture")


def _normalize_message(message: Message) -> tuple[str, list[InboundAttachment]]:
    attachments: list[InboundAttachment] = []
    if message.photo:
        photo = message.photo[-1]
        attachments.append(
            InboundAttachment(
                kind="photo",
                file_id=photo.file_id,
                file_unique_id=photo.file_unique_id,
                size=photo.file_size,
            )
        )
        return "photo", attachments
    if message.document:
        document = message.document
        attachments.append(
            InboundAttachment(
                kind="document",
                file_id=document.file_id,
                file_unique_id=document.file_unique_id,
                filename=document.file_name,
                mime_type=document.mime_type,
                size=document.file_size,
            )
        )
        return "document", attachments
    if message.voice:
        voice = message.voice
        attachments.append(
            InboundAttachment(
                kind="voice",
                file_id=voice.file_id,
                file_unique_id=voice.file_unique_id,
                mime_type=voice.mime_type,
                size=voice.file_size,
            )
        )
        return "voice", attachments
    if message.video:
        video = message.video
        attachments.append(
            InboundAttachment(
                kind="video",
                file_id=video.file_id,
                file_unique_id=video.file_unique_id,
                filename=video.file_name,
                mime_type=video.mime_type,
                size=video.file_size,
            )
        )
        return "video", attachments
    if message.text is not None:
        return "text", attachments
    return "other", attachments


async def _capture(message: Message, *, edited: bool = False) -> None:
    if message.from_user is None or message.from_user.is_bot:
        return

    async with create_db_session() as db:
        user, _ = await check_user(db, message.from_user)
        if has_operator_access(user.role):
            await db.commit()
            return

        service = ChatService(db)
        if edited:
            stored = await service.capture_edit(
                telegram_chat_id=message.chat.id,
                telegram_message_id=message.message_id,
                text=message.text,
                caption=message.caption,
                telegram_edit_date=message.edit_date,
            )
            if stored is not None:
                await db.commit()
                await service.publish_message_updated(stored)
                return

        message_type, attachments = _normalize_message(message)
        reply_to_telegram_message_id = (
            message.reply_to_message.message_id if message.reply_to_message is not None else None
        )
        stored, conversation, created = await service.capture_inbound(
            user=user,
            telegram_chat_id=message.chat.id,
            telegram_message_id=message.message_id,
            message_type=message_type,
            text=message.text,
            caption=message.caption,
            reply_to_telegram_message_id=reply_to_telegram_message_id,
            telegram_edit_date=message.edit_date if edited else None,
            attachments=attachments,
        )
        await db.commit()
        if created:
            await service.publish_message_created(stored, conversation)


@router.message(F.chat.type == "private")
async def capture_unhandled_private_message(message: Message) -> None:
    """Persist only messages not consumed by earlier start/exchange/operator handlers."""
    if message.text is not None and message.text.startswith("/"):
        return
    try:
        await _capture(message)
    except Exception:
        logger.exception(
            "Failed to capture Telegram chat message: chat_id=%s message_id=%s",
            message.chat.id,
            message.message_id,
        )


@router.edited_message(F.chat.type == "private")
async def capture_edited_private_message(message: Message) -> None:
    try:
        await _capture(message, edited=True)
    except Exception:
        logger.exception(
            "Failed to capture edited Telegram chat message: chat_id=%s message_id=%s",
            message.chat.id,
            message.message_id,
        )
