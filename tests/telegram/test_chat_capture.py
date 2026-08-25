from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.telegram.exceptions import TelegramCaptureRetryError
from app.telegram.handlers import chat as chat_handler
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
        "sticker": None,
        "animation": None,
        "audio": None,
        "video_note": None,
        "text": None,
    }
    defaults.update(values)
    return SimpleNamespace(**defaults)


def test_normalize_text_message() -> None:
    kind, attachments = _normalize_message(_message(text="hello"))

    assert kind == "text"
    assert attachments == []


async def test_official_chat_callback_clears_fsm_and_prompts_in_user_locale() -> None:
    """Переход в bot conversation освобождает сообщение от активного exchange FSM."""
    callback = SimpleNamespace(
        from_user=SimpleNamespace(language_code="en"),
        answer=AsyncMock(),
    )
    state = SimpleNamespace(clear=AsyncMock())

    await chat_handler.open_official_manager_chat(callback, state)

    state.clear.assert_awaited_once()
    callback.answer.assert_awaited_once_with(
        "Send your message in this bot chat. The manager will reply here.",
        show_alert=True,
    )


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


@pytest.mark.parametrize(
    ("field", "media", "expected_kind", "expected_filename", "expected_mime", "metadata"),
    [
        (
            "sticker",
            SimpleNamespace(
                file_id="sticker-file",
                file_unique_id="sticker-unique",
                file_size=111,
                width=512,
                height=512,
                is_animated=False,
                is_video=False,
                type="regular",
                emoji="🙂",
                set_name="antex_pack",
                custom_emoji_id=None,
                needs_repainting=False,
            ),
            "sticker",
            "sticker.webp",
            "image/webp",
            {
                "width": 512,
                "height": 512,
                "isAnimated": False,
                "isVideo": False,
                "type": "regular",
                "emoji": "🙂",
                "setName": "antex_pack",
                "customEmojiId": None,
                "needsRepainting": False,
            },
        ),
        (
            "animation",
            SimpleNamespace(
                file_id="animation-file",
                file_unique_id="animation-unique",
                file_name="loop.mp4",
                mime_type="video/mp4",
                file_size=222,
                width=640,
                height=360,
                duration=3,
            ),
            "animation",
            "loop.mp4",
            "video/mp4",
            {"width": 640, "height": 360, "duration": 3},
        ),
        (
            "audio",
            SimpleNamespace(
                file_id="audio-file",
                file_unique_id="audio-unique",
                file_name="track.mp3",
                mime_type="audio/mpeg",
                file_size=333,
                duration=120,
                performer="AntEx",
                title="Rate Song",
            ),
            "audio",
            "track.mp3",
            "audio/mpeg",
            {"duration": 120, "performer": "AntEx", "title": "Rate Song"},
        ),
        (
            "video_note",
            SimpleNamespace(
                file_id="note-file",
                file_unique_id="note-unique",
                file_size=444,
                duration=7,
                length=240,
            ),
            "video_note",
            "video-note.mp4",
            "video/mp4",
            {"duration": 7, "length": 240},
        ),
    ],
)
def test_normalize_common_media_metadata(
    field: str,
    media: SimpleNamespace,
    expected_kind: str,
    expected_filename: str,
    expected_mime: str,
    metadata: dict[str, object],
) -> None:
    """Частые Telegram media types сохраняют render/download metadata."""
    kind, attachments = _normalize_message(_message(**{field: media}))

    assert kind == expected_kind
    assert len(attachments) == 1
    assert attachments[0].file_id == media.file_id
    assert attachments[0].file_unique_id == media.file_unique_id
    assert attachments[0].filename == expected_filename
    assert attachments[0].mime_type == expected_mime
    assert attachments[0].size == media.file_size
    assert attachments[0].metadata == metadata


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
