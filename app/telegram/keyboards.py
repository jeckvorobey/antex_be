"""Inline клавиатуры Telegram бота."""

from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.telegram.i18n import get_translator


def _resolve_translator(translator=None):
    return translator or get_translator()


def home(_, **kwargs) -> InlineKeyboardMarkup:
    """Главное меню пользователя: обмен + заявки."""
    del kwargs
    translate = _resolve_translator(_)
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=translate("menu-exchange"),
                    callback_data="menu:exchange",
                ),
                InlineKeyboardButton(
                    text=translate("menu-orders"),
                    callback_data="menu:orders",
                ),
            ]
        ]
    )


def menu_operator(_, **kwargs) -> InlineKeyboardMarkup:
    """Меню оператора."""
    del kwargs
    translate = _resolve_translator(_)
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=translate("menu-orders"),
                    callback_data="menu:orders",
                ),
                InlineKeyboardButton(
                    text=translate("menu-exchange"),
                    callback_data="menu:exchange",
                ),
            ]
        ]
    )


def choose_currency(_, **kwargs) -> InlineKeyboardMarkup:
    """FSM шаг 1/4: выбор валюты + cancel."""
    del kwargs
    translate = _resolve_translator(_)
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=translate("btn-rub-thb"),
                    callback_data="exchange:currency:RUB",
                ),
                InlineKeyboardButton(
                    text=translate("btn-usdt-thb"),
                    callback_data="exchange:currency:USDT",
                ),
            ],
            [
                InlineKeyboardButton(
                    text=translate("btn-cancel"),
                    callback_data="fsm:cancel",
                )
            ],
        ]
    )


def obtaining(_, **kwargs) -> InlineKeyboardMarkup:
    """FSM шаг 3/4: способ получения + back/cancel."""
    del kwargs
    translate = _resolve_translator(_)
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=translate("btn-qr"),
                    callback_data="method:qr",
                ),
                InlineKeyboardButton(
                    text=translate("btn-transfer"),
                    callback_data="method:rs",
                ),
                InlineKeyboardButton(
                    text=translate("btn-cash"),
                    callback_data="method:cash",
                ),
            ],
            [
                InlineKeyboardButton(
                    text=translate("btn-back"),
                    callback_data="fsm:back",
                ),
                InlineKeyboardButton(
                    text=translate("btn-cancel"),
                    callback_data="fsm:cancel",
                ),
            ],
        ]
    )


def confirm_exchange(_, **kwargs) -> InlineKeyboardMarkup:
    """FSM шаг 4/4: confirm + cancel."""
    del kwargs
    translate = _resolve_translator(_)
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=translate("btn-confirm"),
                    callback_data="exchange:confirm",
                ),
                InlineKeyboardButton(
                    text=translate("btn-cancel"),
                    callback_data="fsm:cancel",
                ),
            ]
        ]
    )


def confirm_order(_=None, *, order_id: int | None = None, **kwargs) -> InlineKeyboardMarkup:
    """Клавиатура подтверждения заявки оператором."""
    del kwargs
    if order_id is None and isinstance(_, int):
        order_id = _
        _ = None
    if order_id is None:
        raise ValueError("order_id is required")

    translate = _resolve_translator(_)
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=translate("btn-confirm"),
                    callback_data=f"op:confirm:{order_id}",
                ),
                InlineKeyboardButton(
                    text=translate("btn-cancel"),
                    callback_data=f"op:cancel:{order_id}",
                ),
            ]
        ]
    )


def delivery_cash(_, **kwargs) -> InlineKeyboardMarkup:
    """Подтверждение получения наличных."""
    del kwargs
    translate = _resolve_translator(_)
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=translate("btn-confirm"),
                    callback_data="cash:confirm",
                ),
                InlineKeyboardButton(
                    text=translate("btn-cancel"),
                    callback_data="cash:cancel",
                ),
            ]
        ]
    )
