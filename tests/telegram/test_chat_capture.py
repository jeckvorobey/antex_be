from __future__ import annotations

from types import SimpleNamespace

from app.telegram.handlers.chat import _normalize_message


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
