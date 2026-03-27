"""Fluent i18n helpers для Telegram бота."""

from __future__ import annotations

from collections.abc import Callable
from functools import cache
from pathlib import Path
from typing import Any

from fluent.runtime import FluentBundle, FluentResource

from app.core.config import settings

LOCALE_DIR = Path(__file__).resolve().parents[2] / "locale"
Translator = Callable[[str], str]


def normalize_locale(locale: str | None) -> str:
    supported = {
        item.strip()
        for item in settings.app_locale_supported.split(",")
        if item.strip()
    }
    if not locale:
        return settings.app_locale_default

    short = locale.split("-", 1)[0].lower()
    if short in supported:
        return short
    return settings.app_locale_default


@cache
def _get_bundle(locale: str) -> FluentBundle:
    resource = FluentResource(
        (LOCALE_DIR / locale / "bot.ftl").read_text(encoding="utf-8"),
    )
    bundle = FluentBundle([locale])
    bundle.add_resource(resource)
    return bundle


def get_translator(locale: str | None = None) -> Callable[[str, Any], str]:
    current_locale = normalize_locale(locale)
    fallback_locale = settings.app_locale_default

    def translate(key: str, **kwargs: Any) -> str:
        for candidate in (current_locale, fallback_locale):
            bundle = _get_bundle(candidate)
            message = bundle.get_message(key)
            if message is None or message.value is None:
                continue

            value, errors = bundle.format_pattern(message.value, kwargs)
            if not errors:
                return value

        return key

    return translate


def get_user_translator(user: Any) -> Callable[[str, Any], str]:
    return get_translator(getattr(user, "language_code", None))
