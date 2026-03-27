"""Тесты message helpers Telegram."""

from __future__ import annotations

from app.telegram import messages


def _clean_fluent_marks(value: str) -> str:
    return value.replace("\u2068", "").replace("\u2069", "")


def test_welcome_uses_translation(make_i18n) -> None:
    _ = make_i18n("ru")
    result = _clean_fluent_marks(messages.welcome("Serg", translator=_))
    assert "Serg" in result


def test_bot_state_messages_use_translation(make_i18n) -> None:
    _ = make_i18n("ru")
    assert "Бот" in messages.bot_disabled(translator=_)
    assert "включ" in messages.bot_turned_on(translator=_)
    assert "выключ" in messages.bot_turned_off(translator=_)


def test_exchange_messages_include_variables(make_i18n) -> None:
    _ = make_i18n("en")
    assert "Step 2" in _clean_fluent_marks(messages.exchange_step(2, 4, translator=_))
    assert "1 RUB" in _clean_fluent_marks(messages.exchange_rate(0.42, 33.5, "12:00", translator=_))
    assert "RUB" in _clean_fluent_marks(messages.enter_amount_prompt("RUB", translator=_))
    prompt = _clean_fluent_marks(messages.choose_method_prompt("THB", translator=_)).lower()
    assert "receive" in prompt


def test_exchange_confirm_summary(make_i18n) -> None:
    _ = make_i18n("ru")
    result = _clean_fluent_marks(
        messages.exchange_confirm_summary(
            amount=10000,
            from_currency="RUB",
            result=4200,
            to_currency="THB",
            method="QR",
            translator=_,
        )
    )
    assert "10000" in result or "10,000" in result
    assert "THB" in result


def test_order_status_messages(make_i18n) -> None:
    _ = make_i18n("ru")
    assert "#7" in _clean_fluent_marks(messages.order_created(7, 1, "RUB", 2, "THB", translator=_))
    assert "#8" in _clean_fluent_marks(messages.order_confirmed(8, translator=_))
    assert "#9" in _clean_fluent_marks(messages.order_cancelled(9, translator=_))
    assert "#10" in _clean_fluent_marks(messages.order_completed(10, translator=_))


def test_orders_helpers(make_i18n) -> None:
    _ = make_i18n("en")
    assert "orders" in messages.orders_header(translator=_).lower()
    assert "no orders" in messages.orders_empty(translator=_).lower()
    assert "#5" in _clean_fluent_marks(
        messages.orders_item(
            order_id=5,
            amount_sell=1000,
            currency_sell="USDT",
            amount_buy=33000,
            currency_buy="THB",
            translator=_,
        )
    )


def test_new_order_operator_contains_payload() -> None:
    result = messages.new_order_operator(1, 2, 3000, "RUB", 1000, "THB", "cash")
    assert "#1" in result
    assert "cash" in result
