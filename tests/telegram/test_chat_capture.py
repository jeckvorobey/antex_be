from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.telegram.exceptions import TelegramCaptureRetryError
from app.telegram.handlers.chat import (
    _normalize_message,
    capture_edited_private_message,
    capture_unhandled_private_message,
)


def _message(**values):
    defaults = {
        "photo": None,
        "document": None,
        "voice": None,
        "video": None,
        "text": None,
    }
    defaults.update(values)
    return SimpleNamespace(**defaults)


def test_normalize_text_message() -> None:
    kind, attachments = _normalize_message(_message(text="hello"))

    assert kind == "text"
    assert attachments == []


def test_normalize_document_attachment() -> None:
    document = SimpleNamespace(
        file_id="file-1",
        file_unique_id="unique-1",
        file_name="receipt.pdf",
        mime_type="application/pdf",
        file_size=512,
    )
    kind, attachments = _normalize_message(_message(document=document))

    assert kind == "document"
    assert len(attachments) == 1
    assert attachments[0].file_id == "file-1"
    assert attachments[0].filename == "receipt.pdf"


async def test_transient_failure_of_regular_update_is_raised_for_redelivery(monkeypatch) -> None:
    """Временная ошибка capture должна оставить обычный Telegram update неподтверждённым."""

    async def fail_capture(_message, *, edited: bool = False) -> None:
        assert edited is False
        raise RuntimeError("temporary database outage")

    monkeypatch.setattr("app.telegram.handlers.chat._capture", fail_capture)
    message = SimpleNamespace(text="Привет", chat=SimpleNamespace(id=101), message_id=11)

    with pytest.raises(TelegramCaptureRetryError) as exc_info:
        await capture_unhandled_private_message(message)
    assert isinstance(exc_info.value.__cause__, RuntimeError)


async def test_transient_failure_of_edited_update_is_raised_for_redelivery(monkeypatch) -> None:
    """Временная ошибка capture должна оставить edited Telegram update неподтверждённым."""

    async def fail_capture(_message, *, edited: bool = False) -> None:
        assert edited is True
        raise RuntimeError("temporary redis outage")

    monkeypatch.setattr("app.telegram.handlers.chat._capture", fail_capture)
    message = SimpleNamespace(chat=SimpleNamespace(id=102), message_id=12)

    with pytest.raises(TelegramCaptureRetryError) as exc_info:
        await capture_edited_private_message(message)
    assert isinstance(exc_info.value.__cause__, RuntimeError)
