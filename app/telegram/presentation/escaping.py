# ruff: noqa: RUF002
"""Контекстное экранирование динамических значений Telegram."""

from __future__ import annotations

from html import escape
from urllib.parse import quote


def escape_html(value: object) -> str:
    """Возвращает значение, безопасное для Rich и regular HTML текста."""
    return escape(str(value), quote=True)


def escape_url_parameter(value: object) -> str:
    """Кодирует значение только для URL/query, не смешивая это с HTML escaping."""
    return quote(str(value), safe="")
