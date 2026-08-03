# ruff: noqa: RUF001
from __future__ import annotations

import re
from datetime import UTC, datetime
from decimal import Decimal

from app.enums.country import Country
from app.services.exchange import ExchangePairSnapshot
from app.telegram import messages


def _strip_bidi_marks(text: str) -> str:
    return text.replace("\u2068", "").replace("\u2069", "")


def test_exchange_rate_formats_all_rates_with_two_decimals() -> None:
    text = messages.exchange_rate(0.3977, 35.114)

    assert "0.40" in text
    assert "35.11" in text
    assert "0.3977" not in text
    assert "35.114" not in text


def test_order_created_includes_order_number() -> None:
    text = messages.order_created(2026050008)

    assert "".join(re.findall(r"\d", text)) == "2026050008"


def test_order_created_adds_queue_notice_only_for_offline_managers() -> None:
    offline_text = messages.order_created(2026050008, managers_offline=True, locale="ru")
    offline_english_text = messages.order_created(
        2026050008,
        managers_offline=True,
        locale="en",
    )
    usual_text = messages.order_created(2026050008, managers_offline=False, locale="ru")

    assert "<blockquote>Менеджер обработает заявку утром" in offline_text
    assert "<blockquote>A manager will process the order in the morning" in offline_english_text
    assert "Менеджер обработает заявку утром" not in usual_text
    assert "после начала рабочего дня в порядке очереди" not in offline_text
    assert "Пожалуйста, ожидайте подтверждения" not in offline_text
    assert "Пожалуйста, ожидайте подтверждения" in usual_text


def test_exchange_off_hours_confirmation_is_localized() -> None:
    text = messages.exchange_off_hours_confirmation(
        "Пн–Пт с 10:00 до 19:00 МСК",
        locale="ru",
    )
    en_text = messages.exchange_off_hours_confirmation(
        "Mon–Fri from 10:00 to 19:00 MSK",
        locale="en",
    )

    assert "Менеджеры сейчас не работают" in text
    assert "Заявка будет обработана утром" in text
    assert "Пн–Пт с 10:00 до 19:00 МСК" in text
    assert "Managers are not working right now" in en_text
    assert "Mon–Fri from 10:00 to 19:00 MSK" in en_text


def test_exchange_off_hours_alert_is_short() -> None:
    text = messages.exchange_off_hours_alert(locale="ru")

    assert text == "Менеджер обработает заявку утром после начала рабочего дня."


def test_exchange_start_welcome_uses_template_and_current_business_schedule() -> None:
    text = messages.exchange_start_welcome(
        "Сергей",
        locale="ru",
        business_hours_text="Пн–Пт с 10:00 до 22:00 МСК",
    )

    assert "<h2>💱 AntEx</h2>" in text
    assert "<footer>Обмен валюты и оплата услуг</footer>" in text
    assert "Заявки принимаются круглосуточно" in text
    assert "<blockquote>🕘 <b>Режим работы</b>" in text
    assert "Менеджеры: Пн–Пт с 10:00 до 22:00 МСК." in _strip_bidi_marks(text)
    assert "Обработаем утром" not in text


def test_exchange_start_welcome_adds_offline_notice_only_when_confirmed() -> None:
    ru_text = messages.exchange_start_welcome(
        "Сергей",
        locale="ru",
        managers_offline=True,
    )
    en_text = messages.exchange_start_welcome(
        "Sergey",
        locale="en",
        managers_offline=True,
    )
    unknown_text = messages.exchange_start_welcome(
        "Сергей",
        locale="ru",
        managers_offline=False,
    )

    assert "<blockquote>⚠️ <b>Обработаем утром, в рабочее время</b>" in ru_text
    assert "Оформить заявку можно уже сейчас." in ru_text
    assert "We’ll process it in the morning, during working hours" in en_text
    assert "You can create an order now." in en_text
    assert "Обработаем утром, в рабочее время" not in unknown_text


def test_exchange_start_welcome_escapes_first_name_for_html() -> None:
    text = messages.exchange_start_welcome("<b>Сергей</b>", locale="ru")

    assert "&lt;b&gt;Сергей&lt;/b&gt;" in text
    assert "<b>Сергей</b>" not in text


