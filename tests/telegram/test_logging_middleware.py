from __future__ import annotations

import logging

import pytest
from aiogram.types import Message, Update

from app.telegram.middlewares.logging import LoggingMiddleware


@pytest.mark.asyncio
async def test_logging_middleware_excludes_message_content_and_username(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Telegram INFO-логи не должны содержать пользовательские данные."""
    event = Update.model_validate(
        {
            "update_id": 1,
            "message": {
                "message_id": 1,
                "date": 1_717_871_000,
                "chat": {"id": 7, "type": "private"},
                "from": {
                    "id": 7,
                    "is_bot": False,
                    "first_name": "Client",
                    "username": "secret_user",
                },
                "text": "секретный текст клиента",
            },
        }
    ).message
    assert isinstance(event, Message)

    async def handler(_, __):
        return None

    with caplog.at_level(logging.INFO):
        await LoggingMiddleware()(handler, event, {"event_from_user": event.from_user})

    messages = "\n".join(record.getMessage() for record in caplog.records)
    assert "секретный текст клиента" not in messages
    assert "secret_user" not in messages
    assert "event=Message" in messages
