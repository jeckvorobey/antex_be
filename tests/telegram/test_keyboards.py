"""Тесты для inline клавиатур Telegram."""

from __future__ import annotations

from aiogram.types import InlineKeyboardMarkup, ReplyKeyboardMarkup

from app.telegram import keyboards


def test_home_returns_inline_keyboard(mock_i18n) -> None:
    assert isinstance(keyboards.home(mock_i18n), InlineKeyboardMarkup)


def test_home_no_reply_keyboard(mock_i18n) -> None:
    assert not isinstance(keyboards.home(mock_i18n), ReplyKeyboardMarkup)


def test_home_has_exchange_button(mock_i18n) -> None:
    kb = keyboards.home(mock_i18n)
    assert "menu:exchange" in _all_callbacks(kb)


def test_home_has_orders_button(mock_i18n) -> None:
    kb = keyboards.home(mock_i18n)
    assert "menu:orders" in _all_callbacks(kb)


def test_choose_currency_has_rub(mock_i18n) -> None:
    kb = keyboards.choose_currency(mock_i18n)
    assert "exchange:currency:RUB" in _all_callbacks(kb)


def test_choose_currency_has_usdt(mock_i18n) -> None:
    kb = keyboards.choose_currency(mock_i18n)
    assert "exchange:currency:USDT" in _all_callbacks(kb)


def test_fsm_keyboard_has_cancel(mock_i18n) -> None:
    for kb_fn in [
        keyboards.choose_currency,
        keyboards.obtaining,
        keyboards.confirm_exchange,
    ]:
        kb = kb_fn(mock_i18n)
        assert "fsm:cancel" in _all_callbacks(kb), f"Missing cancel in {kb_fn.__name__}"


def test_obtaining_has_all_three_methods(mock_i18n) -> None:
    kb = keyboards.obtaining(mock_i18n)
    cbs = _all_callbacks(kb)
    assert "method:qr" in cbs
    assert "method:rs" in cbs
    assert "method:cash" in cbs


def test_obtaining_has_back_button(mock_i18n) -> None:
    kb = keyboards.obtaining(mock_i18n)
    assert "fsm:back" in _all_callbacks(kb)


def test_confirm_order_embeds_id(mock_i18n) -> None:
    kb = keyboards.confirm_order(mock_i18n, order_id=99)
    cbs = _all_callbacks(kb)
    assert "op:confirm:99" in cbs
    assert "op:cancel:99" in cbs


def _all_callbacks(kb: InlineKeyboardMarkup) -> list[str]:
    return [
        btn.callback_data
        for row in kb.inline_keyboard
        for btn in row
        if btn.callback_data
    ]
