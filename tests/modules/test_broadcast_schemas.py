"""Проверки preflight-ограничений Telegram-рассылок."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.modules.broadcasts.schemas import BroadcastCreate


def test_broadcast_rejects_text_longer_than_regular_telegram_limit() -> None:
    """Невалидная рассылка не должна сохраняться и обрываться при массовой отправке."""
    with pytest.raises(ValidationError):
        BroadcastCreate(text="x" * 4097)
