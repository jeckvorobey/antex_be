"""Тесты для Fluent локализации Telegram бота."""

from __future__ import annotations

from pathlib import Path

import pytest

LOCALE_DIR = Path(__file__).parents[2] / "locale"
REQUIRED_KEYS = [
    "welcome",
    "menu-exchange",
    "menu-orders",
    "menu-rate-info",
    "exchange-step",
    "exchange-choose-currency",
    "exchange-enter-amount",
    "exchange-amount-invalid",
    "exchange-choose-method",
    "exchange-confirm-summary",
    "btn-confirm",
    "btn-cancel",
    "btn-back",
    "btn-home",
    "btn-qr",
    "btn-transfer",
    "btn-cash",
    "btn-rub-thb",
    "btn-usdt-thb",
    "order-created",
    "order-confirmed",
    "order-cancelled",
    "order-completed",
]


def _load_ftl_keys(locale: str) -> set[str]:
    ftl_path = LOCALE_DIR / locale / "bot.ftl"
    return {
        line.split("=", 1)[0].strip()
        for line in ftl_path.read_text(encoding="utf-8").splitlines()
        if "=" in line and not line.lstrip().startswith("#")
    }


def test_ru_ftl_file_exists() -> None:
    assert (LOCALE_DIR / "ru" / "bot.ftl").exists()


def test_en_ftl_file_exists() -> None:
    assert (LOCALE_DIR / "en" / "bot.ftl").exists()


@pytest.mark.parametrize("key", REQUIRED_KEYS)
def test_ru_has_required_key(key: str) -> None:
    assert key in _load_ftl_keys("ru"), f"Missing key '{key}' in ru/bot.ftl"


@pytest.mark.parametrize("key", REQUIRED_KEYS)
def test_en_has_required_key(key: str) -> None:
    assert key in _load_ftl_keys("en"), f"Missing key '{key}' in en/bot.ftl"


def test_ru_en_key_parity() -> None:
    assert _load_ftl_keys("ru") == _load_ftl_keys("en")


def test_exchange_step_interpolates(make_i18n) -> None:
    _ = make_i18n("ru")
    result = _("exchange-step", current=2, total=4)
    assert "2" in result and "4" in result


def test_welcome_interpolates_name(make_i18n) -> None:
    _ = make_i18n("ru")
    result = _("welcome", name="Serg")
    assert "Serg" in result
