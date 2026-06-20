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
        country="Таиланд",
        city="Бангкок",
        rate="1 RUB = 0.34 THB",
        amount=15000,
        from_currency="RUB",
        result=5100,
        to_currency="THB",
        method="📱 По QR-коду",
        locale="ru",
    )

    assert "🌍 Страна: Таиланд" in text
    assert "🏙️ Город: Бангкок" in text
    assert "📈 Курс: 1 RUB = 0.34 THB" in text  # noqa: RUF001
    assert "💸 Отдаёте: 15,000 🇷🇺 RUB" in text
    assert "💰 Получаете: 5,100 🇹🇭 THB" in text
    assert "🧾 Способ получения: 📱 По QR-коду" in text
    assert "Проверьте заявку" in text


def test_exchange_confirm_summary_omits_city_when_missing() -> None:
    text = messages.exchange_confirm_summary(
        country="Грузия",
        rate="1 RUB = 0.031 GEL",
        amount=10000,
        from_currency="RUB",
        result=310,
        to_currency="GEL",
        method="💵 Наличные",
        locale="ru",
    )

    assert "🏙️ Город:" not in text
    assert "🌍 Страна: Грузия" in text


def test_order_creation_failed_for_limit_is_human_readable() -> None:
    text = messages.order_creation_failed(code="ORDER_ALREADY_EXISTS", locale="ru")

    assert "слишком много активных заявок" in text


def test_orders_item_uses_compact_multiline_format() -> None:
    text = messages.orders_item(
        order_id="2026060011",
        status=1,
        amount_sell=1400,
        currency_sell="USDT",
        amount_buy=35738752.0,
        currency_buy="VND",
        rate=25527.68,
        method="cash",
        created_at=datetime(2026, 6, 13, 0, 45, tzinfo=UTC),
        updated_at=None,
        end_time=None,
        locale="ru",
    )

    assert "#2026060011: Новая" in text
    assert "1,400 ₮ USDT → 35,738,752.0 🇻🇳 VND" in text
    assert "Курс: 25527.68" in text
    assert "Способ получения: Доставка наличных" in text
    assert "13.06.2026 00:45 UTC" in text


def test_orders_item_respects_english_locale() -> None:
    text = messages.orders_item(
        order_id="2026060011",
        status=2,
        amount_sell=1400,
        currency_sell="USDT",
        amount_buy=35738752.0,
        currency_buy="VND",
        rate=25527.68,
        method="cash",
        created_at=datetime(2026, 6, 13, 0, 45, tzinfo=UTC),
        updated_at=None,
        end_time=None,
        locale="en",
    )

    assert "#2026060011: In progress" in text
    assert "1,400 ₮ USDT → 35,738,752.0 🇻🇳 VND" in text
    assert "Rate: 25527.68" in text
    assert "Payout method: Cash delivery" in text


def test_choose_service_prompt_lists_service_options() -> None:
    text = messages.choose_service_prompt("thailand", locale="ru")

    assert "<b>💠 Выберите подходящую услугу</b>" in text
    assert "🚕 <u><i>Доставка наличных</i></u>" in text
    assert "🏧 <u><i>Наличные по QR</i></u>" in text
    assert "💳 <u><i>Перевод</i></u>" in text
    assert "🧰 <u><i>Оплата сервисов</i></u>" in text


def test_choose_city_prompt_mentions_cash_delivery() -> None:
    text = messages.choose_city_prompt("cash_delivery", locale="ru")

    assert "Выберите город доставки наличных" in text


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

    assert "🇹🇭 1 THB от 2.51 RUB 🇷🇺" in text
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

    assert "🏦 Текущий курс:" not in text
    assert "🇹🇭 1 THB от 2.51 RUB 🇷🇺" in text
    assert "₮ 1 USDT от 35.11 THB 🇹🇭" in text
    assert "₮ 1 USDT от 2.57 GEL 🇬🇪" in text
    assert "🇬🇪 1 GEL от 28.03 RUB 🇷🇺" in text
    assert "🇷🇺 1 RUB от 354.16 VND 🇻🇳" in text
    assert "₮ 1 USDT от 25511.92 VND 🇻🇳" in text
    for pair in pairs:
        assert pair.label not in text
        assert pair.rate_text not in text
