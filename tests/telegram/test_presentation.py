# ruff: noqa: RUF002
"""Контрактные тесты общего presentation-layer Telegram."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from aiogram.exceptions import TelegramBadRequest

from app.telegram.presentation.components import build_message, truncate_text
from app.telegram.presentation.delivery import DeliveryKind, deliver
from app.telegram.presentation.escaping import escape_html, escape_url_parameter


def test_dynamic_values_are_escaped_for_html_and_url() -> None:
    """Пользовательские значения не должны становиться Telegram-разметкой или query-параметром."""
    value = '<b>Аня & "друзья"</b>'

    assert escape_html(value) == "&lt;b&gt;Аня &amp; &quot;друзья&quot;&lt;/b&gt;"
    assert escape_url_parameter(value) == (
        "%3Cb%3E%D0%90%D0%BD%D1%8F%20%26%20%22%D0%B4%D1%80%D1%83%D0%B7%D1%8C%D1%8F%22%3C%2Fb%3E"
    )


def test_message_preserves_facts_in_rich_and_html_fallback() -> None:
    """Rich и regular HTML должны содержать один набор бизнес-фактов."""
    spec = build_message(
        family="summary",
        eyebrow="Новая заявка",
        title="Заявка #2026080001 принята",
        lead="Мы получили запрос.",
        facts=(("Отдаёте", "10 000 RUB"), ("Получаете", "3 400 THB")),
        action="Ожидайте сообщения менеджера.",
    )

    for fact in ("2026080001", "10 000 RUB", "3 400 THB", "Ожидайте"):
        assert fact in spec.rich_html
        assert fact in spec.fallback_html
    assert "<h2>" in spec.rich_html
    assert "<table" in spec.rich_html
    assert "<b>" in spec.fallback_html


def test_truncate_text_marks_only_truncated_value() -> None:
    """Сокращение длинного свободного поля должно быть явным и предсказуемым."""
    assert truncate_text("abcdef", limit=6) == "abcdef"
    assert truncate_text("abcdef", limit=5) == "abcd…"


class _RichBot:
    """Минимальный bot fake для проверки delivery policy."""

    def __init__(self, *, rich_error: Exception | None = None) -> None:
        self.rich_error = rich_error
        self.calls: list[str] = []

    async def send_rich_message(self, **kwargs):
        self.calls.append("rich")
        if self.rich_error is not None:
            raise self.rich_error
        return SimpleNamespace(message_id=1)

    async def send_message(self, **kwargs):
        self.calls.append("html")
        return SimpleNamespace(message_id=2)


@pytest.mark.asyncio
async def test_delivery_uses_html_once_when_rich_is_unsupported() -> None:
    """400 о неподдерживаемом Rich запускает ровно один regular HTML fallback."""
    error = TelegramBadRequest(
        method=SimpleNamespace(__api_method__="sendRichMessage"),
        message="Bad Request: method is not available",
    )
    bot = _RichBot(rich_error=error)
    spec = build_message(
        family="status",
        eyebrow="Статус",
        title="Готово",
        lead="Заявка сохранена.",
    )

    outcome = await deliver(bot, chat_id=1, spec=spec, kind=DeliveryKind.SEND)

    assert outcome.delivered is True
    assert outcome.used_fallback is True
    assert bot.calls == ["rich", "html"]


@pytest.mark.asyncio
async def test_delivery_does_not_fallback_for_network_error() -> None:
    """Сетевая ошибка не доказывает несовместимость Rich и не должна дублировать сообщение."""
    bot = _RichBot(rich_error=OSError("network unavailable"))
    spec = build_message(
        family="status",
        eyebrow="Статус",
        title="Готово",
        lead="Заявка сохранена.",
    )

    outcome = await deliver(bot, chat_id=1, spec=spec, kind=DeliveryKind.SEND)

    assert outcome.delivered is False
    assert outcome.used_fallback is False
    assert bot.calls == ["rich"]
