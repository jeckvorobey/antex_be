# ruff: noqa: RUF001
from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.enums.order import OrderStatus
from app.telegram import messages
from app.telegram.order_cards import OrderMessageView, render_order_regular, render_order_rich


@pytest.fixture
def order_view() -> OrderMessageView:
    order = SimpleNamespace(
        publicNumber="2026080096",
        amountSell=10000,
        currencySell="USDT",
        amountBuy=325000,
        currencyBuy="THB",
        rate=32.5,
        methodGet="qrcode",
        country=SimpleNamespace(value="thailand"),
        city=SimpleNamespace(name="Бангкок"),
        user=SimpleNamespace(username="customer"),
    )
    return OrderMessageView.from_order(order)


@pytest.mark.parametrize(
    ("locale", "sell", "buy", "country", "method"),
    [
        ("ru", "10 000 ₮ USDT", "325 000 🇹🇭 THB", "Таиланд", "Наличные по QR"),
        ("en", "10,000 ₮ USDT", "325,000 🇹🇭 THB", "Thailand", "Cash by QR"),
    ],
)
def test_order_summary_renderers_are_locale_aware_and_equivalent(
    order_view: OrderMessageView,
    locale: str,
    sell: str,
    buy: str,
    country: str,
    method: str,
) -> None:
    rich = render_order_rich(order_view, locale=locale)
    regular = render_order_regular(order_view, locale=locale)

    assert "<table bordered striped>" in rich
    assert rich.count("<tr>") == 6
    for value in (sell, buy, country, method):
        assert value in rich
        assert value in regular


def test_order_summary_omits_missing_optional_values() -> None:
    view = OrderMessageView(
        public_number="2026080096",
        amount_sell=10000,
        currency_sell="USDT",
    )

    rich = render_order_rich(view, locale="ru")
    regular = render_order_regular(view, locale="ru")

    assert "Отдаёте" in rich
    assert "Получаете" not in rich
    assert "Курс" not in rich
    assert "Способ получения" not in regular
    assert "—" not in rich


def test_order_summary_escapes_persisted_telegram_values() -> None:
    view = OrderMessageView(
        public_number="2026080096",
        city="<script>alert(1)</script>",
        customer_username="<b>spoofed</b>",
    )

    rich = render_order_rich(view, locale="ru", include_customer=True)
    regular = render_order_regular(view, locale="ru", include_customer=True)

    assert "<script>" not in rich
    assert "&lt;script&gt;" in rich
    assert "<b>spoofed</b>" not in regular
    assert "@&lt;b&gt;spoofed&lt;/b&gt;" in regular


@pytest.mark.parametrize(
    ("locale", "required_copy"),
    [
        (
            "ru",
            "Напишите менеджеру первым. После вашего сообщения он сможет ответить "
            "и согласовать детали обмена.",
        ),
        (
            "en",
            "Message the manager first. Once you send a message, the manager can reply "
            "and confirm the exchange details.",
        ),
    ],
)
def test_handoff_copy_explains_why_customer_must_write_first(
    order_view: OrderMessageView,
    locale: str,
    required_copy: str,
) -> None:
    rich = messages.order_handoff_rich(order_view, locale=locale)
    regular = messages.order_handoff_html(order_view, locale=locale)

    assert "<footer>" in rich
    assert "<table bordered striped>" in rich
    assert required_copy in rich
    assert required_copy in regular
    for technical_copy in (
        "поле ввода",
        "автоматически",
        "Подготовленный текст",
        "input field",
        "automatically",
        "Prepared text",
    ):
        assert technical_copy not in rich
        assert technical_copy not in regular


def test_reminder_is_compact_and_keeps_order_direction(order_view: OrderMessageView) -> None:
    rich = messages.order_reminder_rich(order_view, locale="ru")
    regular = messages.order_reminder_html(order_view, locale="ru")

    assert "#2026080096" in rich
    assert "USDT → THB" in rich
    assert "напишите менеджеру первым" in rich.lower()
    assert "USDT → THB" in regular
    assert "поле ввода" not in regular


@pytest.mark.parametrize(
    ("status", "ru_title", "en_title"),
    [
        (OrderStatus.CREATED, "🆕 Новая заявка #2026080096", "🆕 New order #2026080096"),
        (
            OrderStatus.PROCESSING,
            "✅ Заявка #2026080096 принята в работу",
            "✅ Order #2026080096 is being processed",
        ),
        (
            OrderStatus.COMPLETED,
            "✅ Заявка #2026080096 завершена",
            "✅ Order #2026080096 completed",
        ),
        (OrderStatus.CANCELLED, "❌ Заявка #2026080096 отменена", "❌ Order #2026080096 cancelled"),
    ],
)
def test_manager_lifecycle_cards_share_one_composition(
    order_view: OrderMessageView,
    status: OrderStatus,
    ru_title: str,
    en_title: str,
) -> None:
    for locale, title in (("ru", ru_title), ("en", en_title)):
        rich = messages.manager_order_card_rich(order_view, status=status, locale=locale)
        regular = messages.manager_order_card_html(order_view, status=status, locale=locale)

        assert title in rich
        assert title in regular
        assert "<table bordered striped>" in rich
        assert "@customer" in rich
        assert "@customer" in regular


def test_manager_processing_card_does_not_claim_failed_delivery(
    order_view: OrderMessageView,
) -> None:
    rich = messages.manager_order_card_rich(
        order_view,
        status=OrderStatus.PROCESSING,
        customer_notified=False,
        locale="ru",
    )

    assert "сообщение клиенту не доставлено" in rich
    assert "Клиенту отправлена просьба" not in rich
