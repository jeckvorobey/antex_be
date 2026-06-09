from __future__ import annotations

import re
from datetime import UTC, datetime

from app.enums.country import Country
from app.services.exchange import ExchangePairSnapshot
from app.telegram import messages


def test_exchange_rate_formats_all_rates_with_two_decimals() -> None:
    text = messages.exchange_rate(0.3977, 35.114)

    assert "0.40" in text
    assert "35.11" in text
    assert "0.3977" not in text
    assert "35.114" not in text


def test_order_created_includes_order_number() -> None:
    text = messages.order_created(2026050008)

    assert "".join(re.findall(r"\d", text)) == "2026050008"


def test_exchange_confirm_summary_uses_human_currency_labels() -> None:
    text = messages.exchange_confirm_summary(
        amount=15000,
        from_currency="RUB",
        result=5100,
        to_currency="THB",
        method="📱 По QR-коду",
        translator=messages.get_translator("ru"),
    )

    assert "🇷🇺 RUB" in text
    assert "🇹🇭 THB" in text
    assert "Проверьте заявку" in text


def test_order_creation_failed_for_limit_is_human_readable() -> None:
    text = messages.order_creation_failed(code="ORDER_ALREADY_EXISTS", locale="ru")

    assert "слишком много активных заявок" in text


def test_exchange_pair_rates_match_miniapp_display_orientation() -> None:
    stamp = datetime(2026, 5, 29, 12, 0, tzinfo=UTC)
    pairs = [
        ExchangePairSnapshot(
            pair_id="rub-thb",
            label="THB/RUB",
            currency_sell="THB",
            currency_buy="RUB",
            country=Country.THAILAND,
            base_rate=2.51,
            client_rate=2.51,
            calculation_rate=2.51,
            rate_display="2.51",
            rate_text="1 THB = 2.51 RUB",
            amount_sell_example=100,
            amount_buy_example=251.0,
            updated_at=stamp,
            available_methods=["qrcode", "cash"],
        )
    ]

    text = messages.exchange_pair_rates(pairs, locale="ru")

    assert "THB/RUB" in text
    assert "1 THB = 2.51 RUB" in text


def test_exchange_pair_rates_format_is_readable_with_currency_emoji() -> None:
    stamp = datetime(2026, 5, 29, 12, 0, tzinfo=UTC)
    pairs = [
        ExchangePairSnapshot(
            pair_id="rub-thb",
            label="THB/RUB",
            currency_sell="THB",
            currency_buy="RUB",
            country=Country.THAILAND,
            base_rate=2.51,
            client_rate=2.51,
            calculation_rate=2.51,
            rate_display="2.51",
            rate_text="1 THB = 2.51 RUB",
            amount_sell_example=100,
            amount_buy_example=251.0,
            updated_at=stamp,
            available_methods=["qrcode", "cash"],
        ),
        ExchangePairSnapshot(
            pair_id="usdt-thb",
            label="USDT/THB",
            currency_sell="USDT",
            currency_buy="THB",
            country=Country.THAILAND,
            base_rate=35.11,
            client_rate=35.11,
            calculation_rate=35.11,
            rate_display="35.11",
            rate_text="1 USDT = 35.11 THB",
            amount_sell_example=100,
            amount_buy_example=3511.0,
            updated_at=stamp,
            available_methods=["qrcode", "cash"],
        ),
    ]

    text = messages.exchange_pair_rates(pairs, locale="ru")

    assert "• 🇹🇭 THB → 🇷🇺 RUB (THB/RUB)" in text
    assert "  1 THB = 2.51 RUB" in text
    assert "• ₮ USDT → 🇹🇭 THB (USDT/THB)" in text
    assert "  1 USDT = 35.11 THB" in text
