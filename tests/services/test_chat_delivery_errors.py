"""Регрессии безопасной диагностики Telegram без публикации текста исключений."""

from __future__ import annotations

import pytest
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramNotFound
from aiogram.methods import SendMessage

from app.services.chat_delivery_errors import telegram_rejection_reason


@pytest.mark.parametrize(
    "description,expected",
    [
        ("Bad Request: chat not found", "chat_not_found"),
        ("Bad Request: user is deactivated", "user_deactivated"),
        ("Bad Request: wrong file identifier/HTTP URL specified", "invalid_file"),
        ("Bad Request: VOICE_MESSAGES_FORBIDDEN", "voice_messages_forbidden"),
        ("Bad Request: VOICE_MESSAGES_FORBIDDEN private text", "telegram_bad_request"),
        ("Bad Request: 123456789:synthetic-secret / private message", "telegram_bad_request"),
    ],
)
def test_rejection_reason_never_returns_raw_description(description, expected):
    """Классифицирует известные причины, скрывая неизвестные детали и суффиксы."""
    error = TelegramBadRequest(
        method=SendMessage(chat_id=99001, text="private message"), message=description
    )
    assert telegram_rejection_reason(error) == expected


@pytest.mark.parametrize("error_type", [TelegramForbiddenError, TelegramNotFound, RuntimeError])
def test_other_error_types_do_not_expose_private_details(error_type):
    """Другие исключения сохраняют общий безопасный код без чужого payload."""
    error = (
        RuntimeError("private detail")
        if error_type is RuntimeError
        else error_type(
            method=SendMessage(chat_id=99001, text="private message"), message="private detail"
        )
    )
    assert telegram_rejection_reason(error) == "telegram_rejected"
