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

    assert "👉 🇹🇭 1 THB → 2.51 RUB 🇷🇺" in text
    assert "THB/RUB" not in text
    assert "1 THB = 2.51 RUB" not in text


def test_exchange_pair_rates_format_is_readable_with_currency_emoji() -> None:
    stamp = datetime(2026, 5, 29, 12, 0, tzinfo=UTC)
    pairs = [
        ExchangePairSnapshot(
            pair_id=pair_id,
            label=label,
            currency_sell=sell,
            currency_buy=buy,
            country=Country.THAILAND,
            base_rate=rate,
            client_rate=rate,
            calculation_rate=rate,
            rate_display=rate_display,
            rate_text=f"1 {sell} = {rate_display} {buy}",
            amount_sell_example=100,
            amount_buy_example=100 * rate,
            updated_at=stamp,
            available_methods=["qrcode", "cash"],
        )
        for pair_id, label, sell, buy, rate, rate_display in [
            ("rub-thb", "THB/RUB", "THB", "RUB", 2.51, "2.51"),
            ("usdt-thb", "USDT/THB", "USDT", "THB", 35.11, "35.11"),
            ("usdt-gel", "USDT/GEL", "USDT", "GEL", 2.57, "2.57"),
            ("rub-gel", "GEL/RUB", "GEL", "RUB", 28.03, "28.03"),
            ("rub-vnd", "RUB/VND", "RUB", "VND", 354.16, "354.16"),
            ("usdt-vnd", "USDT/VND", "USDT", "VND", 25511.92, "25511.92"),
        ]
    ]

    text = messages.exchange_pair_rates(pairs, locale="ru")

    assert "💱 \u041a\u0443\u0440\u0441 \u0441\u0435\u0439\u0447\u0430\u0441:" in text
    assert "👉 🇹🇭 1 THB → 2.51 RUB 🇷🇺" in text
    assert "👉 ₮ 1 USDT → 35.11 THB 🇹🇭" in text
    assert "👉 ₮ 1 USDT → 2.57 GEL 🇬🇪" in text
    assert "👉 🇬🇪 1 GEL → 28.03 RUB 🇷🇺" in text
    assert "👉 🇷🇺 1 RUB → 354.16 VND 🇻🇳" in text
    assert "👉 ₮ 1 USDT → 25511.92 VND 🇻🇳" in text
    for pair in pairs:
        assert pair.label not in text
        assert pair.rate_text not in text
