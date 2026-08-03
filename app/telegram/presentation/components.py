# ruff: noqa: RUF002
"""Небольшие композиционные компоненты Rich и regular HTML сообщений."""

from __future__ import annotations

import re
from collections.abc import Iterable
from html import unescape

from app.telegram.presentation.escaping import escape_html
from app.telegram.presentation.models import TelegramMessageSpec


def truncate_text(value: str, *, limit: int) -> str:
    """Сокращает только свободный текст, оставляя видимый маркер сокращения."""
    if limit < 2:
        msg = "Лимит сокращения должен оставлять место для маркера"
        raise ValueError(msg)
    if len(value) <= limit:
        return value
    return f"{value[: limit - 1]}…"


def strip_telegram_html(value: str) -> str:
    """Убирает trusted regular HTML tags перед вставкой текста в Rich component."""
    return unescape(re.sub(r"<[^>]*>", "", value)).strip()


def build_message(
    *,
    family: str,
    eyebrow: str,
    title: str,
    lead: str,
    facts: Iterable[tuple[str, str]] = (),
    notice: str | None = None,
    action: str | None = None,
    category: str = "system",
) -> TelegramMessageSpec:
    """Собирает компактную mobile-first карточку с эквивалентным fallback."""
    safe_facts = [(escape_html(label), escape_html(value)) for label, value in facts if value]
    rich_parts = [
        f"<footer>{escape_html(eyebrow)}</footer>",
        f"<h2>{escape_html(title)}</h2>",
        f"<p>{escape_html(lead)}</p>",
    ]
    fallback_parts = [f"<b>{escape_html(title)}</b>", escape_html(lead)]

    if safe_facts:
        rows = "".join(
            f"<tr><td>{label}</td><td><b>{value}</b></td></tr>" for label, value in safe_facts
        )
        rich_parts.append(f"<hr/><table bordered striped>{rows}</table>")
        fallback_parts.extend(f"<b>{label}:</b> {value}" for label, value in safe_facts)
    if notice:
        rich_parts.append(f"<aside>{escape_html(notice)}</aside>")
        fallback_parts.append(f"<blockquote>{escape_html(notice)}</blockquote>")
    if action:
        rich_parts.append(f"<p><b>{escape_html(action)}</b></p>")
        fallback_parts.append(f"<b>{escape_html(action)}</b>")

    return TelegramMessageSpec(
        family=family,
        rich_html="".join(rich_parts),
        fallback_html="\n\n".join(fallback_parts),
        category=category,
    )
