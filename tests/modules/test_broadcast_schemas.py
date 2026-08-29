"""Контракт типов кнопок рассылки."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.modules.broadcasts.schemas import BroadcastCreate


def test_broadcast_button_type_defaults_to_url() -> None:
    """Старые клиенты без button_type сохраняют прежнее поведение."""
    payload = BroadcastCreate(
        text="Новости AntEx",
        button_text="Открыть",
        button_url="https://example.test",
    )

    assert payload.button_type == "url"


def test_web_app_button_accepts_https_referral_route() -> None:
    """Mini App кнопка принимает прямой HTTPS URL hash-маршрута referral."""
    payload = BroadcastCreate(
        text="Реферальная программа",
        button_text="Реферальная программа",
        button_url="https://app.example.test/#/referral",
        button_type="web_app",
    )

    assert payload.button_type == "web_app"


def test_web_app_button_rejects_non_https_url() -> None:
    """Telegram WebAppInfo не должен получать URL без HTTPS."""
    with pytest.raises(ValidationError, match=r"web_app.*https"):
        BroadcastCreate(
            text="Реферальная программа",
            button_text="Открыть",
            button_url="http://app.example.test/#/referral",
            button_type="web_app",
        )