def test_referral_bonus_credited_is_short_and_formats_amount_with_two_decimals() -> None:
    ru_text = messages.referral_bonus_credited(amount="0.2", order_id="2026070068", locale="ru")
    en_text = messages.referral_bonus_credited(
        amount=Decimal("2"),
        order_id="2026070068",
        locale="en",
    )

    assert (
        _strip_bidi_marks(ru_text) == "🎁 Вознаграждение по реферальной программе: +0.20 ATXG\n"
        "За успешно завершённую заявку #2026070068."
    )
    assert (
        _strip_bidi_marks(en_text)
        == "🎁 Referral program reward: +2.00 ATXG\nFor completed order #2026070068."
    )


def test_referral_bonus_reversed_is_short_and_formats_amount_with_two_decimals() -> None:
    ru_text = messages.referral_bonus_reversed(
        amount=Decimal("100.456"),
        order_id="2026070068",
        locale="ru",
    )
    en_text = messages.referral_bonus_reversed(amount="0.25", order_id="2026070068", locale="en")

    assert (
        _strip_bidi_marks(ru_text)
        == "💸 Вознаграждение по реферальной программе списано: -100.46 ATXG\n"
        "Заявка #2026070068 отменена."
    )
    assert (
        _strip_bidi_marks(en_text) == "💸 Referral program reward reversed: -0.25 ATXG\n"
        "Order #2026070068 was cancelled."
    )


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
    assert "📈 Курс: 1 RUB = 0.34 THB" in text
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


def test_choose_service_prompt_uses_rich_structure_and_list() -> None:
    text = messages.choose_service_prompt("thailand", locale="ru")

    assert "<footer>Выбор услуги</footer>" in text
    assert "<h2>💎 Как вам удобнее получить деньги?</h2>" in text
    assert "Шаг 2" not in text
    assert "<ul>" in text
    assert "<li><b>🚕 Доставка наличных</b><br/>Привезём деньги в удобное место.</li>" in text
    assert "<li><b>🏧 Наличные по QR</b><br/>Получите наличные через банкомат.</li>" in text
    assert "<li><b>💳 Перевод</b><br/>Переведём на счёт в местном банке.</li>" in text
    assert "<li><b>🧰 Оплата сервисов</b><br/>Поможем оплатить нужные услуги.</li>" in text


def test_choose_city_prompt_uses_rich_structure() -> None:
    text = messages.choose_city_prompt("cash_delivery", locale="ru")

    assert "<footer>Доставка наличных</footer>" in text
    assert "<h2>📍 Выберите город</h2>" in text
    assert "<p>Укажите город, куда нужно привезти наличные.</p>" in text
    assert "<hr/>" in text
    assert "<h3>Доступные города</h3>" in text
    assert "<p>Выберите город на кнопке ниже.</p>" in text
    assert "Шаг 3" not in text


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

def test_choose_currency_prompt_uses_rich_table_and_usdt_symbol() -> None:
    pairs = [
        ExchangePairSnapshot(
            pair_id="rub-vnd",
            label="RUB/VND",
            currency_sell="RUB",
            currency_buy="VND",
            country=Country.VIETNAM,
            base_rate=320.35,
            client_rate=320.35,
            calculation_rate=320.35,
            rate_display="320.35",
            rate_text="1 RUB = 320.35 VND",
            amount_sell_example=1,
            amount_buy_example=320.35,
            updated_at=datetime(2026, 6, 9, 12, 0, tzinfo=UTC),
            available_methods=["cash"],
        ),
        ExchangePairSnapshot(
            pair_id="usdt-vnd",
            label="USDT/VND",
            currency_sell="USDT",
            currency_buy="VND",
            country=Country.VIETNAM,
            base_rate=25479.90,
            client_rate=25479.90,
            calculation_rate=25479.90,
            rate_display="25479.90",
            rate_text="1 USDT = 25479.90 VND",
            amount_sell_example=1,
            amount_buy_example=25479.90,
            updated_at=datetime(2026, 6, 9, 12, 0, tzinfo=UTC),
            available_methods=["cash"],
        ),
    ]

    text = messages.choose_currency_prompt(pairs, locale="ru")

    assert "<footer>Выбор валюты</footer>" in text
    assert "<h2>💱 Какую валюту обменять?</h2>" in text
    assert "<table bordered striped>" in text
    assert "<th>Валюта</th><th>Курс</th>" in text
    assert "<td>🇷🇺 <b>RUB</b></td>" in text
    assert "<td>₮ <b>USDT</b></td>" in text
    assert "<b>25479.90 VND</b> 🇻🇳" in text
    assert "Шаг 4" not in text
