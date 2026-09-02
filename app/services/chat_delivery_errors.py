"""Безопасные коды причин отказа Telegram для журналов менеджерского чата."""

from __future__ import annotations

from aiogram.exceptions import TelegramBadRequest


def telegram_rejection_reason(exc: Exception) -> str:
    """Возвращает только фиксированный код, никогда не возвращает текст исключения."""
    if not isinstance(exc, TelegramBadRequest):
        return "telegram_rejected"
    description = exc.message.casefold().removeprefix("bad request: ").strip()
    # Allowlist намеренно не выводит неизвестный ответ: он может содержать payload.
    return {
        "chat not found": "chat_not_found",
        "user is deactivated": "user_deactivated",
        "wrong file identifier/http url specified": "invalid_file",
        "voice_messages_forbidden": "voice_messages_forbidden",
        "message to be replied not found": "reply_message_not_found",
        "video_content_type_invalid": "invalid_media",
        "file is too big": "file_too_large",
    }.get(description, "telegram_bad_request")
