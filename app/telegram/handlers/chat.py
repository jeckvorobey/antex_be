"""Приём свободных личных сообщений в единый чат менеджера."""

from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.types import Message

from app.core.database import create_db_session
from app.enums.user import has_operator_access
from app.services.chat import ChatService, InboundAttachment
from app.telegram.exceptions import TelegramCaptureRetryError
from app.telegram.services.user_service import check_user

logger = logging.getLogger(__name__)
router = Router(name="manager-chat-capture")


def _normalize_message(message: Message) -> tuple[str, list[InboundAttachment]]:
    """Преобразовать Telegram media в единый durable attachment contract."""
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
    if message.sticker:
        sticker = message.sticker
        if sticker.is_animated:
            filename, mime_type = "sticker.tgs", "application/x-tgsticker"
        elif sticker.is_video:
            filename, mime_type = "sticker.webm", "video/webm"
        else:
            filename, mime_type = "sticker.webp", "image/webp"
        attachments.append(
            InboundAttachment(
                kind="sticker",
                file_id=sticker.file_id,
                file_unique_id=sticker.file_unique_id,
                filename=filename,
                mime_type=mime_type,
                size=sticker.file_size,
                metadata={
                    "width": sticker.width,
                    "height": sticker.height,
                    "isAnimated": sticker.is_animated,
                    "isVideo": sticker.is_video,
                    "type": sticker.type,
                    "emoji": sticker.emoji,
                    "setName": sticker.set_name,
                    "customEmojiId": sticker.custom_emoji_id,
                    "needsRepainting": sticker.needs_repainting,
                },
            )
        )
        return "sticker", attachments
    if message.animation:
        animation = message.animation
        attachments.append(
            InboundAttachment(
                kind="animation",
                file_id=animation.file_id,
                file_unique_id=animation.file_unique_id,
                filename=animation.file_name or "animation.mp4",
                mime_type=animation.mime_type or "video/mp4",
                size=animation.file_size,
                metadata={
                    "width": animation.width,
                    "height": animation.height,
                    "duration": animation.duration,
                },
            )
        )
        return "animation", attachments
    if message.audio:
        audio = message.audio
        attachments.append(
            InboundAttachment(
                kind="audio",
                file_id=audio.file_id,
                file_unique_id=audio.file_unique_id,
                filename=audio.file_name or "audio",
                mime_type=audio.mime_type or "audio/mpeg",
                size=audio.file_size,
                metadata={
                    "duration": audio.duration,
                    "performer": audio.performer,
                    "title": audio.title,
                },
            )
        )
        return "audio", attachments
    if message.video_note:
        video_note = message.video_note
        attachments.append(
            InboundAttachment(
                kind="video_note",
                file_id=video_note.file_id,
                file_unique_id=video_note.file_unique_id,
                filename="video-note.mp4",
                mime_type="video/mp4",
                size=video_note.file_size,
                metadata={
                    "duration": video_note.duration,
                    "length": video_note.length,
                },
            )
        )
        return "video_note", attachments
    if message.text is not None:
        return "text", attachments
    return "other", attachments


def _forward_source_label(message: Message) -> str | None:
    """Получить доступную подпись Telegram origin без раскрытия идентификаторов."""
    origin = message.forward_origin
    if origin is None:
        return None
    if origin.type == "user":
        label = origin.sender_user.full_name
    elif origin.type == "hidden_user":
        label = origin.sender_user_name
    elif origin.type == "chat":
        label = origin.sender_chat.title or origin.sender_chat.full_name
    elif origin.type == "channel":
        label = origin.chat.title
    else:
        label = None
    return label[:255] if label else None


async def _capture(message: Message, *, edited: bool = False) -> None:
    """Сохраняет через ChatService, затем публикует результат после commit."""
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
            forward_source_label=_forward_source_label(message),
        )
        await db.commit()
        if created:
            await service.publish_message_created(stored, conversation)


@router.message(F.chat.type == "private")
async def capture_unhandled_private_message(message: Message) -> None:
    """Принимает сообщения, не занятые командами и шагами оформления заявки."""
    if message.text is not None and message.text.startswith("/"):
        return
    try:
        await _capture(message)
    except Exception as exc:
        logger.exception(
            "Failed to capture Telegram chat message: chat_id=%s message_id=%s",
            message.chat.id,
            message.message_id,
        )
        raise TelegramCaptureRetryError("Telegram chat capture requires retry") from exc


@router.edited_message(F.chat.type == "private")
async def capture_edited_private_message(message: Message) -> None:
    """Сохраняет редактирование сообщения в существующей истории."""
    try:
        await _capture(message, edited=True)
    except Exception as exc:
        logger.exception(
            "Failed to capture edited Telegram chat message: chat_id=%s message_id=%s",
            message.chat.id,
            message.message_id,
        )
        raise TelegramCaptureRetryError("Edited Telegram chat capture requires retry") from exc
